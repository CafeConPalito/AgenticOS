from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

StageName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class StageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None  # an existing stage keeps its id (tasks point at it)
    name: StageName
    agent_id: str | None = None
    requires_review: bool = False
    # Index, in this same list, of an earlier stage the task goes back to when this one rejects.
    reject_to: int | None = None


class PipelineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""
    max_rejections: Annotated[int, Field(ge=1, le=10)] = 3
    stages: Annotated[list[StageWrite], Field(min_length=1, max_length=12)]


class PipelineTemplate(StrEnum):
    WEB = "web"


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: PipelineTemplate


class StageRead(BaseModel):
    id: str
    position: int
    name: str
    agent_id: str | None
    agent_name: str | None
    agent_color: str | None
    requires_review: bool
    reject_to_stage_id: str | None
    active_tasks: int  # tasks that are at this stage and not finished


class PipelineRead(BaseModel):
    id: str
    project_id: str
    name: str
    max_rejections: int
    stages: list[StageRead]
