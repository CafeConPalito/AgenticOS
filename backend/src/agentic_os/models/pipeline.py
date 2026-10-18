from typing import ClassVar

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentic_os.db.base import Base, IdMixin, TimestampMixin

DEFAULT_MAX_REJECTIONS = 3


class Pipeline(IdMixin, TimestampMixin, Base):
    """The stages every task of a project goes through (at most one pipeline per project)."""

    __tablename__ = "pipelines"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    max_rejections: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_REJECTIONS
    )
    stages: Mapped[list["Stage"]] = relationship(
        order_by="Stage.position", cascade="all, delete-orphan", lazy="selectin"
    )
    links: Mapped[list["StageLink"]] = relationship(
        order_by="StageLink.position", cascade="all, delete-orphan", lazy="selectin"
    )
    # Who decides the branches of a fork (phase 13): a CLI called without tools. Null: the first
    # CLI with a live session, its default account and its cheapest model.
    decider_cli: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decider_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cli_accounts.id", ondelete="SET NULL"), nullable=True
    )
    decider_model: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Stage(IdMixin, Base):
    __tablename__ = "stages"

    pipeline_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # An earlier stage the task goes back to when this one rejects (null: it cannot reject).
    reject_to_stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    # Further stages it can send tasks back to (phase 13: after a join, a stage can reject to
    # the branch that failed). `reject_to_stage_id` is the default one.
    reject_extra_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Where the stage sits on the editor's canvas.
    x: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    y: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A fork's decision waits for the person to confirm it (only matters if the stage forks).
    confirm_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StageLink(IdMixin, Base):
    """A link from a stage to the next one. A stage with several links is a fork and each link
    is a branch: the decider picks them by their condition, «always» ones are taken unasked."""

    __tablename__ = "stage_links"
    __table_args__ = (UniqueConstraint("from_stage_id", "to_stage_id"),)
    # Deleting a stage deletes its links in the database before the ORM gets to them.
    __mapper_args__: ClassVar[dict] = {"confirm_deleted_rows": False}

    pipeline_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_stage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    condition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    always: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
