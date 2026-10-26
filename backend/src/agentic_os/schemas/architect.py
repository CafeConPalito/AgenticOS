"""The Architect's API (phase 19, plan §7): conversations, their messages and sheet, proposals
and Ajustes › Arquitecto."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentic_os.models import ArchitectMode

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ArchitectMode = ArchitectMode.AGENT
    agent_id: str | None = None  # improve_agent
    team_id: str | None = None  # improve_team
    project_id: str | None = None  # improve_pipeline
    # agent: go on from a pending proposal of a new agent (one propose_agent made).
    proposal_id: str | None = None


class MessageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Text


class SheetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: dict[str, Any]
    agent_ref: str = "main"


class Unlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str]


class Reset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clear_sheet: bool = False


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    text: str
    tool_events: list[dict]
    created_at: datetime


class SheetRead(BaseModel):
    sheet: dict
    issues: list[dict]
    progress: dict[str, int]
    ready: bool
    locked: list[str]
    refused: dict[str, str] = {}


class ConversationSummary(BaseModel):
    id: str
    mode: str
    title: str
    status: str
    state: str  # starting · thinking · idle · asleep
    agent_id: str | None
    team_id: str | None
    project_id: str | None
    proposal_id: str | None
    updated_at: datetime


class ConversationRead(ConversationSummary):
    cli: str | None
    model: str
    run_id: str | None
    messages: list[MessageRead]
    sheet: SheetRead


class FieldChangeRead(BaseModel):
    field: str
    before: Any
    after: Any
    current: Any
    conflict: bool
    diff: str = ""


class SkillDraftRead(BaseModel):
    id: str
    name: str
    description: str


class ProposalRead(BaseModel):
    id: str
    kind: str
    origin: str
    status: str
    reason: str
    conversation_id: str | None
    source_agent_id: str | None
    source_run_id: str | None
    source_task_id: str | None
    target_agent_id: str | None
    target_team_id: str | None
    target_project_id: str | None
    sheet: dict | None = None  # what a new agent was proposed with
    changes: list[FieldChangeRead] = []
    new_skills: list[SkillDraftRead] = []
    applied_fields: list[str] = []
    created_at: datetime
    decided_at: datetime | None


class Approve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str] | None = None  # changes: those to apply (all by default)
    choices: dict[str, Literal["proposed", "current"]] = {}  # a field in conflict
    skip_skills: list[str] = []  # skills written for it that are not wanted


class Reject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archive: bool = False  # a new agent: keep it archived instead of deleting it


class Applied(BaseModel):
    proposal: ProposalRead
    notes: list[str]


class AgentChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str  # user · architect · agent · import
    proposal_id: str | None
    conversation_id: str | None
    fields: dict
    created_at: datetime


class ArchitectSettingsRead(BaseModel):
    cli: str
    account_id: str
    model: str
    instructions: str
    default_instructions: str
    idle_minutes: int
    max_live: int


class ArchitectSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cli: Literal["", "claude", "agy"] | None = None
    account_id: str | None = None
    model: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    instructions: Annotated[str, StringConstraints(max_length=40_000)] | None = None
    idle_minutes: Annotated[int, Field(ge=1, le=240)] | None = None
    max_live: Annotated[int, Field(ge=1, le=5)] | None = None
