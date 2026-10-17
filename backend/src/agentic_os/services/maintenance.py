"""Cleanup (phase 08): the task branches left in the projects' repositories and the old
terminal logs of finished runs. Phase 11: the snapshots of the runs' folders go with their logs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    ACTIVE_STATUSES,
    AppState,
    Project,
    ProjectRepo,
    Run,
    RunRepo,
    Task,
    TaskRepo,
    TaskStatus,
)
from agentic_os.models.app_state import LOG_RETENTION
from agentic_os.services import git, repos, snapshots

log = structlog.get_logger(__name__)

BRANCH_PREFIX = "agentic/"
DEFAULT_RETENTION_DAYS = 90
CLOSED = (TaskStatus.DONE, TaskStatus.CANCELLED)


# ---------------------------------------------------------------- branches
@dataclass
class TaskBranch:
    name: str
    task_id: str | None
    task_code: str | None
    task_status: str | None
    merged: bool  # into the repository's base branch
    last_commit: str  # ISO date
    in_use: bool  # its task is still open, or a worktree has it checked out
    repo_id: str | None = None
    repo_name: str = ""

    @property
    def deletable(self) -> bool:
        return not self.in_use


def _base_branch(project: Project, repo: ProjectRepo) -> str | None:
    base = repos.base_of(project, repo)
    if base:
        return base
    info = git.detect(repo.path)
    return info.branch if info else None


def _checked_out(path: str) -> set[str]:
    """Branches a worktree of the repository has checked out."""
    out = git.run(path, "worktree", "list", "--porcelain")
    return {
        line.removeprefix("branch refs/heads/")
        for line in out.splitlines()
        if line.startswith("branch refs/heads/")
    }


def task_branches(db: Session, project: Project) -> list[TaskBranch]:
    """The `agentic/T-n` branches of a project's repositories (empty without git or without
    branches)."""
    result: list[TaskBranch] = []
    for repo in repos.ensure(db, project):
        if repo.missing:
            continue
        result += _repo_branches(db, project, repo)
    return sorted(result, key=lambda b: b.last_commit, reverse=True)


def _repo_branches(db: Session, project: Project, repo: ProjectRepo) -> list[TaskBranch]:
    info = git.detect(repo.path)
    if info is None or not info.is_repo:
        return []
    out = git.run(
        repo.path,
        "for-each-ref",
        "--format=%(refname:short)%09%(committerdate:iso-strict)",
        f"refs/heads/{BRANCH_PREFIX}",
    )
    rows = [line.split("	", 1) for line in out.splitlines() if "	" in line]
    if not rows:
        return []
    base = _base_branch(project, repo)
    merged = set()
    if base:
        merged = {
            line.strip().lstrip("*+ ").strip()
            for line in git.run(repo.path, "branch", "--merged", base).splitlines()
        }
    checked_out = _checked_out(repo.path)
    tasks = {
        row.branch: task
        for row, task in db.execute(
            select(TaskRepo, Task)
            .join(Task, Task.id == TaskRepo.task_id)
            .where(TaskRepo.repo_id == repo.id)
        )
    }
    for task in db.scalars(
        select(Task).where(Task.project_id == project.id, Task.branch.is_not(None))
    ):
        tasks.setdefault(task.branch or "", task)  # a task from before the repository rows
    branches = []
    for name, date in rows:
        task = tasks.get(name)
        open_task = task is not None and TaskStatus(task.status) not in CLOSED
        branches.append(
            TaskBranch(
                name=name,
                task_id=task.id if task else None,
                task_code=task.code if task else None,
                task_status=task.status if task else None,
                merged=name in merged,
                last_commit=date,
                in_use=open_task or name in checked_out,
                repo_id=repo.id,
                repo_name=repo.name,
            )
        )
    return branches


def delete_branches(
    db: Session,
    project: Project,
    names: list[str],
    force: bool,
    repo_id: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Deletes task branches. Without `force` only those merged into the base branch; never one
    still in use. `repo_id` says which repository when the project has several. Returns
    (deleted, {branch: why it could not be deleted})."""
    try:
        every = task_branches(db, project)
    except git.GitError as error:
        raise ApiError(409, "git_failed", str(error), "project_id") from error
    known: dict[str, TaskBranch] = {}
    for branch in every:
        if repo_id is not None and branch.repo_id != repo_id:
            continue
        if branch.name in known:
            raise ApiError(
                422, "repo_required", f"{branch.name} is in several repositories", "repo_id"
            )
        known[branch.name] = branch
    for name in names:
        branch = known.get(name)
        if branch is None:
            raise ApiError(404, "branch_not_found", f"{name} is not a task branch", "branches")
        if branch.in_use:
            raise ApiError(409, "branch_in_use", f"{name} is still in use", "branches")
        if not branch.merged and not force:
            raise ApiError(409, "branch_not_merged", f"{name} has unmerged work", "branches")
    deleted, failed = [], {}
    for name in names:
        repo = db.get(ProjectRepo, known[name].repo_id or "")
        if repo is None:
            failed[name] = "the repository is no longer in the project"
            continue
        # `-D`: whether it is merged was checked above against the repository's base branch;
        # `git branch -d` would check it against whatever is checked out.
        try:
            git.run(repo.path, "branch", "-D", name)
        except git.GitError as error:
            failed[name] = str(error)
            continue
        deleted.append(name)
        log.info("task_branch_deleted", project=project.name, branch=name, force=force)
    return deleted, failed


