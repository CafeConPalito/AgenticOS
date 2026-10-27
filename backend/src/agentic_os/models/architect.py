from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow


class ArchitectMode(StrEnum):
    AGENT = "agent"  # a new agent
    IMPROVE_AGENT = "improve_agent"  # changes to an active agent
    TEAM = "team"  # a team with its agents and a project's pipeline
    IMPROVE_TEAM = "improve_team"
    IMPROVE_PIPELINE = "improve_pipeline"


class ConversationStatus(StrEnum):
    OPEN = "open"
    PROPOSED = "proposed"  # «Crear borrador / propuesta»: a proposal waits for the person
    APPLIED = "applied"
    DISCARDED = "discarded"


class MessageRole(StrEnum):
    USER = "user"
    ARCHITECT = "architect"
    SYSTEM = "system"  # what the app says in the chat (limit reached, CLI restarted…)


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class ArchitectConversation(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """A conversation with the Architect (phase 19, ADR 0026): one interactive CLI while it is
    alive (an «architect» run), resumed from `cli_session_id` after it sleeps. The sheet is what
    it is designing; nothing outside it changes until a proposal is approved."""

    __tablename__ = "architect_conversations"
    __table_args__ = (
        CheckConstraint(_in("mode", ArchitectMode), name="mode"),
        CheckConstraint(_in("status", ConversationStatus), name="status"),
    )

    mode: Mapped[str] = mapped_column(String(16), nullable=False, default=ArchitectMode.AGENT)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ConversationStatus.OPEN, index=True
    )
    # What it works on: the agent to improve (or the draft it created), the team, the project
    # whose pipeline it designs.
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The CLI it talks through, fixed when the first message starts it.
    cli: Mapped[str | None] = mapped_column(String(16), nullable=True)
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cli_accounts.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    cli_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    sheet: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    locked_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class ArchitectMessage(IdMixin, Base):
    """One message of the chat. The CLI keeps its own transcript; this is what the chat shows."""

    __tablename__ = "architect_messages"
    __table_args__ = (CheckConstraint(_in("role", MessageRole), name="role"),)

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("architect_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Which fields of the sheet the turn changed (for the chat's «cambió: rol, modelo»).
    tool_events: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
