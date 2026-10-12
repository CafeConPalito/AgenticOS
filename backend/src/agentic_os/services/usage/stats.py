"""Usage aggregates (phase 07, ADR 0011).

- A run counts on the **local day** (the computer's time zone) it started; one that crosses
  midnight counts whole on its first day.
- The figures are added up in Python over the runs of the period: a desktop app has hundreds
  or a few thousand runs, and this avoids SQLite's date functions (to review with Postgres).
- Tokens: Claude's `output_tokens` already include its thinking; agy reports them apart.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import ACTIVE_STATUSES, Cli, Project, Run, RunStatus, Task
from agentic_os.schemas.usage import (
    Breakdown,
    BreakdownRow,
    DailyPoint,
    DailySeries,
    Group,
    Kpis,
    SessionRow,
    UsageSummary,
    UsageTotals,
)

DEFAULT_PROJECT_COLOR = "#7C9CFF"
FAILED_STATUSES = {RunStatus.FAILED.value, RunStatus.INTERRUPTED.value}
SESSION_SORTS = {
    "started_at",
    "agent",
    "project",
    "task",
    "model",
    "tokens",
    "cost",
    "duration",
}


# ---------------------------------------------------------------------- per run
def run_tokens(run: Run) -> int:
    thinking = 0 if run.cli == Cli.CLAUDE else run.thinking_tokens
    return (
        run.input_tokens
        + run.output_tokens
        + thinking
        + run.cache_read_tokens
        + run.cache_creation_tokens
    )


def limit_tokens(run: Run) -> int:
    """What counts for agy's daily limit: no cache (spec 07)."""
    thinking = 0 if run.cli == Cli.CLAUDE else run.thinking_tokens
    return run.input_tokens + run.output_tokens + thinking


def started(run: Run) -> datetime:
    return run.started_at or run.created_at


def local_day(moment: datetime, tz: tzinfo | None = None) -> date:
    return moment.astimezone(tz).date()


def day_bounds(first: date, last: date, tz: tzinfo | None = None) -> tuple[datetime, datetime]:
    """[start, end) in UTC of the local days `first`…`last`."""
    start = datetime.combine(first, time.min)
    end = datetime.combine(last + timedelta(days=1), time.min)
    if tz is not None:
        start, end = start.replace(tzinfo=tz), end.replace(tzinfo=tz)
    else:
        start, end = start.astimezone(), end.astimezone()  # the computer's local time
    return start.astimezone(UTC), end.astimezone(UTC)


def duration(run: Run, now: datetime | None = None) -> float | None:
    if run.started_at is None:
        return None
    end = run.ended_at or (now or utcnow())
    return max(0.0, (end - run.started_at).total_seconds())


# ---------------------------------------------------------------------- queries
def runs_between(
    db: Session,
    first: date,
    last: date,
    *,
    agent_id: str | None = None,
    project_id: str | None = None,
    cli: Cli | None = None,
    tz: tzinfo | None = None,
) -> list[Run]:
    start, end = day_bounds(first, last, tz)
    # created_at is indexed by time like started_at (seconds apart): a day of margin, then
    # the exact filter on the start.
    query = select(Run).where(
        Run.workspace_id == DEFAULT_WORKSPACE,
        Run.created_at >= start - timedelta(days=1),
        Run.created_at < end + timedelta(days=1),
    )
    if agent_id:
        query = query.where(Run.agent_id == agent_id)
    if project_id:
        query = query.where(Run.project_id == project_id)
    if cli is not None:
        query = query.where(Run.cli == cli.value)
    return [run for run in db.scalars(query) if start <= started(run) < end]


def totals(runs: Iterable[Run]) -> UsageTotals:
    result = UsageTotals()
    for run in runs:
        result.input_tokens += run.input_tokens
        result.output_tokens += run.output_tokens
        result.thinking_tokens += run.thinking_tokens
        result.cache_read_tokens += run.cache_read_tokens
        result.cache_creation_tokens += run.cache_creation_tokens
        if run.cost_usd is not None:
            result.cost_usd = (result.cost_usd or 0.0) + run.cost_usd
    return result


def task_usage(db: Session, task_ids: list[str]) -> dict[str, UsageTotals]:
    """Every run of each task, its subagents included."""
    if not task_ids:
        return {}
    by_task: dict[str, list[Run]] = defaultdict(list)
    for run in db.scalars(select(Run).where(Run.task_id.in_(task_ids))):
        by_task[run.task_id or ""].append(run)
    return {task_id: totals(runs) for task_id, runs in by_task.items()}


