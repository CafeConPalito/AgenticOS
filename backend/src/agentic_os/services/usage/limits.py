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
from agentic_os.services.usage.stats import limit_tokens, local_day, runs_between

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


def used_today(db: Session, cli: Cli, today: date, tz: tzinfo | None = None) -> float:
    runs = runs_between(db, today, today, cli=cli, tz=tz)
    if cli == Cli.CLAUDE:
        return sum(r.cost_usd or 0.0 for r in runs)
    return float(sum(limit_tokens(r) for r in runs))


def quota_pending(db: Session, cli: Cli) -> bool:
    """A «Cuota agotada» of this CLI waits for the person (its item names the CLI)."""
    return (
        db.scalar(
            select(InboxItem.id)
            .where(
                InboxItem.kind == InboxKind.QUOTA,
                InboxItem.status == InboxStatus.PENDING,
                InboxItem.command == cli.value,
            )
            .limit(1)
        )
        is not None
    )


def states(db: Session, today: date | None = None, tz: tzinfo | None = None) -> list[LimitState]:
    day = today or local_day(datetime.now().astimezone(), tz)
    limits = get_limits(db)
    result = []
    for cli in (Cli.CLAUDE, Cli.AGY):
        limit = limit_of(limits, cli)
        used = used_today(db, cli, day, tz)
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
                quota_exhausted=quota_pending(db, cli),
            )
        )
    return result


def blocked(
    db: Session, cli: Cli, today: date | None = None, tz: tzinfo | None = None
) -> str | None:
    """Why the scheduler must not start tasks of this CLI now: "quota", "limit" or None."""
    if quota_pending(db, cli):
        return QUOTA
    limit = limit_of(get_limits(db), cli)
    if limit is None:
        return None
    day = today or local_day(datetime.now().astimezone(), tz)
    return LIMIT if used_today(db, cli, day, tz) >= limit else None


def _format(cli: Cli, value: float) -> str:
    if cli == Cli.CLAUDE:
        return f"{value:.2f} $".replace(".", ",")
    return f"{int(value):,} tokens".replace(",", ".")


def sync_limit_items(db: Session, today: date | None = None, tz: tzinfo | None = None) -> bool:
    """Creates today's «Límite diario alcanzado» items and resolves the ones that no longer
    apply (another day, or the limit went up). True if a CLI got unblocked."""
    day = today or local_day(datetime.now().astimezone(), tz)
    limits = get_limits(db)
    unblocked = False
    pending = {(item.command or ""): item for item in inbox.pending(db, kinds=(InboxKind.LIMIT,))}
    for cli in (Cli.CLAUDE, Cli.AGY):
        limit = limit_of(limits, cli)
        used = used_today(db, cli, day, tz)
        reached = limit is not None and used >= limit
        item = pending.get(cli.value)
        if item is not None and (not reached or local_day(item.created_at, tz) != day):
            inbox.resolve(db, item, Resolution.DISMISSED)
            unblocked = unblocked or not reached
            item = None
        if reached and item is None and limit is not None:
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
