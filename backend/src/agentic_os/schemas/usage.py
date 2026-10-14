from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from agentic_os.models.run import UsageStatus


class UsageTotals(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    # Null when none of the runs has a cost (agy only records tokens).
    cost_usd: float | None = None

    @property
    def tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.thinking_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


class RunUsage(UsageTotals):
    source: str | None = None
    status: UsageStatus = UsageStatus.PENDING
    cli_version: str | None = None
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    read_at: datetime | None = None


class AccountLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    # USD for Claude Code, tokens for agy. Null: no limit.
    daily_limit: Annotated[float, Field(gt=0, le=10**12)] | None = None


class LimitsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limits: list[AccountLimit]


class LimitState(BaseModel):
    account_id: str
    account_name: str
    is_default: bool
    cli: str
    unit: str  # "usd" | "tokens"
    limit: float | None
    used: float
    ratio: float | None  # used / limit
    reached: bool
    near: bool  # ≥ 80 %
    quota_exhausted: bool  # a «Cuota agotada» is pending for this account


class Kpis(BaseModel):
    cost_usd: float
    cost_change: float | None  # vs. the previous period of the same length (0.12 = +12 %)
    tokens: int
    cache_ratio: float | None  # share of the input served from cache
    agent_hours: float
    sessions: int
    success_ratio: float | None  # sessions that ended without an error


class UsageSummary(BaseModel):
    date_from: date
    date_to: date
    kpis: Kpis


class Group(BaseModel):
    id: str | None
    name: str
    color: str


class DailyPoint(BaseModel):
    day: date
    # By group id: cost (USD) and tokens of the day.
    cost: dict[str, float]
    tokens: dict[str, int]


class DailySeries(BaseModel):
    group: str  # "agent" | "project"
    groups: list[Group]
    days: list[DailyPoint]


class BreakdownRow(BaseModel):
    id: str | None
    name: str
    color: str
    cost_usd: float
    tokens: int
    sessions: int
    share: float | None  # of the period's cost (or tokens when nothing has a cost)


class Breakdown(BaseModel):
    group: str
    rows: list[BreakdownRow]


class SessionRow(BaseModel):
    run_id: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    agent_id: str | None
    agent_name: str
    agent_color: str
    project_id: str | None
    project_name: str
    task_id: str | None
    task_code: str | None
    task_title: str | None
    cli: str
    model: str
    status: str
    tokens: int
    cost_usd: float | None
    usage_status: UsageStatus


class TodayAgent(BaseModel):
    id: str | None
    name: str
    color: str
    cost_usd: float
    tokens: int


class UsageToday(BaseModel):
    day: date
    tokens: int
    cache_read_tokens: int
    cost_usd: float
    agents: list[TodayAgent]
    limits: list[LimitState]
