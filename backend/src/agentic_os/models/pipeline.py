from sqlalchemy import Boolean, ForeignKey, Integer, String
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
