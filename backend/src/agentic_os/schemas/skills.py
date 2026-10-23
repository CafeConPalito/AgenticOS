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
