"""What the runs, the tasks and the agents changed in their folders (phase 11, ADR 0015)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.agents import _get as get_agent_row
from agentic_os.api.runs import _get as get_run_row
from agentic_os.api.tasks import _get as get_task_row
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.models import Run, Task
from agentic_os.schemas.changes import (
    AgentChangeRun,
    Changes,
    ChangesTotals,
    FileDiff,
    FileLines,
)
from agentic_os.services import changes as change_ops

router = APIRouter(tags=["changes"])
DbSession = Annotated[Session, Depends(get_session)]
Path = Annotated[str, Query(min_length=1, max_length=1000)]
OldPath = Annotated[str | None, Query(max_length=1000)]
Line = Annotated[int, Query(ge=1, le=10_000_000)]


@router.get("/runs/{run_id}/changes")
def run_changes(run_id: str, db: DbSession) -> Changes:
    return change_ops.changes(change_ops.run_range(db, get_run_row(db, run_id)))


@router.get("/runs/{run_id}/changes/file")
def run_file_diff(run_id: str, db: DbSession, path: Path, old_path: OldPath = None) -> FileDiff:
    rng = change_ops.run_range(db, get_run_row(db, run_id))
    return change_ops.file_diff(rng, path, old_path)


@router.get("/runs/{run_id}/changes/lines")
def run_file_lines(run_id: str, db: DbSession, path: Path, start: Line, end: Line) -> FileLines:
    rng = change_ops.run_range(db, get_run_row(db, run_id))
    return change_ops.file_lines(rng, path, start, end)


@router.get("/tasks/{task_id}/changes")
def task_changes(task_id: str, db: DbSession) -> Changes:
    return change_ops.changes(change_ops.task_range(db, get_task_row(db, task_id)))


@router.get("/tasks/{task_id}/changes/file")
def task_file_diff(task_id: str, db: DbSession, path: Path, old_path: OldPath = None) -> FileDiff:
    rng = change_ops.task_range(db, get_task_row(db, task_id))
    return change_ops.file_diff(rng, path, old_path)


@router.get("/tasks/{task_id}/changes/lines")
def task_file_lines(task_id: str, db: DbSession, path: Path, start: Line, end: Line) -> FileLines:
    rng = change_ops.task_range(db, get_task_row(db, task_id))
    return change_ops.file_lines(rng, path, start, end)


@router.get("/agents/{agent_id}/changes")
def agent_changes(
    agent_id: str,
    db: DbSession,
    project_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AgentChangeRun]:
    """The agent's latest runs that changed code (any with a +/- summary above zero files)."""
    agent = get_agent_row(db, agent_id)
    query = select(Run).where(
        Run.workspace_id == DEFAULT_WORKSPACE, Run.agent_id == agent.id, Run.changes_files > 0
    )
    if project_id:
        query = query.where(Run.project_id == project_id)
    runs = list(db.scalars(query.order_by(Run.created_at.desc()).limit(limit)))
    task_ids = {run.task_id for run in runs if run.task_id}
    tasks = {task.id: task for task in db.scalars(select(Task).where(Task.id.in_(task_ids)))}
    return [
        AgentChangeRun(
            run_id=run.id,
            project_id=run.project_id,
            project_name=run.project_name,
            task_id=run.task_id,
            task_code=tasks[run.task_id].code if run.task_id in tasks else None,
            task_title=tasks[run.task_id].title if run.task_id in tasks else None,
            started_at=run.started_at,
            created_at=run.created_at,
            totals=change_ops.run_totals(run) or ChangesTotals(),
        )
        for run in runs
    ]
