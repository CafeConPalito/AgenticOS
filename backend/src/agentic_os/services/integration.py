"""Bringing the branches of a task into their bases (phase 12, ADR 0017).

A task of a project in worktree mode leaves a branch (`agentic/T-142`) in each repository it
worked in. Integrating makes that work part of the repository's base branch:

- Without touching any folder when the base is not checked out anywhere: the merged tree comes
  from `git merge-tree`, the commit from `commit-tree` and the branch moves with `update-ref`.
  A rebase uses `git replay`; if that is not possible it is done in a temporary worktree.
- When the base is checked out in a folder (the project's or a worktree), the folder has to be
  clean and it is moved forward with a fast-forward, so what is on disk follows the branch.

A repository where the work would conflict is left alone and reported; the repositories before it
stay integrated, as one group the person can undo. Conflicts are resolved by bringing the base
into the task's branch (in a worktree of its own, or by an agent) and integrating again.
"""

from __future__ import annotations

import contextlib
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import (
    GitOperation,
    InboxKind,
    Project,
    ProjectRepo,
    Task,
    TaskEventKind,
    TaskRepo,
)
from agentic_os.services import inbox, repos
from agentic_os.services import tasks as task_ops
from agentic_os.services.gitx import merge, oplog, read, remote, trees
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo
from agentic_os.services.worktrees import FALLBACK_IDENTITY, root_for

Mode = Literal["merge", "squash", "rebase"]
RepoState = Literal["nothing", "integrated", "clean", "conflicts", "blocked", "missing"]
Outcome = Literal["integrated", "nothing", "conflicts", "blocked", "failed", "missing"]
LABEL_PREFIX = "Integrar "


# ------------------------------------------------------------------------------ results
class RepoCheck(BaseModel):
    repo_id: str
    name: str
    branch: str
    base: str | None
    # Commits the branch has that the base does not.
    ahead: int = 0
    # Commits the base got since the branch left it.
    behind: int = 0
    state: RepoState
    conflicts: list[str] = Field(default_factory=list)
    # The folder where the base is checked out (None: nobody has it, nothing on disk moves).
    active_in: str | None = None
    # Uncommitted files in that folder, when that is what blocks the integration.
    dirty: list[str] = Field(default_factory=list)
    integrated_at: datetime | None = None
    integrated_sha: str | None = None


class IntegrationCheck(BaseModel):
    task_id: str
    repos: list[RepoCheck]
    # Something to integrate and nothing in the way.
    can_integrate: bool
    pending: int  # repositories with work still to integrate


class RepoOutcome(BaseModel):
    repo_id: str
    name: str
    status: Outcome
    sha: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    dirty: list[str] = Field(default_factory=list)
    error_code: str | None = None
    message: str = ""
    pushed: bool = False


class IntegrationResult(BaseModel):
    group_id: str
    repos: list[RepoOutcome]
    # Stopped before the last repository (conflicts or an error).
    stopped: bool
    integrated: int


class Resolution(BaseModel):
    repo_id: str
    name: str
    path: str
    conflicts: list[str]


@dataclass
class _Member:
    row: TaskRepo
    repo: ProjectRepo
    base: str | None


# ------------------------------------------------------------------------------ helpers
def _members(db: Session, task: Task, project: Project) -> list[_Member]:
    found: list[_Member] = []
    for row in db.scalars(select(TaskRepo).where(TaskRepo.task_id == task.id)):
        repo = db.get(ProjectRepo, row.repo_id)
        if repo is not None:
            found.append(_Member(row, repo, repos.base_of(project, repo)))
    order = {r.id: i for i, r in enumerate(repos.ordered(db, project))}
    return sorted(found, key=lambda m: order.get(m.repo.id, 0))


def _count(repo: Repo, spec: str) -> int:
    return int((repo.attempt("rev-list", "--count", spec) or "0").strip() or 0)


