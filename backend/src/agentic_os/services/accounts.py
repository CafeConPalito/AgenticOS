"""CLI accounts (phase 10, ADR 0014): which login each agent runs with, the folder that keeps it,
whether its session is alive and how much of its subscription windows is used.

Plain functions on a DB session; whoever calls them commits.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, new_id, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    ACTIVE_STATUSES,
    Agent,
    Cli,
    CliAccount,
    InboxItem,
    InboxKind,
    InboxStatus,
    Resolution,
    Run,
    SessionState,
)
from agentic_os.services import proc
from agentic_os.services.quota import QuotaWindow
from agentic_os.services.runs.launcher import clean_env, resolve_executable

SYSTEM_LABEL = "Cuenta del sistema"
CLAUDE_CONFIG_DIR = "CLAUDE_CONFIG_DIR"
AUTH_TIMEOUT = 20
MODELS_TIMEOUT = 45
# A session probed less than this long ago is not probed again before launching.
FRESH_PROBE_SECONDS = 600

Runner = Callable[..., subprocess.CompletedProcess[str]]


# ---------------------------------------------------------------------- lookup
def get(db: Session, account_id: str) -> CliAccount | None:
    return db.get(CliAccount, account_id)


CLI_ORDER = {Cli.CLAUDE.value: 0, Cli.AGY.value: 1}


def list_accounts(db: Session, cli: Cli | None = None) -> list[CliAccount]:
    """The accounts in the order the app shows them: by CLI (Claude Code first), then oldest
    first, so the system account heads its CLI."""
    query = select(CliAccount).where(CliAccount.workspace_id == DEFAULT_WORKSPACE)
    if cli is not None:
        query = query.where(CliAccount.cli == cli.value)
    found = db.scalars(query.order_by(CliAccount.created_at, CliAccount.id))
    return sorted(found, key=lambda a: CLI_ORDER.get(a.cli, len(CLI_ORDER)))


def _system_account(db: Session, cli: Cli) -> CliAccount:
    """The CLI's own configuration. The migration creates it; this covers a database that
    somehow lacks it (it becomes the default only if the CLI has none)."""
    account = db.scalar(
        select(CliAccount)
        .where(CliAccount.cli == cli.value, CliAccount.config_dir.is_(None))
        .order_by(CliAccount.created_at)
    )
    if account is None:
        has_default = db.scalar(
            select(CliAccount.id).where(CliAccount.cli == cli.value, CliAccount.is_default)
        )
        account = CliAccount(
            workspace_id=DEFAULT_WORKSPACE,
            cli=cli.value,
            label=SYSTEM_LABEL,
            config_dir=None,
            is_default=has_default is None,
        )
        db.add(account)
        db.flush()
    return account


def default_for(db: Session, cli: Cli) -> CliAccount:
    account = db.scalar(
        select(CliAccount).where(CliAccount.cli == cli.value, CliAccount.is_default)
    )
    return account or _system_account(db, cli)


def fallback_active(agent: Agent, now: datetime | None = None) -> bool:
    """The person chose to switch and the window has not reset yet: the agent runs with its
    secondary CLI."""
    until = agent.using_fallback_until
    return bool(agent.fallback_account_id and until and until > (now or utcnow()))


def of_agent(db: Session, agent: Agent, now: datetime | None = None) -> CliAccount:
    """The account an agent runs with: the secondary while it is switched, else its own, or the
    default one of its CLI."""
    if fallback_active(agent, now):
        secondary = db.get(CliAccount, agent.fallback_account_id)
        if secondary is not None:
            return secondary
    if agent.account_id:
        account = db.get(CliAccount, agent.account_id)
        if account is not None and account.cli == agent.cli:
            return account
    return default_for(db, Cli(agent.cli))


class AccountIndex:
    """All the accounts, read once, to resolve many agents without a query each."""

    def __init__(self, db: Session) -> None:
        self.accounts = {a.id: a for a in list_accounts(db)}
        self._default = {a.cli: a for a in self.accounts.values() if a.is_default}

    def of(self, agent: Agent, now: datetime | None = None) -> CliAccount | None:
        if fallback_active(agent, now):
            secondary = self.accounts.get(agent.fallback_account_id)
            if secondary is not None:
                return secondary
        account = self.accounts.get(agent.account_id) if agent.account_id else None
        if account is not None and account.cli == agent.cli:
            return account
        return self._default.get(agent.cli)


def display_name(account: CliAccount) -> str:
    """What the app calls an account: its email once the CLI told us, else the name it was given."""
    return (
        account.email or account.label or ("Cuenta nueva" if account.config_dir else SYSTEM_LABEL)
    )


# ---------------------------------------------------------------------- environment
def config_dir(account: CliAccount) -> Path | None:
    return Path(account.config_dir) if account.config_dir else None


def env_for(account: CliAccount) -> dict[str, str]:
    """What the CLI needs to use this account's login. The system account adds nothing: the CLI
    keeps the configuration the person already had (including their own `CLAUDE_CONFIG_DIR`)."""
    if account.cli == Cli.CLAUDE and account.config_dir:
        return {CLAUDE_CONFIG_DIR: account.config_dir}
    return {}


def accounts_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / "accounts"


# ---------------------------------------------------------------------- create / edit / delete
def create(db: Session, data_dir: Path | str, cli: Cli, label: str = "") -> CliAccount:
    """A new account with a login folder of its own. Only Claude Code can have several: agy
    keeps its login in the operating system's credential store, not in a folder (ADR 0014)."""
    if cli != Cli.CLAUDE:
        raise ApiError(
            409, "accounts_unsupported", "this CLI keeps a single login and cannot have more", "cli"
        )
    account_id = new_id()
    folder = accounts_dir(data_dir) / account_id
    folder.mkdir(parents=True, exist_ok=True)
    account = CliAccount(
        id=account_id,
        workspace_id=DEFAULT_WORKSPACE,
        cli=cli.value,
        label=label.strip(),
        config_dir=str(folder),
        is_default=False,
        session_state=SessionState.UNKNOWN,
    )
    db.add(account)
    db.flush()
    return account


