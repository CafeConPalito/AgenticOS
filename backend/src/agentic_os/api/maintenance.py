"""Cleanup (phase 08): task branches and the retention of the runs' terminal logs; snapshots of
the runs' folders (phase 11)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api import settings as settings_api
from agentic_os.api.projects import get_project_or_404
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.models import Project
from agentic_os.services import git, maintenance

router = APIRouter(tags=["maintenance"])
DbSession = Annotated[Session, Depends(get_session)]


class BranchRead(BaseModel):
    name: str
    task_id: str | None
    task_code: str | None
    task_status: str | None
    merged: bool
    last_commit: str
    in_use: bool
    repo_id: str | None = None
    repo_name: str = ""


class ProjectBranches(BaseModel):
    project_id: str
    project_name: str
    branches: list[BranchRead]
    # git failed for this project (the others are still listed).
    error: str | None = None


class BranchDelete(BaseModel):
    project_id: str
    branches: list[str] = Field(min_length=1)
    force: bool = False
    # Which repository, when the project has several with the same branch name.
    repo_id: str | None = None


class BranchesDeleted(BaseModel):
    deleted: list[str]
    # Branches git could not delete, with its message (the others are deleted).
    failed: dict[str, str] = {}


class MaintenanceSettings(BaseModel):
    # Days a finished run keeps its terminal log; null: forever.
    log_retention_days: int | None = Field(default=None, ge=1, le=3650)


class ProjectSnapshotsRead(BaseModel):
    project_id: str
    project_name: str
    runs: int


class SnapshotsDeleted(BaseModel):
    runs: int


class LogsCleaned(BaseModel):
    runs: int
    freed_bytes: int


@router.get("/maintenance/branches")
def list_branches(db: DbSession) -> list[ProjectBranches]:
    result = []
    projects = db.scalars(
        select(Project).where(Project.workspace_id == DEFAULT_WORKSPACE).order_by(Project.name)
    )
    for project in projects:
        try:
            branches = maintenance.task_branches(db, project)
            error = None
        except git.GitError as failure:
            branches, error = [], str(failure)
        if branches or error:
            result.append(
                ProjectBranches(
                    project_id=project.id,
                    project_name=project.name,
                    branches=[BranchRead(**vars(b)) for b in branches],
                    error=error,
                )
            )
    return result


@router.post("/maintenance/branches/delete")
def delete_branches(payload: BranchDelete, db: DbSession) -> BranchesDeleted:
    project = get_project_or_404(db, payload.project_id)
    deleted, failed = maintenance.delete_branches(
        db, project, payload.branches, payload.force, payload.repo_id
    )
    return BranchesDeleted(deleted=deleted, failed=failed)


@router.get("/maintenance/snapshots")
def list_snapshots(db: DbSession) -> list[ProjectSnapshotsRead]:
    return [ProjectSnapshotsRead(**vars(item)) for item in maintenance.snapshot_counts(db)]


@router.post("/maintenance/snapshots/{project_id}/delete")
def delete_snapshots(project_id: str, db: DbSession) -> SnapshotsDeleted:
    project = get_project_or_404(db, project_id)
    return SnapshotsDeleted(runs=maintenance.delete_project_snapshots(db, project))


@router.get("/settings/maintenance")
def get_maintenance(db: DbSession) -> MaintenanceSettings:
    return MaintenanceSettings(log_retention_days=maintenance.retention_days(db))


@router.put("/settings/maintenance")
def put_maintenance(payload: MaintenanceSettings, db: DbSession) -> MaintenanceSettings:
    maintenance.set_retention_days(db, payload.log_retention_days)
    return payload


@router.post("/maintenance/logs/cleanup")
def clean_logs(request: Request, db: DbSession) -> LogsCleaned:
    runs_dir = Path(request.app.state.settings.data_dir) / "runs"
    runs, freed = maintenance.purge_logs(db, runs_dir, maintenance.retention_days(db))
    settings_api.forget_sizes()
    return LogsCleaned(runs=runs, freed_bytes=freed)
