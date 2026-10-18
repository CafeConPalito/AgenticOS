from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"
    # Only a task that forked (phase 13): it has no agent and no queue place, its lanes work for it.
    DECIDING = "deciding"  # the branches of its fork are being chosen
    FORKED = "forked"  # waiting for the lanes it started


FINISHED_TASK_STATUSES = (TaskStatus.DONE, TaskStatus.CANCELLED)


class Priority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


PRIORITY_RANK = {Priority.HIGH: 0, Priority.NORMAL: 1, Priority.LOW: 2}


class WaitingReason(StrEnum):
    """Why a task waits for the user («Esperando humano»)."""

    RUN_EXITED = "run_exited"  # the CLI ended without complete_task
    RUN_FAILED = "run_failed"
    RUN_STOPPED = "run_stopped"
    INTERRUPTED = "interrupted"  # the backend restarted during the run
    MAX_REJECTIONS = "max_rejections"
    LAUNCH_FAILED = "launch_failed"
    NO_AGENT = "no_agent"  # its stage (or the task) has no agent
    WORKSPACE_FAILED = "workspace_failed"
    HUMAN_REQUEST = "human_request"  # the agent asked something (request_human)
    PERMISSION = "permission"  # a permission dialog of the CLI waits
    # The agent asked (request_human) and its CLI is gone: the answer starts a new run.
    QUESTION_PENDING = "question_pending"
    QUOTA = "quota"  # the CLI ran out of its account quota (phase 07)
    CHOOSE_BRANCH = "choose_branch"  # nobody could pick the branches of a fork (phase 13)
    JOIN_CONFLICT = "join_conflict"  # the lanes' git branches clash where they meet
    LANES_CANCELLED = "lanes_cancelled"  # every lane of a fork was cancelled


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


class Task(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """A unit of work for the agents, queued on the agent of its current stage."""

    __tablename__ = "tasks"
    __table_args__ = (
        # A lane (phase 13) shares the number of the task that forked: T-142, T-142·backend…
        UniqueConstraint("workspace_id", "number", "lane_key", name="uq_tasks_workspace_number"),
        CheckConstraint(_in("status", TaskStatus), name="status"),
        CheckConstraint(_in("priority", Priority), name="priority"),
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)  # shown as T-<number>
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default=Priority.NORMAL)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=TaskStatus.BACKLOG)
    # Null without a pipeline: the task then has a single implicit stage, its agent.
    stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The agent whose queue holds the task (its current stage's agent, or the assigned one).
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waiting_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    waiting_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The task's work folder (phase 12: one worktree per repository inside it, see TaskRepo).
    worktree_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # A subtask (create_subtask): the task whose agent created it.
    parent_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # A task made to resolve the conflicts of integrating another one.
    resolves_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Lanes of a forked task (phase 13): each branch taken is a task of its own, a child of the
    # one that forked, that goes through the branch's stages (ADR 0020).
    lane_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    lane_link_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stage_links.id", ondelete="SET NULL"), nullable=True
    )
    fork_stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    lane_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # Branches fixed by hand when the task was created: {fork stage id: [link id, …]}.
    preset_lanes: Mapped[dict[str, list[str]]] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def code(self) -> str:
        base = f"T-{self.number}"
        return f"{base}·{self.lane_key}" if self.lane_key else base

    @property
    def ref_name(self) -> str:
        """The code as a git branch or folder name (no «·»)."""
        base = f"T-{self.number}"
        return f"{base}-{self.lane_key.replace('.', '-')}" if self.lane_key else base


class TaskEventKind(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    REJECTED = "rejected"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    WAITING_HUMAN = "waiting_human"
    RETRIED = "retried"
    COMPLETED_MANUALLY = "completed_manually"
    CANCELLED = "cancelled"
    DONE = "done"
    WORKSPACE = "workspace"  # worktree created, removed or failing
    HUMAN_REQUEST = "human_request"  # the agent asked (request_human)
    HUMAN_ANSWERED = "human_answered"  # the person answered
    SUBTASK = "subtask"  # the agent created a subtask
    GIT = "git"  # a run did something with git (commits, branches, pushes)
    INTEGRATED = "integrated"  # the task's branches were brought into their bases
    DECISION = "decision"  # the branches of a fork were chosen (phase 13)
    LANE_STARTED = "lane_started"
    LANE_FINISHED = "lane_finished"
    LANE_ADDED = "lane_added"  # the user added a branch to a running fork
    LANE_CANCELLED = "lane_cancelled"
    JOINED = "joined"  # the lanes met again


class TaskEvent(IdMixin, Base):
    """The history of a task: what each stage did, verdicts, reviews and user actions."""

    __tablename__ = "task_events"
    __table_args__ = (CheckConstraint(_in("kind", TaskEventKind), name="kind"),)

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Order within the task: several events can share a timestamp (one transaction, and a
    # Windows clock that ticks every ~15 ms).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    stage_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DecisionBy(StrEnum):
    MODEL = "model"  # the decider
    USER = "user"
    ALWAYS = "always"  # every branch was «always»
    PRESET = "preset"  # fixed when the task was created


class BranchDecision(IdMixin, Base):
    """Which branches a task took at a fork, who decided and why."""

    __tablename__ = "branch_decisions"
    __table_args__ = (CheckConstraint(_in("decided_by", DecisionBy), name="decided_by"),)

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fork_stage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False
    )
    # The decider's run (its usage), when the model decided.
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    decided_by: Mapped[str] = mapped_column(String(8), nullable=False)
    # Proposed: waits for the person to confirm it (Stage.confirm_decision).
    proposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chosen: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)  # link ids
    reasons: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
