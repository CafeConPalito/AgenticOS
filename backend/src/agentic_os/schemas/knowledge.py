from datetime import datetime
from pathlib import Path
from typing import Annotated

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
        has_markdown=bool(doc.markdown),
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


class MarkdownRead(BaseModel):
    title: str
    markdown: str
    tokens: int
