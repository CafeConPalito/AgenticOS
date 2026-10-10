from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin


class RunStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    INTERVENING = "intervening"
    EXITED = "exited"
    STOPPED = "stopped"
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
            "status IN ('starting', 'running', 'intervening', 'exited', 'stopped', 'failed',"
            " 'interrupted')",
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
