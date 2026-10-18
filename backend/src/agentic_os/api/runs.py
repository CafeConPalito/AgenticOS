import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from agentic_os.api.agents import _get as get_agent_row
from agentic_os.api.projects import get_project_or_404 as get_project_row
from agentic_os.api.terminal import serve_terminal
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    ACTIVE_STATUSES,
    CliAccount,
    Run,
    RunEvent,
    RunKind,
    RunStatus,
    Stage,
    Task,
)
from agentic_os.schemas.run import (
    ControlAction,
    ControlRequest,
    PermissionAnswer,
    RunCreate,
    RunEventRead,
    RunRead,
)
from agentic_os.schemas.usage import RunUsage
from agentic_os.services import accounts as account_ops
from agentic_os.services import changes as change_ops
from agentic_os.services.runs import resume as resume_ops
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.runs.session import SCROLLBACK_LIMIT, ControlConflict, RunSession
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.usage.reader import usage_payload

router = APIRouter(tags=["runs"])
DbSession = Annotated[Session, Depends(get_session)]


def get_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


Manager = Annotated[RunManager, Depends(get_manager)]


def _get(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("run")
    return run


def _read(run: Run, manager: RunManager, detail: bool = False) -> RunRead:
    """`detail`: also whether it can be resumed (a few queries: not for every row of a list)."""
    result = RunRead.model_validate(run)
    result.usage = RunUsage(**usage_payload(run))
    result.changes = change_ops.run_totals(run)
    db = object_session(run)
    account = db.get(CliAccount, run.account_id) if run.account_id and db is not None else None
    if account is not None:
        result.account_label = account_ops.display_name(account)
    if run.task_id and db is not None:
        task = db.get(Task, run.task_id)
        stage = db.get(Stage, run.stage_id) if run.stage_id else None
        result.task_code = task.code if task else None
        result.stage_name = stage.name if stage else None
    if detail and db is not None and RunStatus(run.status) in resume_ops.RESUMABLE:
        result.resumed_by_id = resume_ops.resumed_by(db, run.id)
        result.resumable = resume_ops.resumable(db, run)
    session = manager.get(run.id)
    if session is not None and session.alive:
        result.controller = session.controller
        result.viewers = session.viewer_count
    return result


def _live(manager: RunManager, run_id: str) -> RunSession:
    session = manager.get(run_id)
    if session is None or not session.alive:
        raise ApiError(409, "run_not_active", "the run is not running")
    return session


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def launch_run(payload: RunCreate, db: DbSession, manager: Manager) -> RunRead:
    agent = get_agent_row(db, payload.agent_id)
    project = get_project_row(db, payload.project_id)
    # Over its account's daily limit, out of quota or logged out a manual run is still allowed
    # (the CLI shows its own login): the UI warns.
    gate = usage_limits.blocked(db, account_ops.of_agent(db, agent))
    run = manager.launch(db, agent, project, payload.prompt)
    result = _read(run, manager)
    result.warning = f"{gate}_reached" if gate else None
    return result


@router.get("/runs")
def list_runs(
    db: DbSession,
    manager: Manager,
    agent_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[RunRead]:
    query = select(Run).where(Run.workspace_id == DEFAULT_WORKSPACE, Run.kind == RunKind.AGENT)
    if agent_id:
        query = query.where(Run.agent_id == agent_id)
    if task_id:
        query = query.where(Run.task_id == task_id)
    if project_id:
        query = query.where(Run.project_id == project_id)
    statuses = [s.value for s in ACTIVE_STATUSES]
    if active is True:
        query = query.where(Run.status.in_(statuses))
    elif active is False:
        query = query.where(Run.status.not_in(statuses))
    query = query.order_by(Run.created_at.desc()).limit(limit)
    return [_read(run, manager) for run in db.scalars(query)]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: DbSession, manager: Manager) -> RunRead:
    return _read(_get(db, run_id), manager, detail=True)


@router.get("/runs/{run_id}/events")
def list_run_events(run_id: str, db: DbSession) -> list[RunEventRead]:
    """What the agent reported (MCP) and what happened (hooks, Agentic OS), oldest first."""
    _get(db, run_id)
    events = db.scalars(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.at, RunEvent.id)
    )
    return [RunEventRead.model_validate(e) for e in events]


@router.post("/runs/{run_id}/control")
def control_run(run_id: str, payload: ControlRequest, db: DbSession, manager: Manager) -> RunRead:
    run = _get(db, run_id)
    session = _live(manager, run_id)
    try:
        if payload.action == ControlAction.TAKE:
            session.take_control(payload.client_id)
        else:
            session.release_control(payload.client_id)
    except ControlConflict as error:
        raise ApiError(409, "control_taken", "another viewer has the control") from error
    db.refresh(run)
    return _read(run, manager)


@router.post("/runs/{run_id}/permission")
def answer_permission(
    run_id: str, payload: PermissionAnswer, db: DbSession, manager: Manager
) -> RunRead:
    """Answers the CLI's open permission dialog («Yes» / «No»)."""
    run = _get(db, run_id)
    if not manager.answer_permission(run.id, payload.approve):
        raise ApiError(409, "no_permission_dialog", "no permission dialog is waiting")
    return _read(run, manager)


@router.post("/runs/{run_id}/resume", status_code=status.HTTP_201_CREATED)
def resume_run(run_id: str, db: DbSession, manager: Manager) -> RunRead:
    """«Reanudar sesión»: a new run continues this one's CLI conversation."""
    run = manager.resume(db, _get(db, run_id))
    return _read(run, manager, detail=True)


@router.post("/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
def stop_run(run_id: str, db: DbSession, manager: Manager) -> RunRead:
    run = _get(db, run_id)
    _live(manager, run_id).stop()
    return _read(run, manager)


def _tail(path: str) -> str:
    """Last SCROLLBACK_LIMIT characters of a finished run's log."""
    file = Path(path)
    if not path or not file.is_file():
        return ""
    text = file.read_text("utf-8", errors="replace")
    return text[-SCROLLBACK_LIMIT:]


@router.websocket("/runs/{run_id}/terminal")
async def run_terminal(websocket: WebSocket, run_id: str, client_id: str) -> None:
    await websocket.accept()
    manager: RunManager = websocket.app.state.run_manager
    session = manager.get(run_id)

    if session is None or not session.alive:
        with websocket.app.state.sessionmaker() as db:
            run = db.get(Run, run_id)
        if run is None:
            await websocket.close(code=4404)
            return
        await websocket.send_json(
            {"type": "snapshot", "data": await asyncio.to_thread(_tail, run.log_path)}
        )
        await websocket.send_json({"type": "exit", "code": run.exit_code, "status": run.status})
        await websocket.close()
        return

    await serve_terminal(websocket, session, client_id)