def set_default(db: Session, account: CliAccount) -> None:
    db.execute(
        update(CliAccount)
        .where(CliAccount.cli == account.cli, CliAccount.id != account.id)
        .values(is_default=False)
    )
    db.flush()  # the partial unique index allows one default per CLI
    account.is_default = True


def delete(db: Session, account: CliAccount) -> None:
    if account.config_dir is None:
        raise ApiError(409, "system_account", "the system account cannot be removed")
    if db.scalar(
        select(Agent.id)
        .where((Agent.account_id == account.id) | (Agent.fallback_account_id == account.id))
        .limit(1)
    ):
        raise ApiError(409, "account_in_use", "agents use this account")
    busy = db.scalar(
        select(Run.id)
        .where(Run.account_id == account.id, Run.status.in_([s.value for s in ACTIVE_STATUSES]))
        .limit(1)
    )
    if busy:
        raise ApiError(409, "account_busy", "a run is using this account")
    if account.is_default:
        set_default(db, _system_account(db, Cli(account.cli)))
    for item in db.scalars(
        select(InboxItem).where(
            InboxItem.command == account.id,
            InboxItem.kind.in_([InboxKind.LIMIT, InboxKind.QUOTA, InboxKind.ACCOUNT]),
            InboxItem.status == InboxStatus.PENDING,
        )
    ):
        item.status, item.resolution, item.resolved_at = (
            InboxStatus.RESOLVED,
            Resolution.DISMISSED,
            utcnow(),
        )
    folder = Path(account.config_dir)
    db.delete(account)
    db.flush()
    shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------------- session
@dataclass
class Identity:
    logged_in: bool | None  # None: the CLI could not tell
    email: str = ""
    plan: str = ""


