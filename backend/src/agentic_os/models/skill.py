"""Skills (phase 17): folders with a `SKILL.md` that teach the agents how to do something.

A skill lives at one of the knowledge levels (general, project, agent) and is a list of versions.
Each version is a manifest {path: sha256} over a content-addressed store in the data folder
(`services/skills/store.py`), so versions that only change `SKILL.md` share the rest. Accepted
versions are never deleted: restoring one makes a new version. See docs/adr/0024-skills.md.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow
from agentic_os.models.knowledge import KnowledgeScope


class SkillReview(StrEnum):
    NONE = "none"
    PROPOSED = "proposed"  # a new skill an agent proposed: nobody sees it until approved


class SkillOriginKind(StrEnum):
    USER = "user"
    AGENT = "agent"
    IMPORT = "import"  # a folder, a .zip or the skills of a CLI
    REGISTRY = "registry"  # installed from a public registry


class VersionStatus(StrEnum):
    ACCEPTED = "accepted"
    PROPOSED = "proposed"  # waiting for the person (propose_skill)
    REJECTED = "rejected"


class VersionAuthor(StrEnum):
    USER = "user"
    AGENT = "agent"
    IMPORT = "import"
    REGISTRY = "registry"
    RESTORE = "restore"  # a copy of an older version


class SkillModeValue(StrEnum):
    AUTO = "auto"  # offered when it fits the task
    ALWAYS = "always"  # loaded whole in every run
    NEVER = "never"  # not offered


class OfferKind(StrEnum):
    ALWAYS = "always"
    CANDIDATE = "candidate"
    REQUESTED = "requested"  # not offered: the agent asked for it by name (use_skill)


class LoadedVia(StrEnum):
    CONTEXT = "context"  # «always»: its text is in the instructions
    TOOL = "tool"  # use_skill
    NATIVE = "native"  # the CLI's own skill mechanism (spikes S1/S2)


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class Skill(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """One skill of the library. Its content is the current version."""

    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(_in("scope", KnowledgeScope), name="scope"),
        CheckConstraint(_in("review", SkillReview), name="review"),
        CheckConstraint(_in("origin", SkillOriginKind), name="origin"),
        CheckConstraint(
            "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
            " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
            " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)",
            name="level",
        ),
        # One name per level. NULLs are distinct in a unique index, hence the coalesce.
        Index(
            "uq_skills_level_name",
            "workspace_id",
            "scope",
            func.coalesce("project_id", ""),
            func.coalesce("agent_id", ""),
            "name",
            unique=True,
        ),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(8), nullable=False, default=KnowledgeScope.GENERAL)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review: Mapped[str] = mapped_column(
        String(8), nullable=False, default=SkillReview.NONE, index=True
    )
    origin: Mapped[str] = mapped_column(String(8), nullable=False, default=SkillOriginKind.USER)
    # The version in use. Not a foreign key: versions and skills point at each other, and a
    # version is only deleted with its skill. None only while a proposed skill is pending.
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Copy of the current version's description: listing and selecting need no join.
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # False with `disable-model-invocation: true`: never a candidate, only asked for by name.
    model_invocable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Vector of «name + description» with the active meaning model (spike S4).
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    vector_model: Mapped[str] = mapped_column(String(80), nullable=False, default="")


class SkillVersion(IdMixin, Base):
    """One state of a skill: its files (by content) and who made it."""

    __tablename__ = "skill_versions"
    __table_args__ = (
        CheckConstraint(_in("status", VersionStatus), name="status"),
        CheckConstraint(_in("author_kind", VersionAuthor), name="author_kind"),
        UniqueConstraint("skill_id", "number", name="uq_skill_versions_number"),
    )

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default=VersionStatus.ACCEPTED)
    # {path: {"sha256": …, "size": …, "executable": bool}}, SKILL.md included.
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    author_kind: Mapped[str] = mapped_column(String(8), nullable=False, default=VersionAuthor.USER)
    author_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    task_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The version this one was made on (the diff of a proposal is against it).
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    restored_from_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # A proposal only: the level the agent suggests (the person decides).
    suggested_scope: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class SkillMode(IdMixin, Base):
    """Automatic / always / never for one skill, set on an agent or on a pipeline stage. The
    stage wins over the agent; without a row the mode is automatic."""

    __tablename__ = "skill_modes"
    __table_args__ = (
        CheckConstraint(_in("mode", SkillModeValue), name="mode"),
        CheckConstraint("(agent_id IS NULL) != (stage_id IS NULL)", name="target"),
        UniqueConstraint("skill_id", "agent_id", name="uq_skill_modes_agent"),
        UniqueConstraint("skill_id", "stage_id", name="uq_skill_modes_stage"),
    )

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default=SkillModeValue.AUTO)


class SkillOrigin(Base):
    """Where a skill installed from a public registry came from, to offer its updates."""

    __tablename__ = "skill_origins"

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False)  # registry module (S3)
    ref: Mapped[str] = mapped_column(Text, nullable=False)  # the skill's id in the registry
    repo_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Commit (GitHub sources), hash of the files (skills.sh) or version (ClawHub). Spike S3.
    revision: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    license: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    security: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    latest_revision: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    installed_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class RunSkill(IdMixin, Base):
    """A skill offered to a run and, if the agent loaded it, how. The usage statistics come from
    here: the copies keep them readable after a stage, a pipeline or a team is deleted (the
    agent, project, CLI, model and account are already copied on the run)."""

    __tablename__ = "run_skills"
    __table_args__ = (
        CheckConstraint(_in("offered", OfferKind), name="offered"),
        CheckConstraint(f"loaded_via IS NULL OR {_in('loaded_via', LoadedVia)}", name="via"),
        UniqueConstraint("run_id", "skill_id", name="uq_run_skills_pair"),
        Index("ix_run_skills_skill_loaded", "skill_id", "loaded_at"),
    )

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skill_versions.id", ondelete="SET NULL"), nullable=True
    )
    skill_name: Mapped[str] = mapped_column(String(64), nullable=False)
    offered: Mapped[str] = mapped_column(String(10), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    loaded_via: Mapped[str | None] = mapped_column(String(8), nullable=True)
    loaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    stage_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    pipeline_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pipeline_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    team_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class SkillRejection(IdMixin, TimestampMixin, Base):
    """A proposal the person rejected, without its files: an agent proposing it again is told."""

    __tablename__ = "skill_rejections"

    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    md_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    vector_model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
