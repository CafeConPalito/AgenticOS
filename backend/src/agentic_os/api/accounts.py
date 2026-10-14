"""CLI accounts (phase 10, ADR 0014): the logins each CLI can run with, their session, their
daily limit and the subscription windows read from their status line."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.api.terminal import serve_terminal
from agentic_os.api.usage import today
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import ACTIVE_STATUSES, Agent, Cli, CliAccount, Run
from agentic_os.schemas.account import (
    AccountAgent,
    AccountCreate,
    AccountLogin,
    AccountRead,
    AccountUpdate,
    QuotaWindowRead,
)
from agentic_os.services import accounts as account_ops
from agentic_os.services.usage import limits as usage_limits

router = APIRouter(tags=["accounts"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(db: Session, account_id: str) -> CliAccount:
    account = account_ops.get(db, account_id)
    if account is None:
        raise NotFound("account")
    return account


def read_many(
    db: Session, accounts: list[CliAccount], logging_in: set[str] | None = None
) -> list[AccountRead]:
    """AccountRead for many accounts with a handful of queries."""
    if not accounts:
        return []
    logging_in = logging_in or set()
    used = usage_limits.used_by_account(db, today())
    index = account_ops.AccountIndex(db)
    users: dict[str, list[AccountAgent]] = {a.id: [] for a in accounts}
    for agent in db.scalars(select(Agent).order_by(Agent.created_at, Agent.name)):
        owner = index.of(agent)
        if owner is not None and owner.id in users:
            users[owner.id].append(AccountAgent(id=agent.id, name=agent.name, color=agent.color))
    live = dict(
        db.execute(
            select(Run.account_id, func.count())
            .where(
                Run.account_id.in_([a.id for a in accounts]),
                Run.status.in_([s.value for s in ACTIVE_STATUSES]),
            )
            .group_by(Run.account_id)
        ).all()
    )
    return [
        AccountRead(
            id=a.id,
            cli=Cli(a.cli),
            label=a.label,
            name=account_ops.display_name(a),
            email=a.email,
            plan=a.plan,
            is_default=a.is_default,
            is_system=a.is_system,
            session_state=a.session_state,
            session_checked_at=a.session_checked_at,
            daily_limit=a.daily_limit,
            unit=usage_limits.unit_of(a),
            used_today=round(used.get(a.id, 0.0), 6),
            quota=[
                QuotaWindowRead(
                    id=v.id,
                    used_pct=v.used_pct,
                    resets_at=v.resets_at,
                    read_at=v.read_at,
                    expired=v.expired,
                )
                for v in account_ops.quota_view(a)
            ],
            agents=users[a.id],
            live_runs=live.get(a.id, 0),
            logging_in=a.id in logging_in,
        )
        for a in accounts
    ]


def _read(db: Session, request: Request, accounts: list[CliAccount]) -> list[AccountRead]:
    return read_many(db, accounts, request.app.state.logins.live_ids())


@router.get("/accounts")
def list_accounts(db: DbSession, request: Request) -> list[AccountRead]:
    return _read(db, request, account_ops.list_accounts(db))


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession, request: Request) -> AccountRead:
    account = account_ops.create(
        db, request.app.state.settings.data_dir, payload.cli, payload.label
    )
    db.commit()
    return _read(db, request, [account])[0]


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: str, payload: AccountUpdate, db: DbSession, request: Request
) -> AccountRead:
    account = _get(db, account_id)
    if payload.label is not None:
        account.label = payload.label
    if "daily_limit" in payload.model_fields_set:
        account_ops.set_daily_limit(account, payload.daily_limit)
        usage_limits.sync_limit_items(db, today())
    db.commit()
    request.app.state.scheduler.poke()  # a raised limit lets queued tasks start
    return _read(db, request, [account])[0]


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: str, db: DbSession, request: Request) -> None:
    account = _get(db, account_id)
    if request.app.state.logins.get(account_id) is not None:
        raise ApiError(409, "account_busy", "a login is open for this account")
    account_ops.delete(db, account)
    db.commit()


@router.post("/accounts/{account_id}/default")
def make_default(account_id: str, db: DbSession, request: Request) -> AccountRead:
    """The account the agents without one of their own use."""
    account = _get(db, account_id)
    account_ops.set_default(db, account)
    db.commit()
    return _read(db, request, [account])[0]


@router.post("/accounts/{account_id}/probe")
def probe_account(account_id: str, db: DbSession, request: Request) -> AccountRead:
    """Asks the CLI whether the session is alive and who it belongs to (a few seconds)."""
    account = _get(db, account_id)
    manager = request.app.state.run_manager
    if not manager.cli_installed(Cli(account.cli)):
        raise ApiError(409, "cli_not_installed", "the CLI of this account is not installed")
    manager.probe_account(db, account)
    usage_limits.sync_session_items(db)
    db.commit()
    request.app.state.scheduler.poke()
    return _read(db, request, [account])[0]


# ---------------------------------------------------------------------- login
@router.post("/accounts/{account_id}/login")
def start_login(
    account_id: str, payload: AccountLogin, db: DbSession, request: Request
) -> AccountRead:
    """Opens the CLI's login in a terminal (see `/accounts/{id}/login/terminal`). With one
    already open, it is the same. When it ends the session is checked again."""
    account = _get(db, account_id)
    request.app.state.logins.start(account, payload.email or account.email)
    return _read(db, request, [account])[0]


@router.delete("/accounts/{account_id}/login", status_code=status.HTTP_204_NO_CONTENT)
def cancel_login(account_id: str, db: DbSession, request: Request) -> None:
    _get(db, account_id)
    request.app.state.logins.stop(account_id)


@router.websocket("/accounts/{account_id}/login/terminal")
async def login_terminal(websocket: WebSocket, account_id: str, client_id: str = "") -> None:
    await websocket.accept()
    session = websocket.app.state.logins.get(account_id)
    if session is None:
        await websocket.send_json({"type": "exit", "code": None, "status": "exited"})
        await websocket.close()
        return
    await serve_terminal(websocket, session, client_id or uuid.uuid4().hex)