# ---------------------------------------------------------------- terminal logs
def retention_days(db: Session) -> int | None:
    """Days a finished run keeps its terminal log (None: forever)."""
    row = db.get(AppState, LOG_RETENTION)
    if row is None:
        return DEFAULT_RETENTION_DAYS
    try:
        days = json.loads(row.value).get("days")
    except (ValueError, AttributeError):
        return DEFAULT_RETENTION_DAYS
    return days if isinstance(days, int) and days > 0 else None


def set_retention_days(db: Session, days: int | None) -> None:
    row = db.get(AppState, LOG_RETENTION) or AppState(key=LOG_RETENTION)
    row.value = json.dumps({"days": days})
    db.add(row)
    db.commit()


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def purge_logs(db: Session, runs_dir: Path, days: int | None) -> tuple[int, int]:
    """Deletes the terminal logs (and run files) of runs that ended more than `days` ago.
    The runs and their usage stay. Returns (runs purged, bytes freed)."""
    if days is None:
        return 0, 0
    cutoff = utcnow() - timedelta(days=days)
    runs = list(
        db.scalars(
            select(Run).where(
                Run.status.not_in([s.value for s in ACTIVE_STATUSES]),
                Run.log_purged.is_(False),
                Run.ended_at.is_not(None),
                Run.ended_at < cutoff,
            )
        )
    )
    freed, purged = 0, 0
    purged_runs: list[Run] = []
    for run in runs:
        complete = True
        for path in (Path(run.log_path) if run.log_path else None, runs_dir / run.id):
            if path is None or not path.exists():
                continue
            try:
                size = _size(path)
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                freed += size
            except OSError as error:  # locked (antivirus, indexer): tried again next time
                complete = False
                log.warning("could not delete a run's log", run_id=run.id, error=str(error))
        if complete:
            run.log_purged = True
            purged += 1
            purged_runs.append(run)
    _drop_snapshots(db, purged_runs)
    db.commit()
    if runs:
        log.info("run_logs_purged", runs=purged, freed=freed, days=days)
    return purged, freed


# ---------------------------------------------------------------- snapshots (phase 11)
def _git_dir(db: Session, row: RunRepo) -> str | None:
    repo = db.get(ProjectRepo, row.repo_id) if row.repo_id else None
    for candidate in (repo.path if repo else None, row.path):
        if candidate and Path(candidate).is_dir():
            return candidate
    return None


def _drop_rows(db: Session, rows: list[RunRepo]) -> None:
    """Deletes the snapshot refs of these run/repository rows and forgets their shas."""
    by_dir: dict[str, list[str]] = {}
    for row in rows:
        folder = _git_dir(db, row)
        if folder is not None:
            by_dir.setdefault(folder, []).append(row.run_id)
    for folder, run_ids in by_dir.items():
        snapshots.delete_runs(folder, sorted(set(run_ids)))
    for row in rows:
        row.snapshot_start = row.snapshot_end = None


def _drop_snapshots(db: Session, runs: list[Run]) -> None:
    """Deletes the snapshot refs of these runs and forgets their shas. The +/- summary of each
    run stays, but its diff is gone («No hay datos de cambios»)."""
    if not runs:
        return
    rows = db.scalars(
        select(RunRepo).where(
            RunRepo.run_id.in_([run.id for run in runs]),
            or_(RunRepo.snapshot_start.is_not(None), RunRepo.snapshot_end.is_not(None)),
        )
    )
    _drop_rows(db, list(rows))


@dataclass
class ProjectSnapshots:
    project_id: str
    project_name: str
    runs: int  # runs that still have snapshots in the project's repositories


def _rows_with_snapshots(db: Session, project: Project) -> list[RunRepo]:
    return list(
        db.scalars(
            select(RunRepo)
            .join(Run, Run.id == RunRepo.run_id)
            .where(
                Run.project_id == project.id,
                or_(RunRepo.snapshot_start.is_not(None), RunRepo.snapshot_end.is_not(None)),
            )
        )
    )


def snapshot_counts(db: Session) -> list[ProjectSnapshots]:
    """Projects whose runs still have snapshots. Counted from the database: two projects may
    share one repository, and each one only owns its own runs' refs."""
    result = []
    for project in db.scalars(select(Project).order_by(Project.name)):
        runs = len({row.run_id for row in _rows_with_snapshots(db, project)})
        if runs:
            result.append(ProjectSnapshots(project.id, project.name, runs))
    return result


def forget_project_snapshots(db: Session, project: Project) -> int:
    """Deletes the snapshot refs of the project's own runs (never another project's, even in the
    same repository) and forgets their shas. The caller commits. Returns how many runs had them."""
    rows = _rows_with_snapshots(db, project)
    runs = len({row.run_id for row in rows})
    _drop_rows(db, rows)
    return runs


def delete_project_snapshots(db: Session, project: Project) -> int:
    """«Borrar instantáneas» of a project: the diffs of its runs are gone, their +/- stays."""
    runs = forget_project_snapshots(db, project)
    db.commit()
    return runs
