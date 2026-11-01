"""Daily limits per account and the gate that stops the scheduler (phase 07, ADR 0011; per
account since phase 10, ADR 0014).

- Claude Code: API-equivalent cost of today, in USD. agy: tokens of today without cache (agy
  records no cost). A limit only stops the scheduler from starting tasks of that account:
  running sessions go on and runs launched by hand are allowed (with a warning).
- A pending «Cuota agotada» item of an account stops it the same way until the person resumes.
- So does a logged-out session: the CLI would only ask for a login nobody is there to type.
- One «Límite diario alcanzado» Inbox item per account and day. It resolves itself on a new day
  or when the limit goes up. One «Sesión cerrada» item per account while it stays logged out.

Every other account of the same CLI keeps working. Plain functions on a DB session; whoever
calls them commits.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import (
    Agent,
    AgentStatus,
    Cli,
    CliAccount,
    InboxItem,
    InboxKind,
    InboxStatus,
    Resolution,
    RunKind,
    SessionState,
)
from agentic_os.schemas.usage import LimitState
from agentic_os.services import accounts as account_ops
from agentic_os.services import inbox
from agentic_os.services.usage.stats import day_bounds, limit_tokens, local_day, runs_between

NEAR = 0.8
LIMIT = "limit"
QUOTA = "quota"
SESSION = "session"
UNITS = {Cli.CLAUDE: "usd", Cli.AGY: "tokens"}
CLI_NAMES = {Cli.CLAUDE: "Claude Code", Cli.AGY: "Antigravity"}


def unit_of(account: CliAccount) -> str:
    return UNITS[Cli(account.cli)]


def used_by_account(db: Session, today: date, tz: tzinfo | None = None) -> dict[str, float]:
    """What counts for each account's limit today, from a single read of today's runs: USD for
    Claude Code, tokens without cache for agy. A run whose account was removed counts for the
    default one of its CLI. The person's own terminals (phase 23) are left out: what they spend
    by hand does not stop the agents (ADR 0029)."""
    accounts = account_ops.list_accounts(db)
    default = {a.cli: a.id for a in accounts if a.is_default}
    used = {a.id: 0.0 for a in accounts}
    for run in runs_between(db, today, today, tz=tz):
        if run.kind == RunKind.TERMINAL:
            continue
        account_id = run.account_id if run.account_id in used else default.get(run.cli)
        if account_id is None:
            continue
        used[account_id] += (run.cost_usd or 0.0) if run.cli == Cli.CLAUDE else limit_tokens(run)
    return used


def quota_pending_accounts(db: Session) -> set[str]:
    """The accounts with a «Cuota agotada» waiting for the person (its item names the account)."""
    return {
        command
        for command in db.scalars(
            select(InboxItem.command).where(
                InboxItem.kind == InboxKind.QUOTA, InboxItem.status == InboxStatus.PENDING
            )
        )
        if command
    }


def _today(today: date | None, tz: tzinfo | None) -> date:
    return today or local_day(datetime.now().astimezone(), tz)


def states(db: Session, today: date | None = None, tz: tzinfo | None = None) -> list[LimitState]:
    """One state per account, to show how far each one is from its limit."""
    accounts = account_ops.list_accounts(db)
    used_now = used_by_account(db, _today(today, tz), tz)
    quota = quota_pending_accounts(db)
    result = []
    for account in accounts:
        limit = account.daily_limit
        used = used_now[account.id]
        ratio = used / limit if limit else None
        result.append(
            LimitState(
                account_id=account.id,
                account_name=account_ops.display_name(account),
                is_default=account.is_default,
                cli=account.cli,
                unit=unit_of(account),
                limit=limit,
                used=round(used, 6),
                ratio=ratio,
                reached=ratio is not None and ratio >= 1,
                near=ratio is not None and ratio >= NEAR,
                quota_exhausted=account.id in quota,
            )
        )
    return result


def blocked_all(
    db: Session, today: date | None = None, tz: tzinfo | None = None
) -> dict[str, str | None]:
    """Why the scheduler must not start tasks of each account now: "quota", "session", "limit"
    or None. One query for the quotas and, only if a limit is set, one for today's runs."""
    accounts = account_ops.list_accounts(db)
    quota = quota_pending_accounts(db)
    result: dict[str, str | None] = {}
    for account in accounts:
        if account.id in quota:
            result[account.id] = QUOTA
        elif account.session_state == SessionState.DOWN:
            result[account.id] = SESSION
        else:
            result[account.id] = None
    pending = [a for a in accounts if result[a.id] is None and a.daily_limit is not None]
    if pending:
        used = used_by_account(db, _today(today, tz), tz)
        for account in pending:
            if account.daily_limit is not None and used[account.id] >= account.daily_limit:
                result[account.id] = LIMIT
    return result


