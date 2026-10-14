"""Usage of the agents (phase 07): KPIs, daily series, breakdown, sessions, CSV, today and the
daily limits. Periods are local dates (`YYYY-MM-DD`), last 30 days by default."""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.schemas.usage import (
    Breakdown,
    DailySeries,
    LimitState,
    LimitsUpdate,
    SessionRow,
    TodayAgent,
    UsageSummary,
    UsageToday,
)
from agentic_os.services import accounts as account_ops
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.usage import stats, switching

router = APIRouter(tags=["usage"])
DbSession = Annotated[Session, Depends(get_session)]
MAX_DAYS = 366


def today() -> date:
    return datetime.now().astimezone().date()


class Period:
    def __init__(
        self,
        date_from: Annotated[date | None, Query(alias="from")] = None,
        date_to: Annotated[date | None, Query(alias="to")] = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        account_id: str | None = None,
    ) -> None:
        last = date_to or today()
        first = date_from or last - timedelta(days=29)
        if first > last:
            raise ApiError(422, "invalid_period", "'from' is after 'to'", "from")
        if (last - first).days >= MAX_DAYS:
            raise ApiError(422, "period_too_long", f"at most {MAX_DAYS} days", "from")
        self.first, self.last = first, last
        self.agent_id, self.project_id, self.account_id = agent_id, project_id, account_id


PeriodDep = Annotated[Period, Depends()]


@router.get("/usage/summary")
def get_summary(db: DbSession, period: PeriodDep) -> UsageSummary:
    return stats.summary(
        db,
        period.first,
        period.last,
        agent_id=period.agent_id,
        project_id=period.project_id,
        account_id=period.account_id,
    )


@router.get("/usage/daily")
def get_daily(
    db: DbSession, period: PeriodDep, group: Literal["agent", "project", "account"] = "agent"
) -> DailySeries:
    return stats.daily(
        db,
        period.first,
        period.last,
        group,
        agent_id=period.agent_id,
        project_id=period.project_id,
        account_id=period.account_id,
    )


@router.get("/usage/breakdown")
def get_breakdown(
    db: DbSession,
    period: PeriodDep,
    group: Literal["agent", "project", "task", "account"] = "agent",
) -> Breakdown:
    return stats.breakdown(
        db,
        period.first,
        period.last,
        group,
        agent_id=period.agent_id,
        project_id=period.project_id,
        account_id=period.account_id,
    )


SortKey = Literal["started_at", "agent", "project", "task", "model", "tokens", "cost", "duration"]


@router.get("/usage/sessions")
def get_sessions(
    db: DbSession,
    period: PeriodDep,
    sort: SortKey = "started_at",
    direction: Annotated[Literal["asc", "desc"], Query(alias="dir")] = "desc",
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[SessionRow]:
    return stats.sessions(
        db,
        period.first,
        period.last,
        agent_id=period.agent_id,
        project_id=period.project_id,
        account_id=period.account_id,
        sort=sort,
        descending=direction == "desc",
        limit=limit,
    )


@router.get("/usage/sessions.csv")
def get_sessions_csv(
    db: DbSession,
    period: PeriodDep,
    sort: SortKey = "started_at",
    direction: Annotated[Literal["asc", "desc"], Query(alias="dir")] = "desc",
) -> Response:
    rows = stats.sessions(
        db,
        period.first,
        period.last,
        agent_id=period.agent_id,
        project_id=period.project_id,
        account_id=period.account_id,
        sort=sort,
        descending=direction == "desc",
        limit=None,
    )
    name = f"consumo_{period.first.isoformat()}_{period.last.isoformat()}.csv"
    return Response(
        stats.sessions_csv(db, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/usage/today")
def get_today(db: DbSession) -> UsageToday:
    day = today()
    runs = stats.runs_between(db, day, day)
    total = stats.totals(runs)
    agents = stats.breakdown(db, day, day, "agent").rows
    return UsageToday(
        day=day,
        tokens=sum(stats.run_tokens(r) for r in runs),
        cache_read_tokens=total.cache_read_tokens,
        cost_usd=round(total.cost_usd or 0.0, 6),
        agents=[
            TodayAgent(id=a.id, name=a.name, color=a.color, cost_usd=a.cost_usd, tokens=a.tokens)
            for a in agents
        ],
        limits=usage_limits.states(db, day),
    )


@router.get("/settings/usage-limits")
def get_usage_limits(db: DbSession) -> list[LimitState]:
    """The daily limit of each account, with how far it is today."""
    return usage_limits.states(db, today())


class SwitchThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: int


@router.get("/settings/switch-threshold")
def get_switch_threshold(db: DbSession) -> SwitchThreshold:
    """The percent of a subscription window at which an agent with a secondary CLI asks."""
    return SwitchThreshold(threshold=switching.threshold(db))


@router.put("/settings/switch-threshold")
def put_switch_threshold(
    payload: SwitchThreshold, db: DbSession, request: Request
) -> SwitchThreshold:
    switching.set_threshold(db, payload.threshold)
    db.commit()
    request.app.state.scheduler.check_limits(force=True)
    return SwitchThreshold(threshold=switching.threshold(db))


@router.put("/settings/usage-limits")
def put_usage_limits(payload: LimitsUpdate, db: DbSession, request: Request) -> list[LimitState]:
    known = {a.id: a for a in account_ops.list_accounts(db)}
    for entry in payload.limits:
        account = known.get(entry.account_id)
        if account is None:
            raise NotFound("account")
        account_ops.set_daily_limit(account, entry.daily_limit)
    usage_limits.sync_limit_items(db, today())
    db.commit()
    request.app.state.scheduler.poke()  # a raised limit lets queued tasks start
    return usage_limits.states(db, today())