# ---------------------------------------------------------------------- aggregates
def _kpis(runs: list[Run], previous: list[Run], now: datetime) -> Kpis:
    cost = sum(r.cost_usd or 0.0 for r in runs)
    previous_cost = sum(r.cost_usd or 0.0 for r in previous)
    fresh_input = sum(r.input_tokens + r.cache_read_tokens + r.cache_creation_tokens for r in runs)
    cached = sum(r.cache_read_tokens for r in runs)
    finished = [r for r in runs if r.status not in [s.value for s in ACTIVE_STATUSES]]
    ok = [r for r in finished if r.status not in FAILED_STATUSES]
    return Kpis(
        cost_usd=round(cost, 6),
        cost_change=(cost - previous_cost) / previous_cost if previous_cost > 0 else None,
        tokens=sum(run_tokens(r) for r in runs),
        cache_ratio=cached / fresh_input if fresh_input else None,
        agent_hours=sum(duration(r, now) or 0.0 for r in runs) / 3600,
        sessions=len(runs),
        success_ratio=len(ok) / len(finished) if finished else None,
    )


def summary(
    db: Session,
    first: date,
    last: date,
    *,
    agent_id: str | None = None,
    project_id: str | None = None,
    tz: tzinfo | None = None,
    now: datetime | None = None,
) -> UsageSummary:
    runs = runs_between(db, first, last, agent_id=agent_id, project_id=project_id, tz=tz)
    length = (last - first).days + 1
    previous = runs_between(
        db,
        first - timedelta(days=length),
        first - timedelta(days=1),
        agent_id=agent_id,
        project_id=project_id,
        tz=tz,
    )
    return UsageSummary(date_from=first, date_to=last, kpis=_kpis(runs, previous, now or utcnow()))


def _group_of(run: Run, group: str) -> str:
    if group == "agent":
        return run.agent_id or f"name:{run.agent_name}"
    if group == "project":
        return run.project_id or f"name:{run.project_name}"
    return run.task_id or "manual"


def _groups(db: Session, runs: list[Run], group: str) -> dict[str, Group]:
    found: dict[str, Group] = {}
    project_colors: dict[str, str] = {}
    if group == "project":
        ids = {r.project_id for r in runs if r.project_id}
        project_colors = {
            p.id: p.color for p in db.scalars(select(Project).where(Project.id.in_(ids)))
        }
    tasks: dict[str, Task] = {}
    if group == "task":
        ids = {r.task_id for r in runs if r.task_id}
        tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(ids)))}
    for run in runs:
        key = _group_of(run, group)
        if key in found:
            continue
        if group == "agent":
            found[key] = Group(id=run.agent_id, name=run.agent_name, color=run.agent_color)
        elif group == "project":
            color = project_colors.get(run.project_id or "", DEFAULT_PROJECT_COLOR)
            found[key] = Group(id=run.project_id, name=run.project_name, color=color)
        else:
            task = tasks.get(run.task_id or "")
            name = f"{task.code} · {task.title}" if task else "Ejecuciones manuales"
            found[key] = Group(id=run.task_id, name=name, color=run.agent_color)
    return found


def daily(
    db: Session,
    first: date,
    last: date,
    group: str,
    *,
    agent_id: str | None = None,
    project_id: str | None = None,
    tz: tzinfo | None = None,
) -> DailySeries:
    runs = runs_between(db, first, last, agent_id=agent_id, project_id=project_id, tz=tz)
    groups = _groups(db, runs, group)
    cost: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    tokens: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for run in runs:
        day, key = local_day(started(run), tz), _group_of(run, group)
        cost[day][key] += run.cost_usd or 0.0
        tokens[day][key] += run_tokens(run)
    days = []
    day = first
    while day <= last:
        days.append(DailyPoint(day=day, cost=dict(cost[day]), tokens=dict(tokens[day])))
        day += timedelta(days=1)
    ordered = sorted(groups.items(), key=lambda item: item[1].name.lower())
    return DailySeries(
        group=group,
        groups=[g.model_copy(update={"id": key}) for key, g in ordered],
        days=days,
    )


