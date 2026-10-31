from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow


class RunStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    INTERVENING = "intervening"
    EXITED = "exited"
    STOPPED = "stopped"
    COMPLETED = "completed"  # the agent called complete_task and its CLI was closed
    FAILED = "failed"
    INTERRUPTED = "interrupted"


ACTIVE_STATUSES = (RunStatus.STARTING, RunStatus.RUNNING, RunStatus.INTERVENING)


class UsageStatus(StrEnum):
    """How far the run's usage has been read (phase 07)."""

    PENDING = "pending"  # nothing read yet (new run, or a run from before phase 07)
    PARTIAL = "partial"  # live figures while the run goes on
    FINAL = "final"  # read after the run ended
    UNAVAILABLE = "unavailable"  # the run ended and its transcript gave nothing


class Activity(StrEnum):
    BUSY = "busy"
    IDLE = "idle"


class RunKind(StrEnum):
    AGENT = "agent"  # an agent's CLI session in a terminal
    DECISION = "decision"  # a call that picked the branches of a fork (phase 13): no terminal
    DESCRIBE = "describe"  # a call that described an image of a document (phase 14): no terminal
    ARCHITECT = "architect"  # the CLI of a conversation with the Architect (phase 19): no task
    TERMINAL = "terminal"  # a CLI the person opens by hand (phase 23, ADR 0029): no agent


# The runs with a terminal: the ones the Ejecuciones list and its counter show (phase 21).
LISTED_RUN_KINDS = (RunKind.AGENT.value, RunKind.ARCHITECT.value)


class Run(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """One execution of an agent CLI in a pseudo-terminal (a CLI session)."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('starting', 'running', 'intervening', 'exited', 'stopped', 'completed',"
            " 'failed', 'interrupted')",
            name="status",
        ),
        CheckConstraint("activity IN ('busy', 'idle')", name="activity"),
        CheckConstraint(
            "usage_status IN ('pending', 'partial', 'final', 'unavailable')", name="usage_status"
        ),
    )

    kind: Mapped[str] = mapped_column(String(12), nullable=False, default=RunKind.AGENT)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Copies so the history stays readable after the agent or project is deleted.
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_color: Mapped[str] = mapped_column(String(9), nullable=False)
    project_name: Mapped[str] = mapped_column(String(80), nullable=False)
    cli: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cwd: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.STARTING)
    activity: Mapped[str] = mapped_column(String(8), nullable=False, default=Activity.IDLE)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cli_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cols: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=32)
    log_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Reported by the agent through the agentic-os MCP server.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Set when the scheduler launched the run for a task (null for a manual run).
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str | None] = mapped_column(String(8), nullable=True)  # from complete_task
    # With a «rejected» verdict, the stage the agent sends the task back to (phase 13): a stage
    # can have several reject targets. Null: the stage's default one.
    reject_to_stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # A subagent of Agentic OS (spawn_subagent): the run that launched it.
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Since when the agent waits for input (no turn running): «Sin terminar» after a while.
    idle_since: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # Usage, read from the CLI's transcript and (Claude) its status line (phase 07, ADR 0011).
    transcript_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # agy native subagents run in their own conversations: their transcripts add up here.
    extra_transcripts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cli_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thinking_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Claude only: API-equivalent cost in USD. Null when the CLI records no cost (agy).
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_models: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    usage_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    usage_status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=UsageStatus.PENDING, index=True
    )
    usage_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # «Reanudar sesión» (phase 08, ADR 0012): the interrupted run this one resumes, and where
    # the shared transcript stood then ({"offset": bytes, "cost_state": {...} | null}), so the
    # usage of the earlier run is not counted twice.
    resumed_from_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usage_baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Its terminal log was deleted by the log retention: the run and its usage stay.
    log_purged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The CLI account the run used (phase 10). The label is a copy, like `agent_name`.
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    # What the run changed: the +/- summary computed when it ended, summed over its repositories
    # (phase 11, ADR 0015). Each repository's snapshots and summary are in `RunRepo` (phase 12).
    # None = no data (not a git folder, a run from before the phase, a snapshot that failed).
    changes_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes_deleted: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Verdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EventKind(StrEnum):
    MCP = "mcp"  # a tool call of the agentic-os MCP server
    HOOK = "hook"  # a CLI hook (turn start/end, session start…)
    SYSTEM = "system"  # something Agentic OS did (prompt sent, MCP timeout, closing…)


class RunEvent(IdMixin, Base):
    """What happened during a run, for the «Eventos MCP» panel."""

    __tablename__ = "run_events"
    __table_args__ = (CheckConstraint("kind IN ('mcp', 'hook', 'system')", name="kind"),)

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
