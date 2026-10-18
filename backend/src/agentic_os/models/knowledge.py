"""Knowledge library (phase 14): documents the agents can read, kept by reference.

The app keeps no copy of the original file. A document stores where the file is, a fingerprint of
it, and only what the AI needs: the Markdown text, the search index (chunks and vectors) and the
images extracted from the document. See docs/adr/0021-knowledge.md.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin


class KnowledgeScope(StrEnum):
    GENERAL = "general"  # every agent in every project
    PROJECT = "project"  # the agents working in one project
    AGENT = "agent"  # one agent, in any project


class KnowledgeMode(StrEnum):
    AUTO = "auto"  # small: into the context; big: search
    CONTEXT = "context"  # always whole into the context
    SEARCH = "search"  # never whole into the context
    OFF = "off"  # kept, but the agents do not see it


class SourceKind(StrEnum):
    FILE = "file"  # a text, code or office file on the user's disk
    IMAGE = "image"  # a picture on the user's disk
    URL = "url"  # a web page


class Presence(StrEnum):
    OK = "ok"
    MISSING = "missing"  # the original was deleted or moved
    CHANGED = "changed"  # the original is not the one that was processed


class DocStatus(StrEnum):
    QUEUED = "queued"
    CONVERTING = "converting"
    IMAGES = "images"  # extracting images and reading them with OCR
    DESCRIBING = "describing"  # optional, with a CLI or llama.cpp
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


# Documents the agents can use: processed without errors and not switched off.
PROCESSING = (
    DocStatus.QUEUED,
    DocStatus.CONVERTING,
    DocStatus.IMAGES,
    DocStatus.DESCRIBING,
    DocStatus.INDEXING,
)


def _enum_check(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class KnowledgeDoc(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    """One document of the library, at one of the three levels."""

    __tablename__ = "knowledge_docs"
    __table_args__ = (
        CheckConstraint(_enum_check("scope", KnowledgeScope), name="scope"),
        CheckConstraint(_enum_check("mode", KnowledgeMode), name="mode"),
        CheckConstraint(_enum_check("source_kind", SourceKind), name="source_kind"),
        CheckConstraint(_enum_check("presence", Presence), name="presence"),
        CheckConstraint(_enum_check("status", DocStatus), name="status"),
        CheckConstraint(
            "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
            " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
            " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)",
            name="level",
        ),
    )

    scope: Mapped[str] = mapped_column(String(8), nullable=False, default=KnowledgeScope.GENERAL)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default=KnowledgeMode.AUTO)
    # None: what the settings say. True/False: forced for this document.
    describe_images: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- origin (the original stays where the user has it)
    source_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fingerprint of the original when it was processed (files only).
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_mtime: Mapped[float | None] = mapped_column(Float, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    presence: Mapped[str] = mapped_column(String(8), nullable=False, default=Presence.OK)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # --- processing
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=DocStatus.QUEUED)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- result
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    md_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embed_model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class KnowledgeChunk(IdMixin, Base):
    """A piece of a document's Markdown: where it is (not its text) and its vector."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("doc_id", "ord", name="uq_knowledge_chunks_doc_ord"),)

    doc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    start: Mapped[int] = mapped_column(Integer, nullable=False)  # offsets in the doc's Markdown
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    vector_model: Mapped[str] = mapped_column(String(80), nullable=False, default="")


class KnowledgeImage(IdMixin, Base):
    """A picture of a document: extracted (a file in the data folder) or the document itself."""

    __tablename__ = "knowledge_images"

    doc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Relative to <data>/knowledge/images; None for a document that is itself an image.
    file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    described_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
