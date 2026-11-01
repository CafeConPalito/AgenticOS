"""Terminals of the person's own (phase 23, ADR 0029): a CLI opened by hand with an account and a
folder, without agent or task. Each one is a run of kind «terminal»: its terminal is the run's
WebSocket, and its usage shows in Consumo."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.runs import Manager, _get, _read
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import ACTIVE_STATUSES, Cli, CliAccount, Run, RunKind
from agentic_os.schemas.run import RunRead
from agentic_os.services import accounts as account_ops

router = APIRouter(tags=["terminals"])
DbSession = Annotated[Session, Depends(get_session)]


class TerminalCreate(BaseModel):
    cli: Cli
    # None: the CLI's default account.
    account_id: str | None = None
    cwd: str = Field(min_length=1)


@router.get("/terminals")
def list_terminals(db: DbSession, manager: Manager) -> list[RunRead]:
    """The terminals still open, oldest first (the order of the dock's tabs)."""
    runs = db.scalars(
        select(Run)
        .where(
            Run.workspace_id == DEFAULT_WORKSPACE,
            Run.kind == RunKind.TERMINAL.value,
            Run.status.in_([s.value for s in ACTIVE_STATUSES]),
        )
        .order_by(Run.created_at)
    ).all()
    return [_read(run, manager) for run in runs]


@router.post("/terminals", status_code=status.HTTP_201_CREATED)
def open_terminal(payload: TerminalCreate, db: DbSession, manager: Manager) -> RunRead:
    folder = Path(payload.cwd).expanduser()
    if not folder.is_dir():
        raise ApiError(422, "not_a_folder", f"No existe la carpeta {payload.cwd}", field="cwd")
    if payload.account_id is None:
        account = account_ops.default_for(db, payload.cli)
    else:
        account = db.get(CliAccount, payload.account_id)
        if account is None or account.cli != payload.cli.value:
            raise NotFound("account")
    run = manager.launch_terminal(db, cli=payload.cli, account=account, cwd=str(folder))
    return _read(run, manager)


@router.delete("/terminals/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_terminal(run_id: str, db: DbSession, manager: Manager) -> None:
    run = _get(db, run_id)
    if run.kind != RunKind.TERMINAL:
        raise NotFound("terminal")
    manager.stop(run_id)
