from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow


class ProposalKind(StrEnum):
    NEW_AGENT = "new_agent"
    AGENT_CHANGES = "agent_changes"
    TEAM = "team"  # a team, its agents and a project's pipeline, approved together
    TEAM_CHANGES = "team_changes"
    PIPELINE_CHANGES = "pipeline_changes"


class ProposalOrigin(StrEnum):
    ARCHITECT = "architect"
    AGENT = "agent"  # propose_agent during a task


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    PARTIAL = "partial"  # applied, but only some of its fields or agents
    REJECTED = "rejected"


class ChangeSource(StrEnum):
    USER = "user"  # edited by hand (only the list of fields is kept)
    ARCHITECT = "architect"
    AGENT = "agent"  # a proposal of propose_agent
    IMPORT = "import"


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class Proposal(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """Something the Architect or an agent proposes (phase 19, ADR 0026). Nothing outside the
    proposal changes until the person approves it, whole or in part, in one transaction. The
    new agents of a proposal already exist as drafts (`Agent.proposal_id`)."""

    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint(_in("kind", ProposalKind), name="kind"),
        CheckConstraint(_in("origin", ProposalOrigin), name="origin"),
        CheckConstraint(_in("status", ProposalStatus), name="status"),
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, default=ProposalStatus.PENDING, index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("architect_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # propose_agent: who proposed it, during which run and task, and why.
    source_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    source_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # What it changes: the agent, team or project (pipeline) of a proposal of changes.
    target_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The proposed sheet(s) and, in a proposal of changes, the value of every field when it
    # was made (a different current value at approval time is a conflict).
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    applied_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentChange(IdMixin, Base):
    """One change of an agent's configuration, for its History tab (phase 19). Proposals keep
    the before and after of each field (the instructions as a diff); a hand edit only the list
    of fields."""

    __tablename__ = "agent_changes"
    __table_args__ = (CheckConstraint(_in("source", ChangeSource), name="source"),)

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("proposals.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("architect_conversations.id", ondelete="SET NULL"), nullable=True
    )
    fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class AgentTemplateRow(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """A template the person saved (phase 19). The five fixed ones stay in code
    (`services/templates.py`). `payload` is the export format `agentic-os.agent` v1."""

    __tablename__ = "agent_templates"
    __table_args__ = (Index("uq_agent_templates_name", "workspace_id", "name", unique=True),)

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#8FB4FF")
    avatar: Mapped[str | None] = mapped_column(String(80), nullable=True)  # phase 20
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
