from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin


class InboxKind(StrEnum):
    APPROVAL = "approval"  # a permission dialog of the CLI
    QUESTION = "question"  # request_human with options
    BLOCKER = "blocker"  # request_human without options (or something only a human can do)
    REVIEW = "review"  # a stage that requires review (phase 05)
    STALLED = "stalled"  # idle for a while without complete_task
    DELIVERY = "delivery"  # a task is done
    ATTENTION = "attention"  # a task waits for the person because something failed
    LIMIT = "limit"  # an account reached its daily limit (phase 07; per account since phase 10)
    QUOTA = "quota"  # the account ran out of its subscription quota (phase 07)
    ACCOUNT = "account"  # the session of an account is logged out (phase 10)
    SWITCH = "switch"  # an agent's account is about to run out: switch CLI or stay (phase 10)


class InboxStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class Resolution(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ANSWERED = "answered"
    ANSWERED_IN_TERMINAL = "answered_in_terminal"  # the human answered the CLI directly
    REVIEWED = "reviewed"  # a delivery marked as seen
    DISMISSED = "dismissed"  # no longer applies (the run ended, the task moved on…)


def _in(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


class InboxItem(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """Something the agents need from the person (phase 06)."""

    __tablename__ = "inbox_items"
    __table_args__ = (
        CheckConstraint(_in("kind", InboxKind), name="kind"),
        CheckConstraint(_in("status", InboxStatus), name="status"),
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InboxStatus.PENDING, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Copies, so a resolved item stays readable after the agent or project is deleted.
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    agent_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#C9D4E8")
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    project_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#7C9CFF")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(24), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
