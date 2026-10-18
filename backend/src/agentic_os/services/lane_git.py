"""Bringing the git branches of a task's lanes together where the lanes meet (phase 13,
ADR 0020).

In a project in worktree mode every lane works on a branch of its own (`agentic/T-142-backend`)
that starts from its parent's (`agentic/T-142`). At the join each lane's branch is merged into
the parent's, one merge commit per lane, with the machinery that integrates a task into its base
(phase 12): no folder is needed, and the parent's worktree, if it is open, follows the branch.

A lane that would conflict is left alone and reported; the parent waits (`join_conflict`) and
the conflicts are resolved in the editor (a scratch worktree on the parent's branch) or by an
agent (a task that works on that same branch). Either way the join is tried again afterwards.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import (
    FINISHED_TASK_STATUSES,
    Project,
    ProjectRepo,
    Task,
    TaskEventKind,
    TaskRepo,
    TaskStatus,
)
from agentic_os.services import repos
from agentic_os.services import tasks as task_ops
from agentic_os.services.gitx import merge, read, trees
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo
from agentic_os.services.integration import (
    Resolution,
    _count,
    _exists,
    _integrate_one,
    _Member,
    _merge_tree,
)
from agentic_os.services.worktrees import Worktrees, root_for


@dataclass(frozen=True)
class Clash:
    """A lane whose work cannot be merged into its parent's branch in one repository."""

    repo_id: str
    name: str
    lane: str
    files: list[str]


@dataclass(frozen=True)
class _Pair:
    parent_row: TaskRepo
    repo: ProjectRepo
    lane: Task
    lane_row: TaskRepo


def _pairs(db: Session, parent: Task, lanes: list[Task]) -> Iterator[_Pair]:
    """Every (repository, lane) the lane has a branch in, in the project's repository order."""
    project = db.get(Project, parent.project_id)
    order = {r.id: i for i, r in enumerate(repos.ordered(db, project))} if project else {}
    rows = sorted(
        db.scalars(select(TaskRepo).where(TaskRepo.task_id == parent.id)),
        key=lambda r: order.get(r.repo_id, 0),
    )
    for prow in rows:
        repo = db.get(ProjectRepo, prow.repo_id)
        if repo is None or repo.missing or not Path(repo.path).is_dir():
            continue
        for lane in lanes:
            lrow = db.scalar(
                select(TaskRepo).where(
                    TaskRepo.task_id == lane.id, TaskRepo.repo_id == prow.repo_id
                )
            )
            if lrow is not None:
                yield _Pair(prow, repo, lane, lrow)


def _loose_work(db: Session, task: Task, project: Project) -> None:
    """Commits what the task's agents left uncommitted in its folders: only commits travel."""
    rows = list(db.scalars(select(TaskRepo).where(TaskRepo.task_id == task.id)))
    everyone = repos.ordered(db, project)
    for row in rows:
        path = row.worktree_path or ""
        repo = db.get(ProjectRepo, row.repo_id)
        if repo is None or not path or not Path(path).is_dir():
            continue
        nested = [str(Path(n)) for n in repos.nested_paths(everyone, repo) if len(rows) > 1]
        with contextlib.suppress(Exception):
            Worktrees._commit_leftovers(task, path, nested)


def _ahead(pair: _Pair) -> int:
    repo = Repo(pair.repo.path)
    if not _exists(repo, pair.lane_row.branch) or not _exists(repo, pair.parent_row.branch):
        return 0
    return _count(repo, f"{pair.parent_row.branch}..{pair.lane_row.branch}")


def clashes(db: Session, parent: Task, lanes: list[Task]) -> list[Clash]:
    """What cannot be merged today, without changing anything."""
    found: list[Clash] = []
    for pair in _pairs(db, parent, lanes):
        if not _ahead(pair):
            continue
        repo = Repo(pair.repo.path)
        _, files = _merge_tree(repo, pair.parent_row.branch, pair.lane_row.branch)
        if files:
            found.append(Clash(pair.repo.id, pair.repo.name, pair.lane.lane_key, files))
    return found


def integrate(db: Session, parent: Task, lanes: list[Task]) -> str | None:
    """Merges each lane's branch into the parent's, in every repository. Returns why it could
    not (a text for the person), or None when everything is in. What already merged stays
    merged: trying again only does what is left."""
    project = db.get(Project, parent.project_id)
    if project is None or not db.scalar(select(TaskRepo.id).where(TaskRepo.task_id == parent.id)):
        return None  # a direct folder, or a project without git: the lanes shared the folder
    _loose_work(db, parent, project)
    for lane in lanes:
        _loose_work(db, lane, project)
    problems: list[str] = []
    for pair in _pairs(db, parent, lanes):
        if not _ahead(pair):
            continue
        member = _Member(pair.lane_row, pair.repo, pair.parent_row.branch)
        scratch = root_for(project) / f"join-{pair.lane.ref_name}"
        try:
            outcome, _, files = _integrate_one(pair.lane, member, "merge", scratch)
        except GitxError as error:
            problems.append(f"{pair.repo.name}: {error}")
            continue
        if outcome == "conflicts":
            problems.append(f"{pair.repo.name} · {pair.lane.lane_key}: " + ", ".join(files))
            continue
        task_ops.add_event(
            db,
            parent,
            TaskEventKind.WORKSPACE,
            f"{pair.lane.lane_key} → {pair.parent_row.branch} ({pair.repo.name})",
        )
    return "\n".join(problems) or None


