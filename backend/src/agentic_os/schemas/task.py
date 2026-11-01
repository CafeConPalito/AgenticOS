from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from agentic_os.models.task import Priority, TaskEventKind, TaskStatus, WaitingReason
from agentic_os.schemas.agent import reject_null
from agentic_os.schemas.usage import UsageTotals

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(max_length=20_000)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8_000)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: Title
    description: Description = ""
    priority: Priority = Priority.NORMAL
    # Only for projects without pipeline (with one, the first stage decides).
    agent_id: str | None = None
    # False: the task stays in the backlog until it is queued.
    enqueue: bool = True
    # Branches fixed by hand for the forks of the pipeline: {fork stage id: [link id, …]}; the
    # decider is not asked about those forks (phase 13).
    preset_lanes: dict[str, list[str]] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Description | None = None
    priority: Priority | None = None
    agent_id: str | None = None

    _no_nulls = field_validator("title", "description", "priority", "agent_id", mode="before")(
        reject_null
    )


class LaneRead(BaseModel):
    """A branch a task took at a fork: a task of its own (phase 13)."""

    id: str
    code: str  # T-142·backend
    lane_key: str
    name: str  # the branch's name
    status: TaskStatus
    stage_id: str | None
    stage_name: str | None
    agent_id: str | None = None  # phase 20: for its avatar
    agent_name: str | None
    agent_color: str | None
    waiting_reason: WaitingReason | None
    link_id: str | None
    fork_stage_id: str | None


class TaskRead(BaseModel):
    id: str
    code: str  # T-142
    number: int
    project_id: str
    project_name: str
    project_color: str
    title: str
    description: str
    priority: Priority
    status: TaskStatus
    stage_id: str | None
    stage_name: str | None
    stage_index: int  # 1-based; 0 without pipeline
    stage_count: int
    requires_review: bool
    agent_id: str | None
    agent_name: str | None
    agent_color: str | None
    queue_position: int
    rejections: int
    waiting_reason: WaitingReason | None
    waiting_detail: str | None
    worktree_path: str | None
    branch: str | None
    # A queued task that cannot start now even with a free agent: "folder_busy", or the reason
    # its agent's account is held: "limit" (daily limit), "quota" or "session" (logged out), or
    # "decision" (its agent waits for the person to choose between its CLIs).
    blocked: str | None
    # The account behind "limit", "quota" and "session" (its name, for the UI).
    blocked_by: str | None = None
    active_run_id: str | None
    last_run_id: str | None
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    parent_task_id: str | None = None
    parent_code: str | None = None
    subtasks_done: int = 0
    subtasks_total: int = 0
    # Every run of the task, its subagents included (phase 07).
    usage: UsageTotals = Field(default_factory=UsageTotals)
    # Branches (phase 13). A task that forked shows the state of its most pressing lane in
    # `status`; `phase` says it is "deciding" its branches or has "forked" into `lanes`.
    phase: str | None = None
    lane_of_id: str | None = None
    lane_name: str | None = None
    fork_stage_id: str | None = None
    lanes: list[LaneRead] = Field(default_factory=list)
    # Phase 24 (ADR 0030): «Terminar aquí». The exit of the stage the task is at (its
    # condition), and where the task ended if an exit ended it.
    stage_exit_condition: str | None = None
    exit_stage_id: str | None = None
    exit_stage_name: str | None = None
    # Phase 24: how the task is worked (its root's for a lane) and the folder of its spec.
    work_mode: str | None = None
    work_mode_reason: str | None = None
    spec_path: str | None = None


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    at: datetime
    kind: TaskEventKind
    stage_name: str | None
    agent_name: str | None
    run_id: str | None
    detail: str


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: Summary


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=8_000)] = ""
    target_stage_id: str | None = None


class ClashRead(BaseModel):
    """A lane whose branch cannot be merged into its parent's in one repository."""

    repo_id: str
    name: str
    lane: str
    files: list[str]


class WorkModeRequest(BaseModel):
    """Phase 24: the person changes how the task is worked (SDD or direct)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["sdd", "direct"]


class DecisionRequest(BaseModel):
    """The person picks the branches of a fork (by the ids of its links)."""

    model_config = ConfigDict(extra="forbid")

    chosen: Annotated[list[str], Field(min_length=1, max_length=30)]


class AddLaneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    at: datetime
    fork_stage_id: str
    decided_by: str
    proposed: bool
    chosen: list[str]
    reasons: dict[str, str]
    error: str | None
    run_id: str | None


class QueueOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_ids: list[str]


class AgentQueue(BaseModel):
    agent_id: str
    running: list[TaskRead]
    queued: list[TaskRead]


class TreeNode(BaseModel):
    """A node of a task's execution tree: a run (with a terminal) or a native subagent."""

    kind: str  # "run" or "native"
    id: str  # run id, or the native subagent's id
    label: str  # agent name / subagent description
    color: str | None = None
    stage_name: str | None = None
    status: str  # run status, or "running" / "done" for a native subagent
    started_at: datetime | None = None
    ended_at: datetime | None = None
    children: list["TreeNode"] = []


class SchedulerState(BaseModel):
    paused: bool
    queued: int
    running: int
    waiting_human: int
    review: int
