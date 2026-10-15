"""One git worktree per task for projects in worktree mode (ADR 0009).

- Created when the task first starts: `<project folder>.wt\\T-142`, branch `agentic/T-142`, from
  the project's base branch (an existing branch, e.g. after a retry, is reused).
- Shared by every stage and retry of the task: QA sees what Dev did.
- Released when the task is done or cancelled, with its CLI already closed: uncommitted work is
  committed to the branch first (never lost), then the folder goes and the branch stays (the user
  merges it). The folder's trust is forgotten (services.trust).
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from agentic_os.models import Project, Task, TaskEventKind, WorkspaceMode
from agentic_os.services import git
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


class Worktrees:
    def __init__(self, trust: TrustCleaner | None = None) -> None:
        self._trust = trust

    def prepare(self, db: Session, task: Task, project: Project) -> str | None:
        """The folder the task works in (None: the project folder itself)."""
        if project.workspace_mode != WorkspaceMode.WORKTREE:
            return None
        if task.worktree_path and Path(task.worktree_path).is_dir():
            return task.worktree_path
        info = git.detect(project.path)
        base = project.base_branch or (info.branch if info else None)
        if not base:
            raise git.GitError("the project has no base branch")
        branch = branch_for(task)
        path = root_for(project) / task.code
        path.parent.mkdir(parents=True, exist_ok=True)
        if git.branch_exists(project.path, branch):
            git.run(project.path, "worktree", "add", str(path), branch)
            origin = _merge_base(project.path, base, branch)
        else:
            origin = git.run(project.path, "rev-parse", base).strip()
            git.run(project.path, "worktree", "add", "-b", branch, str(path), base)
        task.worktree_path, task.branch = str(path), branch
        # The origin of the task's diff (a retry keeps the first one).
        task.base_commit = task.base_commit or origin
        task_ops.add_event(db, task, TaskEventKind.WORKSPACE, f"worktree {path} ({branch})")
        return str(path)

    def release(self, db: Session, task: Task, project: Project) -> None:
        """Never raises: a worktree that cannot be removed is recorded on the task (it keeps
        `worktree_path`, so the UI can show it) and the task still ends."""
        if not task.worktree_path:
            return
        path = task.worktree_path
        try:
            if Path(path).is_dir():
                self._commit_leftovers(task, path)
                self._remove(project.path, path)
        except git.GitError as error:
            log.warning("could not remove the worktree", task=task.code, error=str(error))
            task_ops.add_event(db, task, TaskEventKind.WORKSPACE, f"worktree not removed: {error}")
            return
        task.worktree_path = None
        task_ops.add_event(
            db, task, TaskEventKind.WORKSPACE, f"worktree removed; branch {task.branch} kept"
        )
        if self._trust is not None:
            self._trust.forget(path)

    @staticmethod
    def _commit_leftovers(task: Task, path: str) -> None:
        if not git.run(path, "status", "--porcelain").strip():
            return
        identity = () if _has_identity(path) else FALLBACK_IDENTITY
        git.run(path, "add", "-A")
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


def _merge_base(repo: str, base: str, branch: str) -> str | None:
    try:
        return git.run(repo, "merge-base", base, branch, timeout=10).strip() or None
    except git.GitError:
        return None


def _has_identity(path: str) -> bool:
    try:
        return bool(git.run(path, "config", "--get", "user.email", timeout=10).strip())
    except git.GitError:  # exit code 1: not set
        return False
