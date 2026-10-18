"""The git repositories of a project and what tasks and runs did in each (phase 12, ADR 0016).

A project is no longer tied to a single repository: its folder may hold several (`backend/`,
`frontend/`…), may be none, and repositories outside the folder can be linked to it.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import (
    Base,
    IdMixin,
    TimestampMixin,
    UTCDateTime,
    WorkspaceMixin,
    utcnow,
)


class PullMode(StrEnum):
    FF_ONLY = "ff_only"
    MERGE = "merge"
    REBASE = "rebase"


class ProjectRepo(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """A git repository of a project: found inside its folder, or linked from outside."""

    __tablename__ = "project_repos"
    __table_args__ = (
        UniqueConstraint("project_id", "path_key", name="uq_project_repos_project_path"),
        CheckConstraint("pull_mode IN ('ff_only', 'merge', 'rebase')", name="pull_mode"),
    )

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    # Normalized path (resolved, case-folded on Windows) used to detect duplicates.
    path_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Relative to the project folder ("" is the folder itself); null for a linked repo.
    rel_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # The branch task branches start from, and where they are integrated.
    base_branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    participates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    linked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The folder is gone or no longer a repository: kept until the user removes it.
    missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pull_mode: Mapped[str] = mapped_column(String(8), nullable=False, default=PullMode.FF_ONLY)
    # github | gitlab, when it cannot be told from the remote URL.
    forge: Mapped[str | None] = mapped_column(String(16), nullable=True)


class TaskRepo(IdMixin, Base):
    """What a task has in one repository: its branch, its worktree and where it started."""

    __tablename__ = "task_repos"
    __table_args__ = (UniqueConstraint("task_id", "repo_id", name="uq_task_repos_task_repo"),)

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_repos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch: Mapped[str] = mapped_column(String(120), nullable=False)
    # Null once the worktree is released (or in direct-folder mode, where there is none).
    worktree_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The base branch's commit the branch started from: the origin of the task's diff here.
    base_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    integrated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    integrated_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)


class RunRepo(IdMixin, Base):
    """What a run did in one repository: snapshots of its folder and the +/- summary."""

    __tablename__ = "run_repos"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null when the repository was removed from the project: the run's history stays readable.
    repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_repos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Copies so the history survives the repository leaving the project.
    repo_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # The folder the snapshots were taken in (the task's worktree of this repo, or the repo).
    path: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_start: Mapped[str | None] = mapped_column(String(40), nullable=True)
    snapshot_end: Mapped[str | None] = mapped_column(String(40), nullable=True)
    snapshot_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changes_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changes_deleted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # What the run did with git here (refs when it started, commits and pushes): filled in
    # the agents block.
    refs_start: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activity: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GitOperation(IdMixin, Base):
    """Something the app did to a repository that can be undone (phase 12, ADR 0017): which
    branches pointed where before and after, and a copy of the work tree when the operation
    could lose uncommitted work."""

    __tablename__ = "git_operations"

    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_repos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Several operations that are one action of the person (an integration in two repositories).
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    # {ref: sha} of every local branch, and where HEAD was («branch:main» or «sha:…»).
    refs_before: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    refs_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    head_before: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # A snapshot of the work tree taken before an operation that throws files away.
    backup_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class CommitAttribution(IdMixin, Base):
    """Which run, task and agent made a commit (phase 12, ADR 0019): the history, the graph and
    the blame show the agent next to the commits it created."""

    __tablename__ = "commit_attributions"
    __table_args__ = (UniqueConstraint("repo_id", "sha", name="uq_commit_attributions_repo_sha"),)

    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_repos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Copies, so the history keeps saying who made it when the agent or task is gone.
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    task_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