def blocked(
    db: Session, account: CliAccount, today: date | None = None, tz: tzinfo | None = None
) -> str | None:
    return blocked_all(db, today, tz).get(account.id)


def _format(cli: Cli, value: float) -> str:
    if cli == Cli.CLAUDE:
        return f"{value:.2f} $".replace(".", ",")
    return f"{int(value):,} tokens".replace(",", ".")


def title_name(account: CliAccount, siblings: int) -> str:
    """«Claude Code», or «Claude Code (marta@…)» when the CLI has several accounts."""
    name = CLI_NAMES[Cli(account.cli)]
    return f"{name} ({account_ops.display_name(account)})" if siblings > 1 else name


def sync_limit_items(db: Session, today: date | None = None, tz: tzinfo | None = None) -> bool:
    """Creates today's «Límite diario alcanzado» items and resolves the ones that no longer
    apply (another day, or the limit went up). True if an account got unblocked.

    One item per account and day: an item of today the person already dismissed is not created
    again (the limit still holds; the Dashboard keeps showing it)."""
    day = _today(today, tz)
    accounts = account_ops.list_accounts(db)
    used_now = used_by_account(db, day, tz)
    per_cli = {cli.value: sum(1 for a in accounts if a.cli == cli.value) for cli in Cli}
    unblocked = False
    pending = {(item.command or ""): item for item in inbox.pending(db, kinds=(InboxKind.LIMIT,))}
    known = {a.id for a in accounts}
    for command, item in list(pending.items()):  # the account of an old item is gone
        if command not in known:
            inbox.resolve(db, item, Resolution.DISMISSED)
            del pending[command]
    for account in accounts:
        cli = Cli(account.cli)
        limit = account.daily_limit
        used = used_now[account.id]
        reached = limit is not None and used >= limit
        item = pending.get(account.id)
        if item is not None and (not reached or local_day(item.created_at, tz) != day):
            inbox.resolve(db, item, Resolution.DISMISSED)
            unblocked = unblocked or not reached
            item = None
        if (
            reached
            and item is None
            and limit is not None
            and not _created_today(db, account, day, tz)
        ):
            name = title_name(account, per_cli[account.cli])
            inbox.create(
                db,
                InboxKind.LIMIT,
                f"Límite diario de {name} alcanzado",
                f"Hoy: {_format(cli, used)} de {_format(cli, limit)}. No se lanzarán tareas "
                f"nuevas de {name} hasta mañana o hasta que subas el límite en "
                "Ajustes. Las ejecuciones en marcha siguen.",
                command=account.id,
            )
    return unblocked


def _created_today(db: Session, account: CliAccount, day: date, tz: tzinfo | None) -> bool:
    """A limit item of this account was already created today and still applies: pending, or
    seen by the person («reviewed»). Items resolved because the limit went up are «dismissed»."""
    start, end = day_bounds(day, day, tz)
    items = db.scalars(
        select(InboxItem).where(
            InboxItem.kind == InboxKind.LIMIT,
            InboxItem.command == account.id,
            InboxItem.created_at >= start,
            InboxItem.created_at < end,
            InboxItem.resolution != Resolution.DISMISSED,
        )
    )
    return next(iter(items), None) is not None


def accounts_in_use(db: Session) -> set[str]:
    """The accounts some active agent runs with (only those are worth nagging about)."""
    index = account_ops.AccountIndex(db)
    used = set()
    for agent in db.scalars(select(Agent).where(Agent.status == AgentStatus.ACTIVE)):
        account = index.of(agent)
        if account is not None:
            used.add(account.id)
    return used


def sync_session_items(db: Session) -> bool:
    """«Sesión cerrada» for the accounts in use whose session is logged out; resolved as soon
    as it is back (or nobody uses the account). True if the set of logged-out accounts changed
    in a way the scheduler cares about (a session came back)."""
    accounts = account_ops.list_accounts(db)
    in_use = accounts_in_use(db)
    per_cli = {cli.value: sum(1 for a in accounts if a.cli == cli.value) for cli in Cli}
    pending = {(item.command or ""): item for item in inbox.pending(db, kinds=(InboxKind.ACCOUNT,))}
    back = False
    for account in accounts:
        down = account.session_state == SessionState.DOWN and account.id in in_use
        item = pending.pop(account.id, None)
        if item is not None and not down:
            inbox.resolve(db, item, Resolution.DISMISSED)
            back = back or account.session_state != SessionState.DOWN
        elif item is None and down:
            name = title_name(account, per_cli[account.cli])
            inbox.create(
                db,
                InboxKind.ACCOUNT,
                f"La sesión de {name} está cerrada",
                "Los agentes que usan esta cuenta no arrancarán tareas hasta que vuelvas a "
                "iniciar sesión. Reconéctala desde CLIs y cuentas.",
                command=account.id,
            )
    for item in pending.values():  # the account is gone
        inbox.resolve(db, item, Resolution.DISMISSED)
    return back
