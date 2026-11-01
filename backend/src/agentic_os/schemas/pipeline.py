from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

StageName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
BranchName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
MAX_STAGES = 30


class StageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None  # an existing stage keeps its id (tasks point at it)
    name: StageName
    agent_id: str | None = None
    requires_review: bool = False
    # Index, in this same list, of an earlier stage the task goes back to when this one rejects.
    reject_to: int | None = None
    # Other stages (indexes) it can also send tasks back to: after a join, to the branch that
    # failed. The agent says which one when it rejects.
    reject_also: Annotated[list[int], Field(max_length=MAX_STAGES)] = []
    # Place on the canvas (null: the editor's automatic layout, or where it already was).
    x: int | None = None
    y: int | None = None
    # If the stage forks, its decision waits for the person to confirm it.
    confirm_decision: bool = False
    # Phase 24: «Terminar aquí». Null: no exit; text: the condition the decider evaluates (an
    # empty one is refused by the graph rules). The «Fin» node's place (null: beside the stage).
    exit_condition: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
    ) = None
    exit_x: int | None = None
    exit_y: int | None = None


class LinkWrite(BaseModel):
    """A link between two stages of the same save, by their index in `stages`. A stage with
    several links is a fork: each link is a branch with a name and a condition (or «always»)."""

    model_config = ConfigDict(extra="forbid")

    source: int
    target: int
    name: BranchName = ""
    condition: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    always: bool = False


class PipelineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""
    max_rejections: Annotated[int, Field(ge=1, le=10)] = 3
    stages: Annotated[list[StageWrite], Field(min_length=1, max_length=MAX_STAGES)]
    # Null: a chain, each stage linked to the next one (what every pipeline was before phase 13).
    links: Annotated[list[LinkWrite], Field(max_length=MAX_STAGES * 2)] | None = None
    # Who decides the branches of a fork (null: the first CLI with a live session).
    decider_cli: Literal["claude", "agy"] | None = None
    decider_account_id: str | None = None
    decider_model: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None
    ) = None


class PipelineTemplate(StrEnum):
    WEB = "web"
    WEB_SPLIT = "web_split"


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: PipelineTemplate


class GraphIssue(BaseModel):
    """A problem of the graph being edited; indexes point into the payload's lists."""

    code: str
    stage: int | None = None
    link: int | None = None


class PreviewBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: BranchName
    condition: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class PreviewRequest(BaseModel):
    """«Probar»: an example task and the branches of a fork as they are being edited."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(max_length=5_000)] = ""
    branches: Annotated[list[PreviewBranch], Field(max_length=MAX_STAGES)] = []
    # Phase 24: the stage's «Terminar aquí» (its condition) and name, to try the exit too.
    exit_condition: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None
    stage_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""
    decider_cli: Literal["claude", "agy"] | None = None
    decider_account_id: str | None = None
    decider_model: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None
    ) = None

    @model_validator(mode="after")
    def _something_to_ask(self) -> "PreviewRequest":
        if len(self.branches) < 2 and self.exit_condition is None:
            raise ValueError("try a fork (two branches or more) or an exit")
        return self


class PreviewBranchResult(BaseModel):
    name: str
    take: bool
    reason: str


class PreviewRead(BaseModel):
    branches: list[PreviewBranchResult]
    exit: PreviewBranchResult | None = None  # phase 24: whether the task would end there
    cli: str | None
    model: str | None
    cost_usd: float | None
    seconds: float
    error: str | None


class StageRead(BaseModel):
    id: str
    position: int
    name: str
    agent_id: str | None
    agent_name: str | None
    agent_color: str | None
    requires_review: bool
    reject_to_stage_id: str | None
    reject_extra_stage_ids: list[str]
    x: int
    y: int
    confirm_decision: bool
    exit_condition: str | None = None  # phase 24: «Terminar aquí»
    exit_x: int | None = None
    exit_y: int | None = None
    join_stage_id: str | None  # for a fork: the stage where its branches meet
    active_tasks: int  # tasks that are at this stage and not finished


class LinkRead(BaseModel):
    id: str
    from_stage_id: str
    to_stage_id: str
    name: str
    condition: str
    always: bool
    position: int


class PipelineRead(BaseModel):
    id: str
    project_id: str
    name: str
    max_rejections: int
    decider_cli: str | None
    decider_account_id: str | None
    decider_model: str | None
    stages: list[StageRead]
    links: list[LinkRead]
