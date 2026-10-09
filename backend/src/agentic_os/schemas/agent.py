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


class AgentCreate(AgentFields):
    template: str | None = None


class AgentUpdate(AgentFields):
    pass


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