# ------------------------------------------------------------------------------ resolving
def _editor_folder(project: Project, parent: Task, name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name) or "repo"
    return root_for(project) / f"join-{parent.ref_name}" / safe


def _merge_lanes(folder: Path, branches: list[str]) -> list[str]:
    """Merges the lanes still apart into the branch checked out in `folder`; stops at the first
    that conflicts and returns its files."""
    scratch = Repo(str(folder))
    for branch in branches:
        if _count(scratch, f"HEAD..{branch}") == 0:
            continue
        result = merge.merge(scratch, branch, "no_ff")
        if result.status == "conflicts":
            return result.conflicts or ["?"]
    return []


def _lane_branches(db: Session, parent: Task, repo_id: str) -> list[str]:
    from agentic_os.services import lanes as lane_ops

    found: list[str] = []
    for lane in lane_ops.lanes_of(db, parent, parent.stage_id):
        row = db.scalar(
            select(TaskRepo).where(TaskRepo.task_id == lane.id, TaskRepo.repo_id == repo_id)
        )
        if row is not None and lane.status == TaskStatus.DONE:
            found.append(row.branch)
    return found


def prepare_editor(db: Session, parent: Task, project: Project) -> list[Resolution]:
    """Scratch worktrees on the parent's branch with the lanes merged in, left with the
    conflicts for the person to resolve. The parent's own worktree must have been released."""
    result: list[Resolution] = []
    for prow in db.scalars(select(TaskRepo).where(TaskRepo.task_id == parent.id)):
        prepo = db.get(ProjectRepo, prow.repo_id)
        if prepo is None or prepo.missing:
            continue
        folder = _editor_folder(project, parent, prepo.name)
        repo = Repo(prepo.path)
        if not folder.is_dir():
            if not _exists(repo, prow.branch):
                continue
            folder.parent.mkdir(parents=True, exist_ok=True)
            with repo.write():
                repo.run("worktree", "add", str(folder), prow.branch)
            files = _merge_lanes(folder, _lane_branches(db, parent, prow.repo_id))
        else:
            files = [f.path for f in read.status(Repo(str(folder))).conflicts]
        if files:
            result.append(
                Resolution(repo_id=prepo.id, name=prepo.name, path=str(folder), conflicts=files)
            )
        else:
            _drop_scratch(repo, folder)
    return result


def finish_editor(db: Session, parent: Task, project: Project, repo_id: str) -> list[str]:
    """Commits the merge the person resolved and goes on with the lanes left. Returns the files
    of the next conflict, or [] when this repository is done (its scratch folder is removed)."""
    prepo = db.get(ProjectRepo, repo_id)
    if prepo is None:
        raise GitxError("repo_not_found", "the task has no branch in that repository", status=404)
    folder = _editor_folder(project, parent, prepo.name)
    if not folder.is_dir():
        raise GitxError("no_operation", "there is no resolution in progress", status=404)
    scratch = Repo(str(folder))
    if merge.conflict_paths(scratch):
        raise GitxError("conflicts_unresolved", "there are files still in conflict", status=409)
    if read.operation_in_progress(scratch) == "merge":
        outcome = merge.proceed(scratch, "continue")
        if outcome.status == "conflicts":
            raise GitxError("conflicts_unresolved", "there are files still in conflict", status=409)
    files = _merge_lanes(folder, _lane_branches(db, parent, repo_id))
    if not files:
        _drop_scratch(Repo(prepo.path), folder)
    return files


def _drop_scratch(repo: Repo, folder: Path) -> None:
    with contextlib.suppress(GitxError):
        trees.remove(repo, str(folder), force=True)
    shutil.rmtree(folder, ignore_errors=True)
    with contextlib.suppress(OSError):
        folder.parent.rmdir()


RESOLVE_PROMPT = """Las ramas de las vías de {code} («{title}») dan conflictos al unirlas.

Tu trabajo, en cada repositorio de tu carpeta de trabajo (estás en la rama `{branch}` de {code}):
1. Trae a tu rama el trabajo de cada vía con `git merge <rama de la vía>`.
2. Resuelve los conflictos de los ficheros listados, conservando lo que quiso hacer cada vía.
3. Ejecuta las pruebas del proyecto si las hay.
4. Haz commit del merge. No toques otras ramas ni hagas push.

Repositorios, vías y ficheros en conflicto:
{repos}
"""


def resolution_task(
    db: Session, parent: Task, project: Project, agent_id: str, found: list[Clash]
) -> Task:
    """A task for an agent to resolve the conflicts of the join: it works on the parent's
    branch, only in the repositories that clash."""
    open_one = db.scalar(
        select(Task.id).where(
            Task.resolves_task_id == parent.id,
            Task.status.notin_([s.value for s in FINISHED_TASK_STATUSES]),
        )
    )
    if open_one is not None:
        raise ApiError(409, "resolution_exists", "an agent is already resolving this join")
    listing = "\n".join(
        f"- {c.name}: vía `agentic/{_lane_ref(parent, c.lane)}` → "
        + ", ".join(f"`{f}`" for f in c.files)
        for c in found
    )
    created = task_ops.create_task(
        db,
        project,
        f"Resolver conflictos de {parent.code}",
        RESOLVE_PROMPT.format(
            code=parent.code, title=parent.title, branch=parent.branch or "", repos=listing
        ),
        agent_id=agent_id,
        standalone=True,
    )
    created.resolves_task_id = parent.id
    return created


def _lane_ref(parent: Task, lane_key: str) -> str:
    return f"T-{parent.number}-{lane_key.replace('.', '-')}"
