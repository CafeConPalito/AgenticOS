"""Integrating the branches of a task into their bases (phase 12, block 5)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentic_os.api.agents import _get as get_agent_row
from agentic_os.api.tasks import SchedulerDep, _get, read_task
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.models import Project, TaskRepo
from agentic_os.schemas.task import TaskRead
from agentic_os.services import integration
from agentic_os.services.gitx.errors import GitxError

router = APIRouter(tags=["integration"])
DbSession = Annotated[Session, Depends(get_session)]


class IntegrateBody(BaseModel):
    # Default: the project's way of integrating.
    mode: Literal["merge", "squash", "rebase"] | None = None
    push: bool = False
    delete_branches: bool = False


class ResolveBody(BaseModel):
    agent_id: str = Field(min_length=1)


class RepoBody(BaseModel):
    repo_id: str = Field(min_length=1)


def _project(db: Session, task) -> Project:
    project = db.get(Project, task.project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "the task's project is gone")
    return project


def _changed(request: Request, repo_ids: list[str]) -> None:
    events = request.app.state.git_events
    for repo_id in repo_ids:
        events.changed(repo_id)


@router.get("/tasks/{task_id}/integration")
def get_integration(task_id: str, db: DbSession) -> integration.IntegrationCheck:
    """What integrating the task would do (conflicts, folders in the way), changing nothing."""
    task = _get(db, task_id)
    return integration.check(db, task, _project(db, task))


@router.post("/tasks/{task_id}/integrate")
def integrate(
    task_id: str, body: IntegrateBody, db: DbSession, request: Request
) -> integration.IntegrationResult:
    task = _get(db, task_id)
    project = _project(db, task)
    if not db.query(TaskRepo).filter(TaskRepo.task_id == task.id).count():
        raise ApiError(409, "no_branches", "this task has no branches to integrate")
    try:
        result = integration.run(
            db,
            task,
            project,
            body.mode or project.integration_mode,  # type: ignore[arg-type]
            push=body.push,
            delete_branches=body.delete_branches,
        )
    except GitxError:
        db.commit()
        raise
    db.commit()
    _changed(request, [r.repo_id for r in result.repos])
    return result


@router.post("/tasks/{task_id}/integration/undo")
def undo_integration(task_id: str, db: DbSession, request: Request) -> dict[str, int]:
    """Puts back every base the last integration moved."""
    task = _get(db, task_id)
    project = _project(db, task)
    count = integration.undo(db, task, project)
    db.commit()
    _changed(request, [m.repo_id for m in db.query(TaskRepo).filter(TaskRepo.task_id == task.id)])
    return {"undone": count}


@router.post("/tasks/{task_id}/integration/resolution")
def start_resolution(
    task_id: str, body: RepoBody, db: DbSession, request: Request
) -> integration.Resolution:
    """A worktree on the task's branch with the base merged in, to resolve its conflicts."""
    task = _get(db, task_id)
    result = integration.prepare_resolution(db, task, _project(db, task), body.repo_id)
    _changed(request, [body.repo_id])
    return result


@router.post(
    "/tasks/{task_id}/integration/resolution/finish", status_code=status.HTTP_204_NO_CONTENT
)
def finish_resolution(task_id: str, body: RepoBody, db: DbSession, request: Request) -> None:
    task = _get(db, task_id)
    integration.finish_resolution(db, task, _project(db, task), body.repo_id)
    _changed(request, [body.repo_id])


@router.post("/tasks/{task_id}/resolve-conflicts", status_code=status.HTTP_201_CREATED)
def resolve_conflicts(
    task_id: str, body: ResolveBody, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    """A task for an agent to bring the base into the task's branches and resolve the conflicts."""
    task = _get(db, task_id)
    get_agent_row(db, body.agent_id)
    created = integration.resolution_task(db, task, _project(db, task), body.agent_id)
    db.commit()
    scheduler.poke()
    return read_task(db, created)
