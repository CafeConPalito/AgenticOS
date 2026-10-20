from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentic_os.models import (
    DocStatus,
    KnowledgeDoc,
    KnowledgeMode,
    KnowledgeScope,
    Presence,
    SourceKind,
)
from agentic_os.services.knowledge.formats import Viewer, extension, viewer_of

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PathStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UrlStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Level(BaseModel):
    """Where a document lives: general, in a project, or with an agent."""

    model_config = ConfigDict(extra="forbid")

    scope: KnowledgeScope
    project_id: str | None = None
    agent_id: str | None = None


class AddFiles(Level):
    paths: list[PathStr] = Field(min_length=1, max_length=200)


class AddUrl(Level):
    url: UrlStr


class DocUpdate(BaseModel):
    """Only the sent fields change. `scope` moves the document to another level (and then
    `project_id` or `agent_id` say which). `describe_images: null` means "what the settings say"."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: str | None = None
    mode: KnowledgeMode | None = None
    describe_images: bool | None = None
    scope: KnowledgeScope | None = None
    project_id: str | None = None
    agent_id: str | None = None


class Relocate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: PathStr
    confirm: bool = False


class DocRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: KnowledgeScope
    project_id: str | None
    agent_id: str | None
    title: str
    description: str
    mode: KnowledgeMode
    describe_images: bool | None
    source_kind: SourceKind
    path: str | None
    url: str | None
    file_name: str | None  # the original's name, to show next to the title
    extension: str  # ".pdf", ...; empty for a web address
    viewer: Viewer  # how the UI opens the original
    size: int | None
    presence: Presence
    status: DocStatus
    progress_done: int
    progress_total: int
    error_code: str | None
    error_message: str | None
    notice: str | None  # a warning on a ready document: ocr_missing, ocr_failed
    md_tokens: int
    image_count: int
    has_markdown: bool
    embed_model: str
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def read_doc(doc: KnowledgeDoc) -> DocRead:
    return DocRead(
        id=doc.id,
        scope=doc.scope,
        project_id=doc.project_id,
        agent_id=doc.agent_id,
        title=doc.title,
        description=doc.description,
        mode=doc.mode,
        describe_images=doc.describe_images,
        source_kind=doc.source_kind,
        path=doc.path,
        url=doc.url,
        file_name=Path(doc.path).name if doc.path else None,
        extension=extension(doc.path) if doc.path else "",
        viewer=viewer_of(doc.source_kind, doc.path),
        size=doc.size,
        presence=doc.presence,
        status=doc.status,
        progress_done=doc.progress_done,
        progress_total=doc.progress_total,
        error_code=doc.error_code,
        error_message=doc.error_message,
        notice=doc.notice,
        md_tokens=doc.md_tokens,
        image_count=doc.image_count,
        has_markdown=doc.md_tokens > 0,  # the Markdown itself is not loaded for a list
        embed_model=doc.embed_model,
        processed_at=doc.processed_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class AddItem(BaseModel):
    """The result for one path of an "add files" batch."""

    path: str
    doc: DocRead | None
    error_code: str | None
    message: str


class RelocateRead(BaseModel):
    doc: DocRead
    reprocess: bool  # the content differs: the document will be processed again


class ImageRead(BaseModel):
    """A picture of a document, as `![…](kimg:<ord>)` in its Markdown."""

    ord: int
    kind: str  # embedded | page | file
    location: str  # "p. 3", "diapositiva 2", or ""
    width: int
    height: int
    ocr_text: str
    description: str
    described_by: str  # "claude:haiku", "local:gemma-4-e2b" or ""


class SearchRequest(BaseModel):
    """What an agent working in `project_id` (and being `agent_id`) would find."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    project_id: str | None = None
    agent_id: str | None = None
    limit: int = Field(default=8, ge=1, le=20)


class HitRead(BaseModel):
    doc_id: str
    title: str
    scope: KnowledgeScope
    chunk: int  # the chunk's number inside the document
    heading: str
    location: str  # "p. 12", "diapositiva 3", "hoja Ventas", or ""
    text: str
    score: float
    found_by: str  # meaning | words | both
    images: list[int]  # numbers of the pictures it shows


class SearchRead(BaseModel):
    hits: list[HitRead]
    # "hybrid" (by meaning, plus words for identifiers) or "words" (no model of embeddings).
    mode: str
    model: str | None


class KnowledgeSettingsRead(BaseModel):
    max_file_mb: int
    context_budget: int
    small_doc_tokens: int
    concurrency: int  # documents processed at once; a change applies on the next start
    threads: int  # 0: half of the cores
    describe_images: bool
    describer: str  # cli | local
    describer_cli: str  # "" (the first CLI with a session), claude or agy
    describer_account: str
    describer_model: str


class KnowledgeSettingsWrite(BaseModel):
    """Only the sent fields change. Out-of-range values are refused, not clamped."""

    model_config = ConfigDict(extra="forbid")

    max_file_mb: int | None = Field(default=None, ge=1, le=2048)
    context_budget: int | None = Field(default=None, ge=500, le=200_000)
    small_doc_tokens: int | None = Field(default=None, ge=100, le=50_000)
    concurrency: int | None = Field(default=None, ge=1, le=4)
    threads: int | None = Field(default=None, ge=0, le=64)
    describe_images: bool | None = None
    describer: Literal["cli", "local"] | None = None
    describer_cli: Literal["", "claude", "agy"] | None = None
    describer_account: str | None = Field(default=None, max_length=80)
    describer_model: str | None = Field(default=None, max_length=80)


class MarkdownRead(BaseModel):
    title: str
    markdown: str
    tokens: int
