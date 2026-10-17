"""One git worktree per task and repository for projects in worktree mode (ADR 0009, ADR 0016).

- Created when the task first starts, in the task's work folder `<project folder>.wt\\T-142`, on
  branch `agentic/T-142` from each repository's base branch (an existing branch, e.g. after a
  retry, is reused).
- A project with **one** repository gets its worktree as the work folder itself. With several, the
  work folder mirrors the project: each repository's worktree sits at the repository's path inside
  the project (`backend/`, `frontend/`), and linked repositories outside the folder at
  `@<name>/`. Files that belong to no repository are not in the work folder.
- Shared by every stage and retry of the task: QA sees what Dev did.
- Released when the task is done or cancelled, with its CLI already closed: uncommitted work is
  committed to each branch first (never lost), then the folders go and the branches stay (the user
  merges them). In a task with several repositories, the branches that got no commits are
  dropped. The folder's trust is forgotten (services.trust).
"""

from __future__ import annotations

import contextlib
import os
import re
import time
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import Project, ProjectRepo, Task, TaskEventKind, TaskRepo, WorkspaceMode
from agentic_os.services import git, repos
from agentic_os.services import tasks as task_ops
from agentic_os.services.trust import TrustCleaner

log = structlog.get_logger()

REMOVE_ATTEMPTS = 4
REMOVE_PAUSE = 1.0  # Windows may hold files of a process that has just exited
# Identity for the safety commit when the repo has none configured.
FALLBACK_IDENTITY = ("user.name=Agentic OS", "user.email=agentic-os@localhost")


def root_for(project: Project) -> Path:
    folder = Path(project.path)
    return folder.with_name(folder.name + ".wt")


def branch_for(task: Task) -> str:
    return f"agentic/{task.code}"


def _branch_of(db: Session, task: Task) -> str:
    """The task's branch: a task that resolves conflicts works on the branch it resolves."""
    original = db.get(Task, task.resolves_task_id) if task.resolves_task_id else None
    if original is not None:
        return original.branch or branch_for(original)
    return branch_for(task)


def layouts(members: list[ProjectRepo]) -> dict[str, str]:
    """Where each repository's worktree goes inside the work folder, by repository id ("" when
    it is the work folder itself)."""
    if len(members) == 1:
        return {members[0].id: ""}
    taken: set[str] = set()
    result: dict[str, str] = {}
    for repo in members:
        if repo.rel_path is not None:
            result[repo.id] = repo.rel_path
            continue
        name = "@" + (re.sub(r'[<>:"/\\|?*]', "_", repo.name).strip(" .") or "repo")
        candidate, n = name, 2
        while candidate in taken:
            candidate, n = f"{name}-{n}", n + 1
        taken.add(candidate)
        result[repo.id] = candidate
    return result


def _task_rows(db: Session, task: Task) -> list[TaskRepo]:
    return list(db.scalars(select(TaskRepo).where(TaskRepo.task_id == task.id)))


