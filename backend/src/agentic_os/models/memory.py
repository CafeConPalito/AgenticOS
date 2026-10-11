from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin


class AuthorKind(StrEnum):
    AGENT = "agent"
    USER = "user"


class MemoryNote(IdMixin, TimestampMixin, Base):
    """One note of a project's memory, written by an agent or by the user."""

    __tablename__ = "memory_notes"
    __table_args__ = (CheckConstraint("author_kind IN ('agent', 'user')", name="author_kind"),)

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_kind: Mapped[str] = mapped_column(String(8), nullable=False, default=AuthorKind.USER)
    author_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
