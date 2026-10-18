"""What a run did with git, and undoing it (phase 12, block 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.runs import _get
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.models import ProjectRepo, RunRepo
from agentic_os.services.gitx import activity as git_activity
from agentic_os.services.gitx.runner import Repo

router = APIRouter(tags=["git"])
DbSession = Annotated[Session, Depends(get_session)]


class RunRepoGit(BaseModel):
    repo_id: str | None
    name: str
    path: str
    # None: nothing was recorded (a run from before git was tracked, or without snapshots).
    activity: git_activity.Activity | None = None
    # Something the person could undo: local branches the run created or moved.
    can_undo: bool = False
    # What the run pushed: undoing never touches it.
    pushed: bool = False


class UndoBody(BaseModel):
    confirm: bool = False


class UndoReport(BaseModel):
    repos: dict[str, git_activity.UndoResult]


def _rows(db: Session, run_id: str) -> list[RunRepo]:
    return list(
        db.scalars(select(RunRepo).where(RunRepo.run_id == run_id).order_by(RunRepo.repo_name))
    )


def _read(row: RunRepo) -> RunRepoGit:
    found = git_activity.Activity.model_validate(row.activity) if row.activity else None
    return RunRepoGit(
        repo_id=row.repo_id,
        name=row.repo_name,
        path=row.path,
        activity=found,
        can_undo=bool(found and found.branches and not found.undone),
        pushed=bool(found and git_activity.pushed(found)),
    )


@router.get("/runs/{run_id}/git")
def run_git(run_id: str, db: DbSession) -> list[RunRepoGit]:
    """What the run did with git, repository by repository."""
    run = _get(db, run_id)
    return [_read(row) for row in _rows(db, run.id)]


@router.post("/runs/{run_id}/git/undo")
def undo_run_git(run_id: str, body: UndoBody, db: DbSession, request: Request) -> UndoReport:
    """Puts back the local branches the run moved (and deletes the ones it created). Needs
    `confirm`. What was pushed stays as it is."""
    run = _get(db, run_id)
    if not body.confirm:
        raise ApiError(428, "confirmation_required", "undoing what a run did moves branches back")
    pending: list[tuple[RunRepo, ProjectRepo, git_activity.Activity]] = []
    for row in _rows(db, run.id):
        found = git_activity.Activity.model_validate(row.activity) if row.activity else None
        project_repo = db.get(ProjectRepo, row.repo_id) if row.repo_id else None
        if found is None or not found.branches or found.undone or project_repo is None:
            continue
        # Every repository has to be reachable before any is touched: half an undo is worse.
        if project_repo.missing or not Path(project_repo.path).is_dir():
            raise ApiError(409, "repo_missing", "the repository folder is gone", "repo_id")
        pending.append((row, project_repo, found))
    reports: dict[str, git_activity.UndoResult] = {}
    for row, project_repo, found in pending:
        result = git_activity.undo(db, project_repo, Repo(project_repo.path), found)
        # Done once every branch it could move is back; a skipped one stays as a report.
        found.undone = all(item.result != "skipped" for item in result.items)
        row.activity = found.model_dump()
        reports[project_repo.id] = result
        request.app.state.git_events.changed(project_repo.id)
    db.commit()
    if not reports:
        raise ApiError(409, "nothing_to_undo", "this run left nothing that can be undone")
    return UndoReport(repos=reports)
