from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentic_os.models.account import SessionState
from agentic_os.models.agent import Cli

Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cli: Cli
    label: Label = ""


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Label | None = None
    # USD for Claude Code, tokens for agy. Send null to remove the limit.
    daily_limit: Annotated[float, Field(gt=0, le=10**12)] | None = None


class QuotaWindowRead(BaseModel):
    id: str  # five_hour, seven_day (Claude) · gemini-5h, 3p-weekly… (agy)
    used_pct: float
    resets_at: datetime
    read_at: datetime
    # The window ended since it was read: 0 % until a session reads it again.
    expired: bool


class AccountAgent(BaseModel):
    id: str
    name: str
    color: str


class AccountRead(BaseModel):
    id: str
    cli: Cli
    label: str
    name: str  # what the UI shows: the email once known, else the label
    email: str
    plan: str
    is_default: bool
    is_system: bool
    session_state: SessionState
    session_checked_at: datetime | None
    daily_limit: float | None
    unit: str  # "usd" | "tokens"
    used_today: float
    quota: list[QuotaWindowRead]
    agents: list[AccountAgent]
    live_runs: int
