from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from agentic_os.models.agent import MAX_CONCURRENCY, AgentStatus, Cli, PermissionMode, Tool

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Concurrency = Annotated[int, Field(ge=1, le=MAX_CONCURRENCY)]


def _unique_tools(tools: list[Tool] | None) -> list[Tool] | None:
    return None if tools is None else list(dict.fromkeys(tools))


def reject_null(value: object) -> object:
    """Fields are optional (omit them to leave them unchanged) but never nullable: the
    columns are NOT NULL. Runs only on values present in the request, not on defaults."""
    if value is None:
        raise ValueError("null is not allowed; omit the field to leave it unchanged")
    return value


class AgentFields(BaseModel):
    """Editable fields, all optional: shared by create (with template) and update."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    role: Short | None = None
    description: str | None = None
    color: Color | None = None
    cli: Cli | None = None
    model: Short | None = None
    instructions: str | None = None
    permission_mode: PermissionMode | None = None
    allowed_tools: list[Tool] | None = None
    max_concurrency: Concurrency | None = None
    can_spawn_subagents: bool | None = None
    can_create_tasks: bool | None = None
    can_propose_agents: bool | None = None  # phase 19: propose_agent
    status: AgentStatus | None = None
    # Phase 10. Unlike the other fields these may be null: no team, or the default account of
    # its CLI. Omit them to leave them unchanged.
    team_id: str | None = None
    account_id: str | None = None
    # The secondary CLI: an account (it fixes the CLI) and a model. Null/empty: none.
    fallback_account_id: str | None = None
    fallback_model: Short | None = None

    _dedupe_tools = field_validator("allowed_tools")(_unique_tools)
    _no_nulls = field_validator(
        "name",
        "role",
        "description",
        "color",
        "cli",
        "model",
        "instructions",
        "permission_mode",
        "allowed_tools",
        "max_concurrency",
        "fallback_model",
        "can_spawn_subagents",
        "can_create_tasks",
        "can_propose_agents",
        "status",
        mode="before",
    )(reject_null)


class AgentCreate(AgentFields):
    template: str | None = None


class AgentUpdate(AgentFields):
    pass


class TemplateFromAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: str | None = None
    color: Color | None = None


class AgentImport(BaseModel):
    """An exported agent (`agentic-os.agent` v1) and what to change on the way in."""

    model_config = ConfigDict(extra="forbid")

    payload: dict
    name: Name | None = None
    account_id: str | None = None
    team_id: str | None = None


class ImportPreview(BaseModel):
    agent: dict
    missing_skills: list[str]
    missing_connections: list[str]
    missing_knowledge: list[str]
    own_skills: list[str]
    cli_installed: bool


class Imported(BaseModel):
    agent: "AgentRead"
    notes: list[str]


class AgentDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    description: str
    color: str
    cli: Cli
    model: str
    instructions: str
    permission_mode: PermissionMode
    allowed_tools: list[Tool]
    max_concurrency: int
    can_spawn_subagents: bool
    can_create_tasks: bool
    can_propose_agents: bool = False
    status: AgentStatus
    template: str | None
    # Phase 19: the proposal a draft comes from (the Architect or propose_agent).
    proposal_id: str | None = None
    team_id: str | None = None
    account_id: str | None = None
    fallback_account_id: str | None = None
    fallback_model: str = ""
    # Computed: the agent is running with its secondary CLI right now.
    using_fallback: bool = False
    created_at: datetime
    updated_at: datetime
    # Its queue (phase 05): tasks waiting for it and tasks it is working on.
    queued_count: int = 0
    running_count: int = 0


class AgentTemplate(BaseModel):
    id: str
    # Phase 19: one the person saved (it can be edited and deleted), with what it brings along.
    own: bool = False
    skills: int = 0
    connections: int = 0
    documents: int = 0
    name: str
    role: str
    description: str
    color: str
    cli: Cli
    model: str
    instructions: str
    permission_mode: PermissionMode
    allowed_tools: list[Tool]
    can_spawn_subagents: bool
    can_create_tasks: bool


Imported.model_rebuild()
