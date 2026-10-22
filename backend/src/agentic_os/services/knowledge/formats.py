"""Which files the library accepts, how the UI should show them, and their MIME types."""

from __future__ import annotations

import mimetypes
from enum import StrEnum
from pathlib import Path

from agentic_os.models import SourceKind

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
OFFICE_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".pptx"})
TEXT_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml"})
CODE_EXTENSIONS = frozenset(
    {
        ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".c", ".h",
        ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".sh", ".ps1", ".bat", ".sql", ".css",
        ".scss", ".html", ".htm", ".xml", ".ini", ".cfg", ".env", ".log", ".r", ".lua",
    }
)  # fmt: skip
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | OFFICE_EXTENSIONS | TEXT_EXTENSIONS | CODE_EXTENSIONS


class Viewer(StrEnum):
    """What the UI opens an original with: inside the app, or with the system's application."""

    PDF = "pdf"
    IMAGE = "image"
    MARKDOWN = "markdown"
    TEXT = "text"
    CODE = "code"
    CSV = "csv"
    SYSTEM = "system"  # Word, Excel, PowerPoint…: the system's application
    URL = "url"  # the system's browser
    NONE = "none"  # no original: only the Markdown (an agent's document)


def extension(path: str) -> str:
    return Path(path).suffix.lower()


def is_supported(path: str) -> bool:
    return extension(path) in SUPPORTED_EXTENSIONS


def source_kind_of(path: str) -> SourceKind:
    return SourceKind.IMAGE if extension(path) in IMAGE_EXTENSIONS else SourceKind.FILE


def viewer_of(source_kind: str, path: str | None) -> Viewer:
    if source_kind == SourceKind.MARKDOWN:
        return Viewer.NONE
    if source_kind == SourceKind.URL or path is None:
        return Viewer.URL
    ext = extension(path)
    if ext == ".pdf":
        return Viewer.PDF
    if ext in IMAGE_EXTENSIONS:
        return Viewer.IMAGE
    if ext in (".md", ".markdown"):
        return Viewer.MARKDOWN
    if ext == ".csv":
        return Viewer.CSV
    if ext in CODE_EXTENSIONS or ext in (".json", ".yaml", ".yml", ".toml"):
        return Viewer.CODE
    if ext == ".txt":
        return Viewer.TEXT
    return Viewer.SYSTEM


def mime_of(path: str) -> str:
    """The Content-Type the viewer needs. Text-like files are served as plain text (never as
    HTML or script: a «.html» original is shown as code)."""
    ext = extension(path)
    if ext == ".pdf":
        return "application/pdf"
    if ext in IMAGE_EXTENSIONS:
        return mimetypes.types_map.get(ext, "application/octet-stream")
    return "text/plain; charset=utf-8"
