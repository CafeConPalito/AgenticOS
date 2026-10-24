"""Usage statistics of the skills (phase 17, block 10; spec E): which skills are used most, where
and with what result. One aggregate query over `run_skills` ⋈ `runs` ⋈ `skills`; the names copied
on both keep the figures of a deleted agent, stage, pipeline, team or account (CA21)."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Run, RunSkill, RunStatus, Skill, SkillReview, SkillVersion, Verdict
from agentic_os.services.usage.stats import day_bounds, local_day

GROUPS = ("agent", "team", "project", "pipeline", "stage", "cli", "account", "model")
METRICS = (
    "offered",
    "loaded",
    "rate",
    "runs",
    "tasks",
    "done",
    "failed",
    "approved",
    "rejected",
    "avg_cost",
    "avg_tokens",
    "last_used",
    "via_context",
    "via_tool",
    "via_native",
    "name",
)


@dataclass
class Filters:
    first: date | None = None
    last: date | None = None
    agent_id: str | None = None
    team_id: str | None = None
    project_id: str | None = None
    pipeline_id: str | None = None
    stage_id: str | None = None
    cli: str | None = None
    account_id: str | None = None
    model: str | None = None
    scope: str | None = None
    origin: str | None = None
    via: str | None = None
    unused: str | None = None  # never_loaded · never_offered
    skill_id: str | None = None


@dataclass
class Row:
    skill_id: str
    name: str
    scope: str
    origin: str
    group_key: str | None = None
    group_label: str = ""
    offered: int = 0
    loaded: int = 0
    rate: float | None = None
    runs: int = 0
    tasks: int = 0
    done: int = 0
    failed: int = 0
    approved: int = 0
    rejected: int = 0
    avg_cost: float | None = None
    avg_tokens: float | None = None
    last_used: datetime | None = None
    via_context: int = 0
    via_tool: int = 0
    via_native: int = 0


@dataclass
class Table:
    rows: list[Row] = field(default_factory=list)
    total: int = 0


def _group_columns(group: str | None):
    """(key, label) of a breakdown: the id when there is one, else the copied name."""
    if group is None:
        return None, None
    return {
        "agent": (func.coalesce(Run.agent_id, Run.agent_name), Run.agent_name),
        "team": (func.coalesce(RunSkill.team_id, RunSkill.team_name), RunSkill.team_name),
        "project": (func.coalesce(Run.project_id, Run.project_name), Run.project_name),
        "pipeline": (
            func.coalesce(RunSkill.pipeline_id, RunSkill.pipeline_name),
            RunSkill.pipeline_name,
        ),
        "stage": (RunSkill.stage_name, RunSkill.stage_name),
        "cli": (Run.cli, Run.cli),
        "account": (func.coalesce(Run.account_id, Run.account_label), Run.account_label),
        "model": (Run.model, Run.model),
    }[group]


def _conditions(f: Filters) -> list:
    when = func.coalesce(Run.started_at, Run.created_at)
    conds = [Skill.workspace_id == DEFAULT_WORKSPACE]
    if f.first or f.last:
        start, end = day_bounds(f.first or date(2000, 1, 1), f.last or date(2100, 1, 1))
        conds += [when >= start, when < end]
    for column, value in (
        (Run.agent_id, f.agent_id),
        (RunSkill.team_id, f.team_id),
        (Run.project_id, f.project_id),
        (RunSkill.pipeline_id, f.pipeline_id),
        (Run.stage_id, f.stage_id),
        (Run.cli, f.cli),
        (Run.account_id, f.account_id),
        (Run.model, f.model),
        (Skill.scope, f.scope),
        (Skill.origin, f.origin),
        (RunSkill.loaded_via, f.via),
        (Skill.id, f.skill_id),
    ):
        if value:
            conds.append(column == value)
    return conds


def table(
    db: Session,
    f: Filters,
    group: str | None = None,
    sort: str = "loaded",
    desc: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> Table:
    loaded = RunSkill.loaded_via.is_not(None)
    key, label = _group_columns(group)

    def count_if(condition):
        return func.sum(case((condition, 1), else_=0))

    columns = [
        Skill.id,
        Skill.name,
        Skill.scope,
        Skill.origin,
        count_if(RunSkill.offered != "requested").label("offered"),
        count_if(loaded).label("loaded"),
        count_if(and_(loaded, RunSkill.offered != "requested")).label("loaded_offered"),
        func.count(func.distinct(case((loaded, RunSkill.run_id)))).label("runs"),
        func.count(func.distinct(case((loaded, Run.task_id)))).label("tasks"),
        count_if(and_(loaded, Run.status == RunStatus.COMPLETED)).label("done"),
        count_if(and_(loaded, Run.status == RunStatus.FAILED)).label("failed"),
        count_if(and_(loaded, Run.verdict == Verdict.APPROVED)).label("approved"),
        count_if(and_(loaded, Run.verdict == Verdict.REJECTED)).label("rejected"),
        func.avg(case((loaded, Run.cost_usd))).label("avg_cost"),
        func.avg(case((loaded, Run.input_tokens + Run.output_tokens))).label("avg_tokens"),
        func.max(RunSkill.loaded_at).label("last_used"),
        count_if(RunSkill.loaded_via == "context").label("via_context"),
        count_if(RunSkill.loaded_via == "tool").label("via_tool"),
        count_if(RunSkill.loaded_via == "native").label("via_native"),
    ]
    group_by = [Skill.id]
    if key is not None:
        columns += [key.label("group_key"), func.max(label).label("group_label")]
        group_by.append(key)
    query = (
        select(*columns)
        .select_from(RunSkill)
        .join(Run, Run.id == RunSkill.run_id)
        .join(Skill, Skill.id == RunSkill.skill_id)
        .where(*_conditions(f))
        .group_by(*group_by)
    )
    rows = [
        Row(
            skill_id=r.id,
            name=r.name,
            scope=r.scope,
            origin=r.origin,
            group_key=getattr(r, "group_key", None),
            group_label=getattr(r, "group_label", "") or "",
            offered=r.offered or 0,
            loaded=r.loaded or 0,
            rate=round(r.loaded_offered / r.offered, 4) if r.offered else None,
            runs=r.runs or 0,
            tasks=r.tasks or 0,
            done=r.done or 0,
            failed=r.failed or 0,
            approved=r.approved or 0,
            rejected=r.rejected or 0,
            avg_cost=round(r.avg_cost, 6) if r.avg_cost is not None else None,
            avg_tokens=round(r.avg_tokens, 1) if r.avg_tokens is not None else None,
            last_used=r.last_used,
            via_context=r.via_context or 0,
            via_tool=r.via_tool or 0,
            via_native=r.via_native or 0,
        )
        for r in db.execute(query)
    ]
    if f.unused:
        # «never offered»: no row at all in the filtered runs; «never loaded»: offered but never
        # loaded, plus those (spec E: to clean the library up).
        missing = _without_rows(db, f, {r.skill_id for r in rows}) if group is None else []
        rows = missing if f.unused == "never_offered" else [r for r in rows if r.loaded == 0]
        if f.unused == "never_loaded":
            rows += missing
    if sort not in METRICS:
        sort = "loaded"

    def key_of(row: Row):
        value = getattr(row, sort)
        missing = value is None
        if isinstance(value, datetime):
            value = value.timestamp()
        if isinstance(value, str):
            value = value.lower()
        return (missing, value if not missing else 0)

    rows.sort(key=lambda r: r.name.lower())
    rows.sort(key=key_of, reverse=desc)
    if desc:  # empty values last either way
        rows.sort(key=lambda r: getattr(r, sort) is None)
    return Table(rows[offset : offset + limit], len(rows))


def _without_rows(db: Session, f: Filters, seen: set[str]) -> list[Row]:
    """The skills with no figure in the filtered runs (to clean the library up)."""
    query = select(Skill).where(
        Skill.workspace_id == DEFAULT_WORKSPACE, Skill.review == SkillReview.NONE
    )
    if f.scope:
        query = query.where(Skill.scope == f.scope)
    if f.origin:
        query = query.where(Skill.origin == f.origin)
    return [Row(s.id, s.name, s.scope, s.origin) for s in db.scalars(query) if s.id not in seen]


def daily(db: Session, f: Filters, skill_ids: list[str]) -> list[dict]:
    """Loads per local day for the chosen skills, every day of the period present."""
    query = (
        select(RunSkill.skill_id, RunSkill.loaded_at)
        .join(Run, Run.id == RunSkill.run_id)
        .join(Skill, Skill.id == RunSkill.skill_id)
        .where(*_conditions(f), RunSkill.loaded_via.is_not(None))
    )
    if skill_ids:
        query = query.where(RunSkill.skill_id.in_(skill_ids))
    counts: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for skill_id, at in db.execute(query):
        counts[local_day(at)][skill_id] += 1
    if not counts and not (f.first and f.last):
        return []
    first = f.first or min(counts)
    last = f.last or max(counts)
    days, day = [], first
    while day <= last:
        days.append({"day": day.isoformat(), "loads": dict(counts.get(day, {}))})
        day += timedelta(days=1)
    return days


def runs(db: Session, f: Filters, group: str | None, group_key: str | None, limit: int = 200):
    """The runs behind one figure (a skill, maybe one group of it), newest first."""
    key, _ = _group_columns(group)
    query = (
        select(RunSkill, Run, SkillVersion.number)
        .join(Run, Run.id == RunSkill.run_id)
        .join(Skill, Skill.id == RunSkill.skill_id)
        .outerjoin(SkillVersion, SkillVersion.id == RunSkill.version_id)
        .where(*_conditions(f))
        .order_by(func.coalesce(Run.started_at, Run.created_at).desc())
        .limit(limit)
    )
    if key is not None and group_key is not None:
        query = query.where(key == group_key)
    return list(db.execute(query))


HEADERS = {
    "name": "Skill",
    "group_label": "Grupo",
    "offered": "Ofrecida",
    "loaded": "Cargada",
    "rate": "Tasa de uso",
    "runs": "Ejecuciones",
    "tasks": "Tareas",
    "done": "Terminadas",
    "failed": "Fallidas",
    "approved": "Aprobadas",
    "rejected": "Rechazadas",
    "avg_cost": "Coste medio (USD)",
    "avg_tokens": "Tokens medios",
    "last_used": "Última vez",
    "via_context": "Por contexto",
    "via_tool": "Por use_skill",
    "via_native": "Nativa",
}


def to_csv(rows: list[Row], grouped: bool) -> str:
    buffer = io.StringIO()
    keys = [k for k in HEADERS if grouped or k != "group_label"]
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([HEADERS[k] for k in keys])
    for row in rows:
        values = []
        for k in keys:
            value = getattr(row, k)
            if isinstance(value, datetime):
                value = value.astimezone().strftime("%Y-%m-%d %H:%M")
            elif isinstance(value, float):
                value = f"{value:.4f}".replace(".", ",")
            values.append("" if value is None else value)
        writer.writerow(values)
    return "﻿" + buffer.getvalue()  # the BOM makes Excel read UTF-8