def _json_object(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_claude_status(result: subprocess.CompletedProcess[str]) -> Identity:
    """`claude auth status` prints JSON and exits 1 when nobody is logged in: read the JSON, not
    the exit code."""
    data = _json_object(result.stdout or "")
    if data is None or not isinstance(data.get("loggedIn"), bool):
        return Identity(None)
    email, plan = data.get("email"), data.get("subscriptionType")
    return Identity(
        data["loggedIn"],
        email if isinstance(email, str) else "",
        plan if isinstance(plan, str) else "",
    )


LOGGED_OUT_HINTS = ("log in", "login", "sign in", "not logged", "authenticat", "credential")


def is_installed(cli: Cli, overrides: Mapping[str, list[str]] | None = None) -> bool:
    try:
        resolve_executable(cli, overrides)
    except ApiError:
        return False
    return True


def _agy_identity(result: subprocess.CompletedProcess[str]) -> Identity:
    """agy has no status command: with a session `agy models` lists them (id<TAB>label). A failure
    only means «logged out» if it says so: offline or a crash must not block the agents."""
    if result.returncode == 0 and "\t" in (result.stdout or ""):
        return Identity(True)
    text = f"{result.stdout or ''} {result.stderr or ''}".lower()
    if any(hint in text for hint in LOGGED_OUT_HINTS):
        return Identity(False)
    return Identity(None)


def probe(
    db: Session,
    account: CliAccount,
    overrides: Mapping[str, list[str]] | None = None,
    run: Runner | None = None,
) -> CliAccount:
    """Asks the CLI whether this account's session is alive, and who it is. The caller commits.

    When the CLI cannot tell (a timeout, no network, an unreadable answer) what was known stays:
    only the time of the check moves, so a hiccup neither blocks the agents of a good account
    nor releases a logged-out one. A CLI that is not installed is not checked at all."""
    run = run or proc.run
    cli = Cli(account.cli)
    try:
        prefix = resolve_executable(cli, overrides)
    except ApiError:
        return account
    env = {**clean_env(), **env_for(account)}
    identity = Identity(None)
    try:
        if cli == Cli.CLAUDE:
            identity = parse_claude_status(run([*prefix, "auth", "status"], AUTH_TIMEOUT, env=env))
        else:
            identity = _agy_identity(run([*prefix, "models"], MODELS_TIMEOUT, env=env))
    except (OSError, subprocess.TimeoutExpired):
        pass
    account.session_checked_at = utcnow()
    if identity.logged_in is None:
        return account
    account.session_state = SessionState.OK if identity.logged_in else SessionState.DOWN
    if identity.logged_in:
        record_identity(account, identity.email, identity.plan)
    return account


def record_identity(account: CliAccount, email: str, plan: str) -> None:
    """Who the account is, as the CLI reports it (`auth status`, or agy's status line)."""
    if email:
        account.email = email[:200]
    if plan:
        account.plan = plan[:80]


def session_is_fresh(account: CliAccount, now: datetime | None = None) -> bool:
    if account.session_checked_at is None:
        return False
    age = ((now or utcnow()) - account.session_checked_at).total_seconds()
    return age < FRESH_PROBE_SECONDS


# ---------------------------------------------------------------------- quota
@dataclass(frozen=True)
class QuotaView:
    id: str
    used_pct: float
    resets_at: datetime
    read_at: datetime
    # The window ended since it was read: it shows as reset (0 %) until a session reads it again.
    expired: bool


REFRESH_READ_AT_SECONDS = 60


def record_quota(
    account: CliAccount, windows: Iterable[QuotaWindow], now: datetime | None = None
) -> bool:
    """Keeps the last value of each window the CLI reported (a window it omits is kept as it
    was: it expires by itself when its reset time passes). The status line fires on every state
    change, so an unchanged value only refreshes its «read at» once a minute.

    True when a figure or a reset time changed (worth telling the UI)."""
    now = now or utcnow()
    current = dict(account.quota or {})
    changed = stale = False
    for window in windows:
        entry = {
            "used_pct": round(window.used_pct, 2),
            "resets_at": window.resets_at.isoformat(),
            "read_at": now.isoformat(),
        }
        old = current.get(window.id)
        if old is None or (old.get("used_pct"), old.get("resets_at")) != (
            entry["used_pct"],
            entry["resets_at"],
        ):
            changed = True
        else:
            try:
                age = (now - datetime.fromisoformat(old["read_at"])).total_seconds()
            except (KeyError, TypeError, ValueError):
                age = REFRESH_READ_AT_SECONDS
            if age < REFRESH_READ_AT_SECONDS:
                continue
            stale = True
        current[window.id] = entry
    if changed or stale:
        account.quota = current  # a new dict: SQLAlchemy does not see changes inside a JSON value
    return changed


def quota_view(account: CliAccount, now: datetime | None = None) -> list[QuotaView]:
    now = now or utcnow()
    views = []
    for window_id, value in sorted((account.quota or {}).items()):
        try:
            resets_at = datetime.fromisoformat(value["resets_at"])
            read_at = datetime.fromisoformat(value["read_at"])
            used = float(value["used_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        expired = now >= resets_at
        views.append(QuotaView(window_id, 0.0 if expired else used, resets_at, read_at, expired))
    return views


def highest_quota(account: CliAccount, now: datetime | None = None) -> QuotaView | None:
    views = [v for v in quota_view(account, now) if not v.expired]
    return max(views, key=lambda v: v.used_pct, default=None)


# ---------------------------------------------------------------------- daily limit
def set_daily_limit(account: CliAccount, value: float | None) -> None:
    """The one place a daily limit is set. agy counts whole tokens: a fraction rounds to the
    nearest one, and a limit that rounds to 0 would block the account for good, so it is refused."""
    if value is not None and account.cli == Cli.AGY:
        value = float(round(value))
    if value is not None and value < 1 and account.cli == Cli.AGY:
        raise ApiError(422, "invalid_limit", "the limit must be at least 1 token", "daily_limit")
    account.daily_limit = value
