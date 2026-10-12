"""Daily limits per CLI and the «Cuota agotada» gate (phase 07, ADR 0011).

- Claude Code: API-equivalent cost of today, in USD. agy: tokens of today without cache (agy
  records no cost). A limit only stops the scheduler from starting tasks of that CLI: running
  sessions go on and runs launched by hand are allowed (with a warning).
- A pending «Cuota agotada» item of a CLI stops it the same way until the person resumes.
- One «Límite diario alcanzado» Inbox item per CLI and day. It resolves itself on a new day or
  when the limit goes up.

Plain functions on a DB session; whoever calls them commits.
"""

from __future__ import annotations

import json
from datetime import date, datetime, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import (
    USAGE_LIMITS,
    AppState,
    Cli,
    InboxItem,
    InboxKind,
    InboxStatus,
    Resolution,
)
from agentic_os.schemas.usage import LimitState, UsageLimits
from agentic_os.services import inbox
from agentic_os.services.usage.stats import day_bounds, limit_tokens, local_day, runs_between

NEAR = 0.8
LIMIT = "limit"
QUOTA = "quota"
UNITS = {Cli.CLAUDE: "usd", Cli.AGY: "tokens"}
CLI_NAMES = {Cli.CLAUDE: "Claude Code", Cli.AGY: "Antigravity"}


def get_limits(db: Session) -> UsageLimits:
    state = db.get(AppState, USAGE_LIMITS)
    if state is None:
        return UsageLimits()
    try:
        return UsageLimits(**json.loads(state.value))
    except (ValueError, TypeError):
        return UsageLimits()


def save_limits(db: Session, limits: UsageLimits) -> UsageLimits:
    state = db.get(AppState, USAGE_LIMITS) or AppState(key=USAGE_LIMITS)
    state.value = limits.model_dump_json()
    db.add(state)
    return limits


def limit_of(limits: UsageLimits, cli: Cli) -> float | None:
    return limits.claude_usd if cli == Cli.CLAUDE else limits.agy_tokens


def used_by_cli(db: Session, today: date, tz: tzinfo | None = None) -> dict[Cli, float]:
    """What counts for each CLI's limit today, from a single read of today's runs: USD for
    Claude Code, tokens without cache for agy."""
    used = {cli: 0.0 for cli in Cli}
    for run in runs_between(db, today, today, tz=tz):
        cli = Cli(run.cli)
        used[cli] += (run.cost_usd or 0.0) if cli == Cli.CLAUDE else limit_tokens(run)
    return used


def used_today(db: Session, cli: Cli, today: date, tz: tzinfo | None = None) -> float:
    return used_by_cli(db, today, tz)[cli]


def quota_pending_clis(db: Session) -> set[str]:
    """The CLIs with a «Cuota agotada» waiting for the person (its item names the CLI)."""
    return set(
        db.scalars(
            select(InboxItem.command).where(
                InboxItem.kind == InboxKind.QUOTA, InboxItem.status == InboxStatus.PENDING
            )
        )
    )


def quota_pending(db: Session, cli: Cli) -> bool:
    return cli.value in quota_pending_clis(db)


def _today(today: date | None, tz: tzinfo | None) -> date:
    return today or local_day(datetime.now().astimezone(), tz)


def states(db: Session, today: date | None = None, tz: tzinfo | None = None) -> list[LimitState]:
    limits = get_limits(db)
    used_now = used_by_cli(db, _today(today, tz), tz)
    quota = quota_pending_clis(db)
    result = []
    for cli in (Cli.CLAUDE, Cli.AGY):
        limit = limit_of(limits, cli)
        used = used_now[cli]
        ratio = used / limit if limit else None
        result.append(
            LimitState(
                cli=cli.value,
                unit=UNITS[cli],
                limit=limit,
                used=round(used, 6),
                ratio=ratio,
                reached=ratio is not None and ratio >= 1,
                near=ratio is not None and ratio >= NEAR,
                quota_exhausted=cli.value in quota,
            )
        )
    return result


def blocked_all(
    db: Session, today: date | None = None, tz: tzinfo | None = None
) -> dict[Cli, str | None]:
    """Why the scheduler must not start tasks of each CLI now: "quota", "limit" or None.
    One query for the quotas and, only if a limit is set, one for today's runs."""
    quota = quota_pending_clis(db)
    limits = get_limits(db)
    result: dict[Cli, str | None] = {cli: QUOTA if cli.value in quota else None for cli in Cli}
    pending = [cli for cli in Cli if result[cli] is None and limit_of(limits, cli) is not None]
    if pending:
        used = used_by_cli(db, _today(today, tz), tz)
        for cli in pending:
            limit = limit_of(limits, cli)
            if limit is not None and used[cli] >= limit:
                result[cli] = LIMIT
    return result


def blocked(
    db: Session, cli: Cli, today: date | None = None, tz: tzinfo | None = None
) -> str | None:
    return blocked_all(db, today, tz)[cli]


def _format(cli: Cli, value: float) -> str:
    if cli == Cli.CLAUDE:
        return f"{value:.2f} $".replace(".", ",")
    return f"{int(value):,} tokens".replace(",", ".")


def sync_limit_items(db: Session, today: date | None = None, tz: tzinfo | None = None) -> bool:
    """Creates today's «Límite diario alcanzado» items and resolves the ones that no longer
    apply (another day, or the limit went up). True if a CLI got unblocked.

    One item per CLI and day: an item of today the person already dismissed is not created
    again (the limit still holds; the Dashboard keeps showing it)."""
    day = _today(today, tz)
    limits = get_limits(db)
    used_now = used_by_cli(db, day, tz)
    unblocked = False
    pending = {(item.command or ""): item for item in inbox.pending(db, kinds=(InboxKind.LIMIT,))}
    for cli in (Cli.CLAUDE, Cli.AGY):
        limit = limit_of(limits, cli)
        used = used_now[cli]
        reached = limit is not None and used >= limit
        item = pending.get(cli.value)
        if item is not None and (not reached or local_day(item.created_at, tz) != day):
            inbox.resolve(db, item, Resolution.DISMISSED)
            unblocked = unblocked or not reached
            item = None
        if reached and item is None and limit is not None and not _created_today(db, cli, day, tz):
            inbox.create(
                db,
                InboxKind.LIMIT,
                f"Límite diario de {CLI_NAMES[cli]} alcanzado",
                f"Hoy: {_format(cli, used)} de {_format(cli, limit)}. No se lanzarán tareas "
                f"nuevas de {CLI_NAMES[cli]} hasta mañana o hasta que subas el límite en "
                "Ajustes. Las ejecuciones en marcha siguen.",
                command=cli.value,
            )
    return unblocked


def _created_today(db: Session, cli: Cli, day: date, tz: tzinfo | None) -> bool:
    """A limit item of this CLI was already created today and still applies: pending, or seen
    by the person («reviewed»). Items resolved because the limit went up are «dismissed»."""
    start, end = day_bounds(day, day, tz)
    items = db.scalars(
        select(InboxItem).where(
            InboxItem.kind == InboxKind.LIMIT,
            InboxItem.command == cli.value,
            InboxItem.created_at >= start,
            InboxItem.created_at < end,
            InboxItem.resolution != Resolution.DISMISSED,
        )
    )
    return next(iter(items), None) is not None
