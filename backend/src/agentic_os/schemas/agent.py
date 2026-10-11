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
    status: AgentStatus | None = None

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
        "can_spawn_subagents",
        "can_create_tasks",
        "status",
        mode="before",
    )(reject_null)


class AgentCreate(AgentFields):
    template: str | None = None


class AgentUpdate(AgentFields):
    pass


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
    status: AgentStatus
    template: str | None
    created_at: datetime
    updated_at: datetime
    # Its queue (phase 05): tasks waiting for it and tasks it is working on.
    queued_count: int = 0
    running_count: int = 0


class AgentTemplate(BaseModel):
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
    can_spawn_subagents: bool
    can_create_tasks: bool
