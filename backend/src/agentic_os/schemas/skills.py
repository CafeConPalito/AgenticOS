"""API shapes of the skill library (phase 17)."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from agentic_os.models import (
    KnowledgeScope,
    Skill,
    SkillOriginKind,
    SkillReview,
    SkillVersion,
    VersionAuthor,
    VersionStatus,
)
from agentic_os.schemas.changes import FileChange, FileDiff
from agentic_os.schemas.knowledge import Level

PathStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class FileInput(BaseModel):
    """A support file sent by the editor: text, or any bytes in base64."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    base64: str | None = None

    @model_validator(mode="after")
    def _one(self) -> FileInput:
        if (self.text is None) == (self.base64 is None):
            raise ValueError("send either text or base64")
        return self

    def data(self) -> bytes:
        if self.text is not None:
            return self.text.encode("utf-8")
        return base64.b64decode(self.base64 or "", validate=True)


class SkillCreate(Level):
    name: str
    description: str
    body: str = ""
    files: dict[PathStr, FileInput] = Field(default_factory=dict)
    note: Note = ""


class SkillEdit(BaseModel):
    """A new version from the editor. `files` maps a path to its new content, or to null to
    remove it; a `SKILL.md` there replaces the whole file (and the fields are ignored)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    body: str | None = None
    files: dict[PathStr, FileInput | None] = Field(default_factory=dict)
    note: Note = ""


class SkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    scope: KnowledgeScope | None = None
    project_id: str | None = None
    agent_id: str | None = None


class ImportPath(Level):
    path: PathStr


class CliImportItem(Level):
    path: PathStr


class CliImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CliImportItem] = Field(min_length=1, max_length=200)


class VersionAuthorRead(BaseModel):
    kind: VersionAuthor
    label: str
    agent_id: str | None
    run_id: str | None
    task_id: str | None
    task_title: str


class VersionRead(BaseModel):
    id: str
    number: int
    status: VersionStatus
    description: str
    tokens: int
    files: int
    note: str
    author: VersionAuthorRead
    base_version_id: str | None
    restored_from_id: str | None
    created_at: datetime
    decided_at: datetime | None
    current: bool


class FileRead(BaseModel):
    path: str
    size: int
    executable: bool


class SkillRead(BaseModel):
    id: str
    name: str
    description: str
    scope: KnowledgeScope
    project_id: str | None
    agent_id: str | None
    enabled: bool
    review: SkillReview
    origin: SkillOriginKind
    version: int | None  # number of the current version
    tokens: int
    files: int
    executables: int
    model_invocable: bool
    used: int  # runs that loaded it
    last_used: datetime | None
    created_at: datetime
    updated_at: datetime


class SkillDetail(SkillRead):
    body: str
    header: dict  # every field of the SKILL.md header
    file_list: list[FileRead]
    versions: int


class ImportResult(BaseModel):
    path: str
    skill: SkillRead | None = None
    renamed_to: str | None = None  # its name was taken at that level
    error_code: str | None = None
    message: str | None = None


class CliSkillRead(BaseModel):
    source: Literal["claude_user", "claude_project", "agy_global", "agy_project"]
    path: str
    name: str
    description: str
    project_id: str | None
    project_name: str
    imported: bool
    error: str


class DiffFile(BaseModel):
    change: FileChange
    diff: FileDiff


class DiffRead(BaseModel):
    from_version: int | None
    to_version: int
    files: list[DiffFile]


def read_version(version: SkillVersion, current_id: str | None) -> VersionRead:
    return VersionRead(
        id=version.id,
        number=version.number,
        status=VersionStatus(version.status),
        description=version.description,
        tokens=version.tokens,
        files=len(version.manifest),
        note=version.note,
        author=VersionAuthorRead(
            kind=VersionAuthor(version.author_kind),
            label=version.author_label,
            agent_id=version.agent_id,
            run_id=version.run_id,
            task_id=version.task_id,
            task_title=version.task_title,
        ),
        base_version_id=version.base_version_id,
        restored_from_id=version.restored_from_id,
        created_at=version.created_at,
        decided_at=version.decided_at,
        current=version.id == current_id,
    )


def read_skill(
    skill: Skill,
    version: SkillVersion | None,
    used: int = 0,
    last_used: datetime | None = None,
) -> SkillRead:
    manifest = version.manifest if version else {}
    return SkillRead(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        scope=KnowledgeScope(skill.scope),
        project_id=skill.project_id,
        agent_id=skill.agent_id,
        enabled=skill.enabled,
        review=SkillReview(skill.review),
        origin=SkillOriginKind(skill.origin),
        version=version.number if version else None,
        tokens=version.tokens if version else 0,
        files=len(manifest),
        executables=sum(1 for e in manifest.values() if e.get("executable")),
        model_invocable=skill.model_invocable,
        used=used,
        last_used=last_used,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


# --------------------------------------------------------------------- use (block 3)
ModeValue = Literal["auto", "always", "never"]


class SkillModeRead(BaseModel):
    skill: SkillRead
    mode: ModeValue  # what this agent or stage says (auto when it says nothing)
    effective: ModeValue  # what a run gets: the stage wins over the agent
    set_by: Literal["stage", "agent", "default"]


class ModesWrite(BaseModel):
    """skill id → mode. «auto» removes what this agent or stage said."""

    model_config = ConfigDict(extra="forbid")

    modes: dict[str, ModeValue]


class TryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    agent_id: str | None = None
    project_id: str | None = None
    stage_id: str | None = None


class TryCandidate(BaseModel):
    skill: SkillRead
    rank: int
    score: float | None


class TryExcluded(BaseModel):
    skill: SkillRead
    reason: Literal["never_stage", "never_agent", "manual_only", "below_floor"]


class TryRead(BaseModel):
    method: Literal["vector", "words", "none"]
    always: list[SkillRead]
    candidates: list[TryCandidate]
    excluded: list[TryExcluded]
    section: str


class RunSkillRead(BaseModel):
    skill_id: str
    skill_name: str
    offered: Literal["always", "candidate", "requested"]
    rank: int
    score: float | None
    loaded_via: Literal["context", "tool", "native"] | None
    loaded_at: datetime | None
    version: int | None


# ------------------------------------------------------------- proposals (block 5)
class ProposalRead(BaseModel):
    skill: SkillRead
    version: VersionRead
    new_skill: bool  # a new skill, or a new version of `skill`
    suggested_scope: str  # what the agent suggested ("" for nothing)
    body: str
    header: dict
    files: list[FileRead]
    executables: list[str]  # to open before approving (CA13)
    inbox_item_id: str | None


class ProposalAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opened_files: list[PathStr] = Field(default_factory=list)
    name: str | None = None
    description: str | None = None
    body: str | None = None
    files: dict[PathStr, FileInput | None] = Field(default_factory=dict)
    scope: KnowledgeScope | None = None
    project_id: str | None = None
    agent_id: str | None = None


class ProposalReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class SkillSettingsRead(BaseModel):
    candidates: int
    index_tokens: int
    always_tokens: int
    words_floor: float
    proposals_enabled: bool
    proposals_per_run: int
    registries: dict[str, bool]  # every switchable source, with its effective state
    skillsmp_key_set: bool  # the key itself never goes back to the screen


class SkillSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: int | None = None
    index_tokens: int | None = None
    always_tokens: int | None = None
    words_floor: float | None = None
    proposals_enabled: bool | None = None
    proposals_per_run: int | None = None
    registries: dict[str, bool] | None = None
    skillsmp_key: str | None = None  # "" removes it


# ------------------------------------------------------------- registries (block 6)
class RegistryRead(BaseModel):
    id: str
    title: str
    enabled: bool
    switchable: bool
    default_enabled: bool
    has_popular: bool


class CardRead(BaseModel):
    source: str
    ref: str
    name: str
    description: str
    author: str
    installs: int | None
    stars: int | None
    updated_at: str | None
    category: str
    url: str
    installed_skill_id: str | None = None  # already in the library from this same source


class ListingRead(BaseModel):
    cards: list[CardRead]
    errors: dict[str, str]  # source → offline · unavailable · rate_limited · not_found
    attribution: str


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class PreviewRead(BaseModel):
    id: str  # to install exactly this (it expires in an hour)
    card: CardRead
    revision: str
    repo_url: str
    path: str
    license: str
    security: dict
    name: str
    body: str
    header: dict
    files: list[FileRead]
    executables: list[str]


class InstallRequest(Level):
    preview_id: str
    opened_files: list[PathStr] = Field(default_factory=list)


class InstallRead(BaseModel):
    skill: SkillDetail
    renamed_to: str | None


class OriginRead(BaseModel):
    source: str
    title: str
    ref: str
    repo_url: str
    revision: str
    latest_revision: str
    update_available: bool
    license: str
    security: dict
    checked_at: datetime | None


class UpdatePreviewRead(BaseModel):
    preview: PreviewRead
    files: list[DiffFile]


class ApplyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str
    opened_files: list[PathStr] = Field(default_factory=list)


# ------------------------------------------------------------ usage statistics (block 10)
class StatsRowRead(BaseModel):
    skill_id: str
    name: str
    scope: str
    origin: str
    group_key: str | None
    group_label: str
    offered: int
    loaded: int
    rate: float | None
    runs: int
    tasks: int
    done: int
    failed: int
    approved: int
    rejected: int
    avg_cost: float | None
    avg_tokens: float | None
    last_used: datetime | None
    via_context: int
    via_tool: int
    via_native: int


class StatsTableRead(BaseModel):
    rows: list[StatsRowRead]
    total: int


class StatsDayRead(BaseModel):
    day: str
    loads: dict[str, int]  # skill id → loads that day


class StatsRunRead(BaseModel):
    run_id: str
    started_at: datetime
    skill_id: str
    skill_name: str
    version: int | None
    offered: str
    loaded_via: str | None
    agent_name: str
    project_name: str
    stage_name: str
    pipeline_name: str
    cli: str
    model: str
    account_label: str
    status: str
    verdict: str | None
    cost_usd: float | None
    task_id: str | None
