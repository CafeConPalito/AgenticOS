from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
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


class Activity(StrEnum):
    BUSY = "busy"
    IDLE = "idle"


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
    )

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
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
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
