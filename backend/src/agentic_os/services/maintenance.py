"""Cleanup (phase 08): the task branches left in the projects' repositories and the old
terminal logs of finished runs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import ACTIVE_STATUSES, AppState, Project, Run, Task, TaskStatus
from agentic_os.models.app_state import LOG_RETENTION
from agentic_os.services import git

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
    merged: bool  # into the project's base branch
    last_commit: str  # ISO date
    in_use: bool  # its task is still open, or a worktree has it checked out

    @property
    def deletable(self) -> bool:
        return not self.in_use


def _base_branch(project: Project) -> str | None:
    if project.base_branch:
        return project.base_branch
    info = git.detect(project.path)
    return info.branch if info else None


def _checked_out(project: Project) -> set[str]:
    """Branches a worktree of the repository has checked out."""
    out = git.run(project.path, "worktree", "list", "--porcelain")
    return {
        line.removeprefix("branch refs/heads/")
        for line in out.splitlines()
        if line.startswith("branch refs/heads/")
    }


def task_branches(db: Session, project: Project) -> list[TaskBranch]:
    """The `agentic/T-n` branches of a project (empty without git or without branches)."""
    info = git.detect(project.path)
    if info is None or not info.is_repo:
        return []
    out = git.run(
        project.path,
        "for-each-ref",
        "--format=%(refname:short)%09%(committerdate:iso-strict)",
        f"refs/heads/{BRANCH_PREFIX}",
    )
    rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
    if not rows:
        return []
    base = _base_branch(project)
    merged = set()
    if base:
        merged = {
            line.strip().lstrip("*+ ").strip()
            for line in git.run(project.path, "branch", "--merged", base).splitlines()
        }
    checked_out = _checked_out(project)
    tasks = {
        task.branch: task
        for task in db.scalars(
            select(Task).where(Task.project_id == project.id, Task.branch.is_not(None))
        )
    }
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
            )
        )
    return sorted(branches, key=lambda b: b.last_commit, reverse=True)


def delete_branches(
    db: Session, project: Project, names: list[str], force: bool
) -> tuple[list[str], dict[str, str]]:
    """Deletes task branches. Without `force` only those merged into the base branch; never one
    still in use. Returns (deleted, {branch: why it could not be deleted})."""
    try:
        known = {b.name: b for b in task_branches(db, project)}
    except git.GitError as error:
        raise ApiError(409, "git_failed", str(error), "project_id") from error
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
        # `-D`: whether it is merged was checked above against the project's base branch;
        # `git branch -d` would check it against whatever is checked out.
        try:
            git.run(project.path, "branch", "-D", name)
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
    db.commit()
    if runs:
        log.info("run_logs_purged", runs=purged, freed=freed, days=days)
    return purged, freed