class Worktrees:
    def __init__(self, trust: TrustCleaner | None = None) -> None:
        self._trust = trust

    # ------------------------------------------------------------------------------ prepare
    def prepare(self, db: Session, task: Task, project: Project) -> str | None:
        """The folder the task works in (None: the project folder itself)."""
        if project.workspace_mode != WorkspaceMode.WORKTREE:
            return None
        if task.worktree_path and Path(task.worktree_path).is_dir():
            return task.worktree_path
        members = self._members(db, task, project)
        if not members:
            raise git.GitError("the project has no git repository")
        work = root_for(project) / task.code
        where = layouts(members)
        # The repository at the work folder first, then those inside it, by depth.
        ordered = sorted(members, key=lambda r: (len(Path(where[r.id]).parts), where[r.id]))
        branch = _branch_of(db, task)
        made: list[tuple[ProjectRepo, Path, str | None]] = []
        try:
            for repo in ordered:
                folder = work / where[repo.id] if where[repo.id] else work
                origin = self._add(project, repo, branch, folder)
                made.append((repo, folder, origin))
        except git.GitError:
            for repo, folder, _ in reversed(made):
                with contextlib.suppress(git.GitError):
                    self._remove(repo.path, str(folder))
            raise
        rows = {row.repo_id: row for row in _task_rows(db, task)}
        for repo, folder, origin in made:
            row = rows.get(repo.id)
            if row is None:
                row = TaskRepo(task_id=task.id, repo_id=repo.id, branch=branch)
                db.add(row)
            row.worktree_path = str(folder)
            # The origin of the task's diff: a retry keeps the first one.
            row.base_commit = row.base_commit or origin
        task.worktree_path, task.branch = str(work), branch
        names = ", ".join(r.name for r, _, _ in made)
        extra = f" · {names}" if len(made) > 1 else ""
        task_ops.add_event(db, task, TaskEventKind.WORKSPACE, f"worktree {work} ({branch}){extra}")
        return str(work)

    @staticmethod
    def _members(db: Session, task: Task, project: Project) -> list[ProjectRepo]:
        """The repositories the task works in: those it already has (a retry), else those of the
        project that take part."""
        known = [row.repo_id for row in _task_rows(db, task)]
        # A task that resolves another's conflicts works only where there are some.
        from agentic_os.services import integration

        wanted = None if known else integration.resolving_repos(db, task, project)
        if wanted is not None:
            return [r for r in repos.active(db, project) if r.id in wanted]
        if known:
            found = [db.get(ProjectRepo, repo_id) for repo_id in known]
            kept = [r for r in found if r is not None and not r.missing]
            if kept:
                return kept
        return repos.active(db, project)

    @staticmethod
    def _add(project: Project, repo: ProjectRepo, branch: str, folder: Path) -> str | None:
        base = repos.base_of(project, repo)
        if not base:
            info = git.detect(repo.path)
            base = info.branch if info else None
        if not base:
            raise git.GitError(f"the repository {repo.name} has no base branch")
        folder.parent.mkdir(parents=True, exist_ok=True)
        if git.branch_exists(repo.path, branch):
            git.run(repo.path, "worktree", "add", str(folder), branch)
            return git.merge_base(repo.path, base, branch)
        origin = git.run(repo.path, "rev-parse", base).strip()
        git.run(repo.path, "worktree", "add", "-b", branch, str(folder), base)
        return origin

    # ------------------------------------------------------------------------------ release
    def release(self, db: Session, task: Task, project: Project) -> None:
        """Never raises: a worktree that cannot be removed is recorded on the task (it keeps
        `worktree_path`, so the UI can show it) and the task still ends."""
        if not task.worktree_path:
            return
        work = task.worktree_path
        rows = [row for row in _task_rows(db, task) if row.worktree_path]
        try:
            self._release_rows(db, task, project, rows)
        except git.GitError as error:
            log.warning("could not remove the worktree", task=task.code, error=str(error))
            task_ops.add_event(db, task, TaskEventKind.WORKSPACE, f"worktree not removed: {error}")
            return
        _remove_empty_folders(Path(work))
        task.worktree_path = None
        task_ops.add_event(
            db, task, TaskEventKind.WORKSPACE, f"worktree removed; branch {task.branch} kept"
        )
        if Path(work).exists():  # files the agent wrote outside every repository: never deleted
            task_ops.add_event(
                db,
                task,
                TaskEventKind.WORKSPACE,
                f"files outside the repositories were left in {work}",
            )
        if self._trust is not None:
            self._trust.forget(work)

    def _release_rows(
        self, db: Session, task: Task, project: Project, rows: list[TaskRepo]
    ) -> None:
        if not rows:  # a task from before the repository rows: the work folder is the worktree
            path = task.worktree_path or ""
            if Path(path).is_dir():
                self._commit_leftovers(task, path, [])
                self._remove(project.path, path)
            return
        everyone = repos.ordered(db, project)
        pairs = [(row, db.get(ProjectRepo, row.repo_id)) for row in rows]
        # Deepest first: a repository's worktree can sit inside another's.
        pairs.sort(key=lambda p: -len(Path(p[0].worktree_path or "").parts))
        for row, repo in pairs:
            path = row.worktree_path or ""
            if repo is None or not Path(path).is_dir():
                row.worktree_path = None
                continue
            nested = [str(Path(n)) for n in repos.nested_paths(everyone, repo) if len(rows) > 1]
            self._commit_leftovers(task, path, nested)
            self._remove(repo.path, path)
            row.worktree_path = None
        if len(rows) > 1:
            self._drop_untouched_branches(db, project, rows)

    @staticmethod
    def _drop_untouched_branches(db: Session, project: Project, rows: list[TaskRepo]) -> None:
        """In a task with several repositories, the ones that got no commits leave no branch."""
        for row in rows:
            repo = db.get(ProjectRepo, row.repo_id)
            if repo is None or not row.base_commit:
                continue
            try:
                ahead = git.run(
                    repo.path, "rev-list", "--count", f"{row.base_commit}..{row.branch}", timeout=20
                ).strip()
                if ahead == "0":
                    git.run(repo.path, "branch", "-D", row.branch, timeout=20)
                    db.delete(row)
            except git.GitError as error:  # the branch is just kept
                log.warning("could not tidy a task branch", branch=row.branch, error=str(error))

    @staticmethod
    def _commit_leftovers(task: Task, path: str, nested: list[str]) -> None:
        if not git.run(path, "status", "--porcelain").strip():
            return
        identity = () if _has_identity(path) else FALLBACK_IDENTITY
        # Other repositories' worktrees inside this one are not part of its work.
        git.run(path, "add", "-A", "--", ".", *(f":(exclude){n}" for n in nested))
        if not git.run(path, "diff", "--cached", "--name-only").strip():
            return
        git.run(
            path,
            "commit",
            "-m",
            f"chore(agentic): uncommitted work of {task.code}",
            config=identity,
        )

    @staticmethod
    def _remove(repo: str, path: str) -> None:
        for attempt in range(1, REMOVE_ATTEMPTS + 1):
            try:
                git.run(repo, "worktree", "remove", "--force", path)
                break
            except git.GitError:
                if attempt == REMOVE_ATTEMPTS:
                    raise
                time.sleep(REMOVE_PAUSE)
        git.run(repo, "worktree", "prune")


def _remove_empty_folders(folder: Path) -> None:
    """The work folder of a multi-repository task keeps empty folders once its worktrees are
    gone. Only empty ones are removed, never files."""
    if not folder.is_dir():
        return
    for current, _dirs, _files in os.walk(folder, topdown=False):
        with contextlib.suppress(OSError):
            Path(current).rmdir()


def _has_identity(path: str) -> bool:
    try:
        return bool(git.run(path, "config", "--get", "user.email", timeout=10).strip())
    except git.GitError:  # exit code 1: not set
        return False
