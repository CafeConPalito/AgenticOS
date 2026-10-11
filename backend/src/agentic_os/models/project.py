from enum import StrEnum

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, WorkspaceMixin


class WorkspaceMode(StrEnum):
    DIRECT = "direct"
    WORKTREE = "worktree"


class Project(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "path_key", name="uq_projects_workspace_path"),
        CheckConstraint("workspace_mode IN ('direct', 'worktree')", name="workspace_mode"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#7C9CFF")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path: Mapped[str] = mapped_column(Text, nullable=False)
    # Normalized path (resolved, case-folded on Windows) used to detect duplicates.
    path_key: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WorkspaceMode.DIRECT
    )
    # Worktree mode: the branch each task worktree starts from.
    base_branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
