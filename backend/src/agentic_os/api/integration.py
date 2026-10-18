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
from agentic_os.models import Project, TaskRepo, TaskStatus, WaitingReason
from agentic_os.schemas.task import ClashRead, TaskRead
from agentic_os.services import integration, lane_git
from agentic_os.services import lanes as lane_ops
from agentic_os.services import tasks as task_ops
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


# ------------------------------------------------------------- the join of a forked task
def _joining(db: Session, task_id: str):
    """The task, which has to be waiting because its lanes' branches clash."""
    task = _get(db, task_id)
    if task.status != TaskStatus.WAITING_HUMAN or task.waiting_reason != (
        WaitingReason.JOIN_CONFLICT
    ):
        raise ApiError(409, "task_status", "the task is not waiting to join its branches", "status")
    return task


@router.get("/tasks/{task_id}/join")
def get_join(task_id: str, db: DbSession) -> list[ClashRead]:
    """What keeps the lanes of the task from being merged (changing nothing)."""
    task = _get(db, task_id)
    found = lane_git.clashes(db, task, lane_ops.lanes_of(db, task, task.stage_id))
    return [ClashRead(repo_id=c.repo_id, name=c.name, lane=c.lane, files=c.files) for c in found]


@router.post("/tasks/{task_id}/join/editor")
def start_join_editor(
    task_id: str, db: DbSession, scheduler: SchedulerDep
) -> list[integration.Resolution]:
    """Scratch worktrees on the task's branch with its lanes merged in, left with their
    conflicts to resolve (the task's own worktree is closed first: the branch is free)."""
    task = _joining(db, task_id)
    project = _project(db, task)
    scheduler.release_workspace(db, task, project)
    result = lane_git.prepare_editor(db, task, project)
    db.commit()
    return result


@router.post("/tasks/{task_id}/join/editor/finish")
def finish_join_editor(
    task_id: str, body: RepoBody, db: DbSession, scheduler: SchedulerDep
) -> dict[str, object]:
    """Commits what the person resolved in a repository. When nothing is left, the join
    goes on by itself."""
    task = _joining(db, task_id)
    files = lane_git.finish_editor(db, task, _project(db, task), body.repo_id)
    joined = False
    if not files:
        left = lane_git.clashes(db, task, lane_ops.lanes_of(db, task, task.stage_id))
        if not left:
            task_ops.retry(db, task)
            joined = True
            if task.status == TaskStatus.DONE:
                scheduler.release_finished(db, task)
    db.commit()
    scheduler.poke()
    return {"conflicts": files, "joined": joined}


@router.post("/tasks/{task_id}/join/agent", status_code=status.HTTP_201_CREATED)
def resolve_join_with_agent(
    task_id: str, body: ResolveBody, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    """A task for an agent to merge the lanes' branches into the task's and resolve the
    conflicts; when it is approved the join goes on."""
    task = _joining(db, task_id)
    get_agent_row(db, body.agent_id)
    project = _project(db, task)
    found = lane_git.clashes(db, task, lane_ops.lanes_of(db, task, task.stage_id))
    if not found:
        raise ApiError(409, "no_conflicts", "joining these branches has no conflicts")
    scheduler.release_workspace(db, task, project)
    created = lane_git.resolution_task(db, task, project, body.agent_id, found)
    db.commit()
    scheduler.poke()
    return read_task(db, created)


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