def breakdown(
    db: Session,
    first: date,
    last: date,
    group: str,
    *,
    agent_id: str | None = None,
    project_id: str | None = None,
    tz: tzinfo | None = None,
) -> Breakdown:
    runs = runs_between(db, first, last, agent_id=agent_id, project_id=project_id, tz=tz)
    groups = _groups(db, runs, group)
    per: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        per[_group_of(run, group)].append(run)
    total_cost = sum(r.cost_usd or 0.0 for r in runs)
    total_tokens = sum(run_tokens(r) for r in runs)
    rows = []
    for key, members in per.items():
        cost = sum(r.cost_usd or 0.0 for r in members)
        tokens = sum(run_tokens(r) for r in members)
        if total_cost > 0:
            share = cost / total_cost
        else:
            share = tokens / total_tokens if total_tokens else None
        g = groups[key]
        rows.append(
            BreakdownRow(
                id=g.id,
                name=g.name,
                color=g.color,
                cost_usd=round(cost, 6),
                tokens=tokens,
                sessions=len(members),
                share=share,
            )
        )
    rows.sort(key=lambda r: (r.cost_usd, r.tokens), reverse=True)
    return Breakdown(group=group, rows=rows)


def sessions(
    db: Session,
    first: date,
    last: date,
    *,
    agent_id: str | None = None,
    project_id: str | None = None,
    sort: str = "started_at",
    descending: bool = True,
    limit: int | None = 500,
    tz: tzinfo | None = None,
    now: datetime | None = None,
) -> list[SessionRow]:
    runs = runs_between(db, first, last, agent_id=agent_id, project_id=project_id, tz=tz)
    ids = {r.task_id for r in runs if r.task_id}
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(ids)))}
    moment = now or utcnow()
    rows = []
    for run in runs:
        task = tasks.get(run.task_id or "")
        rows.append(
            SessionRow(
                run_id=run.id,
                started_at=started(run),
                ended_at=run.ended_at,
                duration_seconds=duration(run, moment),
                agent_id=run.agent_id,
                agent_name=run.agent_name,
                agent_color=run.agent_color,
                project_id=run.project_id,
                project_name=run.project_name,
                task_id=run.task_id,
                task_code=task.code if task else None,
                task_title=task.title if task else None,
                cli=run.cli,
                model=_model_of(run),
                status=run.status,
                tokens=run_tokens(run),
                cost_usd=run.cost_usd,
                usage_status=run.usage_status,
            )
        )
    keys = {
        "started_at": lambda r: r.started_at or datetime.min.replace(tzinfo=UTC),
        "agent": lambda r: r.agent_name.lower(),
        "project": lambda r: r.project_name.lower(),
        "task": lambda r: (r.task_code or "", r.task_title or ""),
        "model": lambda r: r.model,
        "tokens": lambda r: r.tokens,
        "cost": lambda r: r.cost_usd if r.cost_usd is not None else -1.0,
        "duration": lambda r: r.duration_seconds or 0.0,
    }
    rows.sort(key=keys.get(sort, keys["started_at"]), reverse=descending)
    return rows[:limit] if limit else rows


def _model_of(run: Run) -> str:
    """The model the agent asked for, else the one the transcript names (the main one)."""
    if run.model:
        return run.model
    models = run.usage_models or {}
    if not models:
        return ""
    return max(models, key=lambda name: models[name].get("output_tokens", 0))


CSV_COLUMNS = (
    "inicio",
    "fin",
    "duracion_s",
    "agente",
    "proyecto",
    "tarea",
    "cli",
    "modelo",
    "estado",
    "tokens_entrada",
    "tokens_salida",
    "tokens_razonamiento",
    "cache_lectura",
    "cache_escritura",
    "tokens_total",
    "coste_usd",
    "consumo",
)


def sessions_csv(db: Session, rows: list[SessionRow]) -> str:
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.id.in_([r.run_id for r in rows])))}
    out = io.StringIO()
    out.write("﻿")  # Excel reads the accents right with a BOM
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        run = runs[row.run_id]
        writer.writerow(
            (
                row.started_at.astimezone().isoformat(timespec="seconds") if row.started_at else "",
                row.ended_at.astimezone().isoformat(timespec="seconds") if row.ended_at else "",
                round(row.duration_seconds) if row.duration_seconds is not None else "",
                row.agent_name,
                row.project_name,
                f"{row.task_code} {row.task_title}" if row.task_code else "",
                row.cli,
                row.model,
                row.status,
                run.input_tokens,
                run.output_tokens,
                run.thinking_tokens,
                run.cache_read_tokens,
                run.cache_creation_tokens,
                row.tokens,
                f"{row.cost_usd:.6f}" if row.cost_usd is not None else "",
                row.usage_status,
            )
        )
    return out.getvalue()