def _exists(repo: Repo, ref: str) -> bool:
    return repo.attempt("rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None


def _checked_out(repo: Repo, base: str) -> str | None:
    """The folder that has the base branch checked out, if any."""
    for tree in trees.worktrees(repo):
        if tree.branch == base and not tree.prunable:
            return tree.path
    return None


def _dirty(folder: str) -> list[str]:
    out = Repo(folder).attempt("status", "--porcelain", "--untracked-files=no") or ""
    return [line[3:] for line in out.splitlines() if line.strip()]


def _merge_tree(repo: Repo, base: str, branch: str) -> tuple[str, list[str]]:
    """The tree merging the branch into the base would give and the files that would conflict
    (none: it merges clean). Writes only objects, never refs or folders."""
    out = repo.run("merge-tree", "--write-tree", "--name-only", base, branch, ok=(0, 1))
    lines = out.splitlines()
    # The tree, then the conflicting file names up to a blank line (a clean merge has none).
    names: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            break
        names.append(line.strip())
    return (lines[0].strip() if lines else ""), names


def _identity(repo: Repo) -> tuple[str, ...]:
    return (
        () if (repo.attempt("config", "--get", "user.email") or "").strip() else FALLBACK_IDENTITY
    )


def _check_member(member: _Member) -> RepoCheck:
    row, project_repo, base = member.row, member.repo, member.base
    info = RepoCheck(
        repo_id=project_repo.id,
        name=project_repo.name,
        branch=row.branch,
        base=base,
        state="missing",
        integrated_at=row.integrated_at,
        integrated_sha=row.integrated_sha,
    )
    path = project_repo.path
    if project_repo.missing or not Path(path).is_dir() or not base:
        return info
    repo = Repo(path)
    if not _exists(repo, row.branch) or not _exists(repo, base):
        return info
    info.ahead = _count(repo, f"{base}..{row.branch}")
    info.behind = _count(repo, f"{row.branch}..{base}")
    if info.ahead == 0:
        info.state = "integrated" if row.integrated_at else "nothing"
        return info
    info.active_in = _checked_out(repo, base)
    tree, conflicts = _merge_tree(repo, base, row.branch)
    if conflicts:
        info.state, info.conflicts = "conflicts", conflicts
    elif (repo.attempt("rev-parse", f"{base}^{{tree}}") or "").strip() == tree:
        # Squashed or rebased earlier: the branch's commits are not in the base, its changes are.
        info.state = "integrated" if row.integrated_at else "nothing"
    elif info.active_in and (dirty := _dirty(info.active_in)):
        info.state, info.dirty = "blocked", dirty
    else:
        info.state = "clean"
    return info


def check(db: Session, task: Task, project: Project) -> IntegrationCheck:
    """What integrating the task would do, without changing anything."""
    checks = [_check_member(m) for m in _members(db, task, project)]
    pending = [c for c in checks if c.state in ("clean", "conflicts", "blocked")]
    return IntegrationCheck(
        task_id=task.id,
        repos=checks,
        pending=len(pending),
        can_integrate=bool(pending) and all(c.state == "clean" for c in pending),
    )


# ------------------------------------------------------------------------------ integrating
def _message(task: Task, mode: Mode, repo: Repo, base: str, branch: str) -> str:
    if mode == "merge":
        return f"Merge {task.code}: {task.title}"
    subjects = repo.attempt("log", "--reverse", "--format=- %s", f"{base}..{branch}") or ""
    return f"{task.code}: {task.title}\n\n{subjects.strip()}"


def _advance(repo: Repo, base: str, new: str, old: str, folder: str | None) -> None:
    """Moves the base branch to `new`, a descendant of `old`. A checked-out base follows on disk."""
    if folder:
        Repo(folder).run("merge", "--ff-only", new, timeout=120)
    else:
        repo.run("update-ref", f"refs/heads/{base}", new, old)


def _replay(repo: Repo, base: str, branch: str) -> None:
    """Moves the branch's commits on top of the base without a folder. Older git versions print
    the ref updates instead of doing them."""
    out = repo.run("replay", "--onto", base, f"{base}..{branch}", timeout=300)
    updates = [line for line in out.splitlines() if line.startswith("update ")]
    if updates:
        repo.run("update-ref", "--stdin", input="\n".join(updates) + "\n")


def _rebase_in_temp(repo: Repo, base: str, branch: str, work: Path) -> list[str]:
    """The fallback of `git replay`: a throwaway worktree. Returns the conflicting files (the
    branch is then left as it was)."""
    work.parent.mkdir(parents=True, exist_ok=True)
    repo.run("worktree", "add", "--detach", str(work), branch)
    scratch = Repo(str(work))
    try:
        result = merge.rebase(scratch, base)
        if result.status == "conflicts":
            conflicts = result.conflicts
            merge.proceed(scratch, "abort")
            return conflicts or ["?"]
        repo.run("branch", "-f", branch, scratch.run("rev-parse", "HEAD").strip())
        return []
    finally:
        with contextlib.suppress(GitxError):
            trees.remove(repo, str(work), force=True)
        shutil.rmtree(work, ignore_errors=True)


def _integrate_one(
    task: Task, member: _Member, mode: Mode, scratch: Path
) -> tuple[Outcome, str | None, list[str]]:
    """Integrates one repository. Returns the outcome, the new tip of the base and the conflicts."""
    base, branch = member.base or "", member.row.branch
    repo = Repo(member.repo.path)
    with repo.write():
        old = repo.run("rev-parse", base).strip()
        folder = _checked_out(repo, base)
        if folder and (dirty := _dirty(folder)):
            raise GitxError(
                "dirty_worktree", "the base branch has uncommitted changes: " + ", ".join(dirty)
            )
        config = _identity(repo)
        if mode == "rebase":
            try:
                _replay(repo, base, branch)
            except GitxError:
                conflicts = _rebase_in_temp(repo, base, branch, scratch)
                if conflicts:
                    return "conflicts", None, conflicts
            new = repo.run("rev-parse", branch).strip()
        else:
            tree, conflicts = _merge_tree(repo, base, branch)
            if conflicts:
                return "conflicts", None, conflicts
            parents = ["-p", base] + (["-p", branch] if mode == "merge" else [])
            new = repo.run(
                "commit-tree",
                tree,
                *parents,
                "-m",
                _message(task, mode, repo, base, branch),
                config=config,
            ).strip()
        _advance(repo, base, new, old, folder)
        return "integrated", new, []


def run(
    db: Session,
    task: Task,
    project: Project,
    mode: Mode,
    *,
    push: bool = False,
    delete_branches: bool = False,
    group_id: str | None = None,
) -> IntegrationResult:
    """Integrates the task's branches, repository by repository, as one group that can be undone.
    Stops at the first repository that cannot be integrated; the ones before it stay done."""
    group = group_id or str(uuid.uuid4())
    outcomes: list[RepoOutcome] = []
    stopped = False
    integrated = 0
    members = _members(db, task, project)
    for member in members:
        project_repo = member.repo
        item = RepoOutcome(repo_id=project_repo.id, name=project_repo.name, status="nothing")
        outcomes.append(item)
        info = _check_member(member)
        if info.state in ("nothing", "integrated"):
            continue
        if info.state == "missing":
            item.status, item.message = "missing", "the repository or its branch is gone"
            stopped = True
            break
        if info.state == "blocked":
            item.status, item.dirty = "blocked", info.dirty
            item.error_code = "dirty_worktree"
            stopped = True
            break
        repo = Repo(project_repo.path)
        operation = oplog.begin(
            db,
            project_repo,
            repo,
            "integrate",
            f"{LABEL_PREFIX}{task.code} en {member.base}",
            group_id=group,
        )
        scratch = root_for(project) / f"integrate-{uuid.uuid4().hex[:8]}"
        try:
            status, sha, conflicts = _integrate_one(task, member, mode, scratch)
        except GitxError as error:
            oplog.drop_if_unchanged(db, operation, repo)
            item.status, item.error_code, item.message = "failed", error.code, error.message
            stopped = True
            break
        oplog.finish(operation, repo)
        if status == "conflicts":
            db.delete(operation)
            item.status, item.conflicts = "conflicts", conflicts
            stopped = True
            break
        item.status, item.sha = "integrated", sha
        member.row.integrated_at, member.row.integrated_sha = datetime.now(UTC), sha
        integrated += 1
        if push:
            item.pushed = _push(repo, member.base or "", item)
        if delete_branches:
            repo.attempt("branch", "-D", member.row.branch)
        db.flush()
    if integrated:
        names = ", ".join(o.name for o in outcomes if o.status == "integrated")
        task_ops.add_event(
            db, task, TaskEventKind.INTEGRATED, f"{mode}: {names}" + (" (pushed)" if push else "")
        )
    return IntegrationResult(group_id=group, repos=outcomes, stopped=stopped, integrated=integrated)


def _push(repo: Repo, base: str, item: RepoOutcome) -> bool:
    """Pushing is a courtesy of «integrar y subir»: its failure does not undo the integration."""
    try:
        target = remote.default_remote(repo, base)
        repo.run("push", target, base, timeout=300, interactive=True)
        return True
    except GitxError as error:
        item.error_code, item.message = error.code, error.message
        return False


# ------------------------------------------------------------------------------ undo
def last_group(db: Session, task: Task, project: Project) -> list[GitOperation]:
    """The operations of the newest integration of the task, not undone yet."""
    ids = [m.repo.id for m in _members(db, task, project)]
    if not ids:
        return []
    rows = list(
        db.scalars(
            select(GitOperation)
            .where(
                GitOperation.repo_id.in_(ids),
                GitOperation.kind == "integrate",
                GitOperation.label.startswith(f"{LABEL_PREFIX}{task.code} "),
                GitOperation.undone_at.is_(None),
            )
            .order_by(GitOperation.at.desc())
        )
    )
    if not rows:
        return []
    return [row for row in rows if row.group_id == rows[0].group_id]


def undo(db: Session, task: Task, project: Project) -> int:
    """Puts back every base the last integration moved (refuses if any moved since)."""
    operations = last_group(db, task, project)
    if not operations:
        raise GitxError("no_operation", "this task has no integration to undo", status=404)
    members = {m.repo.id: m for m in _members(db, task, project)}
    repo_of = {
        op.repo_id: Repo(members[op.repo_id].repo.path)
        for op in operations
        if op.repo_id in members
    }
    # Nothing is touched unless every repository can go back.
    for op in operations:
        reason = oplog.blocker(op, repo_of[op.repo_id])
        if reason:
            raise GitxError(reason, f"the integration cannot be undone now ({reason})", status=409)
    for op in operations:
        oplog.undo(op, repo_of[op.repo_id])
        member = members[op.repo_id]
        member.row.integrated_at = member.row.integrated_sha = None
    return len(operations)


# ------------------------------------------------------------------------------ resolving
def _resolution_folder(task: Task, project: Project, name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name) or "repo"
    return root_for(project) / f"merge-{task.code}" / safe


def prepare_resolution(db: Session, task: Task, project: Project, repo_id: str) -> Resolution:
    """A worktree on the task's branch with the base merged in, left with its conflicts for the
    person to resolve. When it is done, `finish_resolution` commits and removes it."""
    member = next((m for m in _members(db, task, project) if m.repo.id == repo_id), None)
    if member is None or not member.base:
        raise GitxError("repo_not_found", "the task has no branch in that repository", status=404)
    repo = Repo(member.repo.path)
    folder = _resolution_folder(task, project, member.repo.name)
    if folder.is_dir():
        scratch = Repo(str(folder))
        return Resolution(
            repo_id=repo_id,
            name=member.repo.name,
            path=str(folder),
            conflicts=[f.path for f in read.status(scratch).conflicts],
        )
    if any(t.branch == member.row.branch for t in trees.worktrees(repo)):
        raise GitxError(
            "branch_checked_out", "the task's branch is checked out in another folder", status=409
        )
    folder.parent.mkdir(parents=True, exist_ok=True)
    with repo.write():
        repo.run("worktree", "add", str(folder), member.row.branch)
    result = merge.merge(Repo(str(folder)), member.base, "no_ff")
    if result.status != "conflicts":  # it merged: nothing to resolve
        trees.remove(repo, str(folder), force=True)
        shutil.rmtree(folder, ignore_errors=True)
        return Resolution(repo_id=repo_id, name=member.repo.name, path="", conflicts=[])
    return Resolution(
        repo_id=repo_id, name=member.repo.name, path=str(folder), conflicts=result.conflicts
    )


def finish_resolution(db: Session, task: Task, project: Project, repo_id: str) -> None:
    """Commits the resolved merge on the task's branch and removes the worktree."""
    member = next((m for m in _members(db, task, project) if m.repo.id == repo_id), None)
    if member is None:
        raise GitxError("repo_not_found", "the task has no branch in that repository", status=404)
    folder = _resolution_folder(task, project, member.repo.name)
    if not folder.is_dir():
        raise GitxError("no_operation", "there is no resolution in progress", status=404)
    scratch = Repo(str(folder))
    if merge.conflict_paths(scratch):
        raise GitxError("conflicts_unresolved", "there are files still in conflict", status=409)
    if read.operation_in_progress(scratch) == "merge":
        result = merge.proceed(scratch, "continue")
        if result.status == "conflicts":
            raise GitxError("conflicts_unresolved", "there are files still in conflict", status=409)
    trees.remove(Repo(member.repo.path), str(folder), force=True)
    shutil.rmtree(folder, ignore_errors=True)


# ------------------------------------------------------------------------------ resolver task
RESOLVE_PROMPT = """Integrar la tarea {code} («{title}») en su rama base da conflictos.

Tu trabajo, en cada repositorio de tu carpeta de trabajo (estás en la rama `{branch}` de {code}):
1. Trae la base a la rama con `git merge <base>`.
2. Resuelve los conflictos de los ficheros listados, conservando lo que quiso hacer cada lado.
3. Ejecuta las pruebas del proyecto si las hay.
4. Haz commit del merge. No toques la rama base ni hagas push.

Repositorios y ficheros en conflicto:
{repos}
"""


def resolution_task(
    db: Session,
    task: Task,
    project: Project,
    agent_id: str,
    checked: IntegrationCheck | None = None,
) -> Task:
    """A task for an agent to resolve the conflicts of integrating `task`: it works on the same
    branches, only in the repositories with conflicts."""
    checked = checked or check(db, task, project)
    conflicting = [c for c in checked.repos if c.state == "conflicts"]
    if not conflicting:
        raise GitxError("no_conflicts", "integrating this task has no conflicts", status=409)
    listing = "\n".join(
        f"- {c.name} (base `{c.base}`): " + ", ".join(f"`{f}`" for f in c.conflicts)
        for c in conflicting
    )
    created = task_ops.create_task(
        db,
        project,
        f"Resolver conflictos de {task.code}",
        RESOLVE_PROMPT.format(
            code=task.code, title=task.title, branch=task.branch or "", repos=listing
        ),
        agent_id=agent_id,
    )
    created.resolves_task_id = task.id
    return created


def resolving_repos(db: Session, task: Task, project: Project) -> list[str] | None:
    """For a resolver task: the repositories (ids) of the original with conflicts, or None when
    the task resolves nothing."""
    if not task.resolves_task_id:
        return None
    original = db.get(Task, task.resolves_task_id)
    if original is None:
        return None
    checked = check(db, original, project)
    wanted = [c.repo_id for c in checked.repos if c.state == "conflicts"]
    return wanted or [c.repo_id for c in checked.repos if c.ahead]


# ------------------------------------------------------------------------------ on approve
def after_approval(db: Session, task: Task, project: Project) -> None:
    """What the project does when a task is approved (`on_approve`). A failure or a conflict does
    not change the task: it leaves a request with the reason."""
    if task.resolves_task_id:
        original = db.get(Task, task.resolves_task_id)
        if original is not None:
            inbox.create(
                db,
                InboxKind.DELIVERY,
                f"Integrar {original.code}",
                f"{task.code} resolvió los conflictos: integra {original.code} desde su tarea.",
                task=original,
            )
        return
    if project.on_approve not in ("integrate", "integrate_push"):
        return
    result = run(
        db,
        task,
        project,
        project.integration_mode,  # type: ignore[arg-type]
        push=project.on_approve == "integrate_push",
    )
    problems = [
        o for o in result.repos if o.status in ("conflicts", "blocked", "failed", "missing")
    ]
    if not problems:
        return
    reasons = []
    for item in problems:
        if item.status == "conflicts":
            reasons.append(f"conflictos en {item.name}: {len(item.conflicts)} ficheros")
        elif item.status == "blocked":
            reasons.append(f"{item.name} tiene cambios sin commit en la rama base")
        else:
            reasons.append(f"{item.name}: {item.message or item.error_code}")
    inbox.create(
        db,
        InboxKind.DELIVERY,
        f"No se pudo integrar {task.code}",
        "No se pudo integrar: " + "; ".join(reasons),
        task=task,
    )
