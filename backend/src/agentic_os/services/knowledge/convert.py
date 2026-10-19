"""Converting any document to Markdown: one pipeline, MarkItDown plus converters of our own.

MarkItDown handles Word, PowerPoint and generic HTML. The ones registered here come first
(priority -1) for what it does badly or needs heavy libraries for (spike S1): PDF by pages with
`pypdfium2`, Excel with `openpyxl` (no pandas), the main content of a web page with
`trafilatura`, pictures, and text or code. They all share the same contract: the Markdown they
return carries page, slide and sheet markers, and the pictures go to the `ImageCollector`.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
import trafilatura
from charset_normalizer import from_bytes
from markitdown import (
    DocumentConverter,
    DocumentConverterResult,
    FileConversionException,
    MarkItDown,
    StreamInfo,
    UnsupportedFormatException,
)
from markitdown.converters import DocxConverter, HtmlConverter, PptxConverter
from trafilatura.utils import decode_file

from agentic_os.services.knowledge import formats
from agentic_os.services.knowledge.errors import KnowledgeError
from agentic_os.services.knowledge.images import (
    ImageCollector,
    PendingImage,
    extract_data_uris,
    ref,
)

Progress = Callable[[int, int], None]

OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")  # an Office file locked with a password
MIN_PAGE_TEXT = 20  # characters; a page with less text and a picture is a scan
SCAN_SCALE = 2.0  # render scanned pages at 144 dpi: enough for OCR
MAX_SHEET_ROWS = 10_000
MAX_SHEET_COLUMNS = 50
MIN_ARTICLE = 80  # characters; less than this from trafilatura means it found nothing

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
    ".tsx": "tsx", ".jsx": "jsx", ".java": "java", ".kt": "kotlin", ".go": "go", ".rs": "rust",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
    ".php": "php", ".swift": "swift", ".sh": "bash", ".ps1": "powershell", ".bat": "batch",
    ".sql": "sql", ".css": "css", ".scss": "scss", ".xml": "xml", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".csv": "csv", ".r": "r", ".lua": "lua",
}  # fmt: skip
PLAIN = frozenset({".md", ".markdown", ".txt"})  # already text: kept as they are
MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".htm": "text/html",
}


@dataclass
class Converted:
    markdown: str
    title: str | None
    images: list[PendingImage]
    dropped_images: int
    pages: int | None  # pages, slides or sheets, when the format has them


def _extension(info: StreamInfo) -> str:
    return (info.extension or "").lower()


def decode(data: bytes, charset: str | None = None) -> str:
    """Text of unknown encoding. UTF-8 first, then Windows-1252 (what Spanish files saved by
    older programs use: a short text is too ambiguous for a detector, which guesses wrong), and
    only then the detector, for everything else."""
    for encoding in (charset, "utf-8-sig", "cp1252"):
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    best = from_bytes(data).best()
    return str(best) if best is not None else data.decode("utf-8", errors="replace")


def _fence(text: str, language: str) -> str:
    """The text in a code block whose fence is longer than any run of backticks inside it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text.strip(chr(10))}\n{fence}\n"


# ------------------------------------------------------------------------------- PDF
class PdfPagesConverter(DocumentConverter):
    """Text page by page with a `<!-- page: N -->` marker. A page without text but with a
    picture is a scan: it is rendered and handed to the collector for the OCR."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _extension(stream_info) == ".pdf"

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        collector: ImageCollector | None = kwargs.get("collector")
        progress: Progress | None = kwargs.get("progress")
        try:
            pdf = pdfium.PdfDocument(file_stream.read())
        except pdfium.PdfiumError as error:
            if "password" in str(error).lower():
                raise KnowledgeError("encrypted", "the PDF is protected with a password") from error
            raise KnowledgeError("convert_error", f"unreadable PDF: {error}") from error
        try:
            total = len(pdf)
            parts: list[str] = []
            for index in range(total):
                parts.append(self._page(pdf[index], index + 1, collector))
                if progress:
                    progress(index + 1, total)
            title = (pdf.get_metadata_dict().get("Title") or "").strip() or None
            return DocumentConverterResult(markdown="\n\n".join(parts), title=title)
        finally:
            pdf.close()

    @staticmethod
    def _page(page: Any, number: int, collector: ImageCollector | None) -> str:
        where = f"p. {number}"
        text = page.get_textpage().get_text_range().replace("\r\n", "\n").strip()
        pieces = [f"<!-- page: {number} -->"]
        pictures = list(page.get_objects(filter=[pdfium_raw.FPDF_PAGEOBJ_IMAGE]))
        if len(text) < MIN_PAGE_TEXT and pictures and collector is not None:
            n = collector.add(
                _png(page.render(scale=SCAN_SCALE).to_pil()), where, kind="page", keep_small=True
            )
            if n is not None:
                pieces.append(f"![Página {number}]({ref(n)})")
            return "\n\n".join(pieces)
        if text:
            pieces.append(text)
        if collector is not None:
            for picture in pictures:
                try:
                    data = _png(picture.get_bitmap().to_pil())
                except Exception:
                    collector.dropped += 1
                    continue
                n = collector.add(data, where)
                if n is not None:
                    pieces.append(f"![Imagen de la página {number}]({ref(n)})")
        return "\n\n".join(pieces)


def _png(picture: Any) -> bytes:
    out = io.BytesIO()
    picture.convert("RGB").save(out, "PNG")
    return out.getvalue()


# ----------------------------------------------------------------------------- Excel
class XlsxConverter(DocumentConverter):
    """One table per sheet, read with openpyxl (MarkItDown's own needs pandas)."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _extension(stream_info) == ".xlsx"

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        from openpyxl import load_workbook  # heavy: only when an Excel file comes

        progress: Progress | None = kwargs.get("progress")
        try:
            book = load_workbook(file_stream, read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError, ValueError, OSError) as error:
            raise KnowledgeError("convert_error", f"unreadable workbook: {error}") from error
        try:
            sheets = [ws for ws in book.worksheets if ws.sheet_state == "visible"]
            parts: list[str] = []
            for index, sheet in enumerate(sheets, 1):
                table = self._table(sheet)
                if table:
                    parts.append(f"<!-- sheet: {sheet.title} -->\n## {sheet.title}\n\n{table}")
                if progress:
                    progress(index, len(sheets))
            return DocumentConverterResult(markdown="\n\n".join(parts))
        finally:
            book.close()

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "sí" if value else "no"
        if isinstance(value, float):
            return str(int(value)) if value.is_integer() else f"{value:.10g}"
        if isinstance(value, datetime):
            return (
                value.date().isoformat()
                if value.time().isoformat() == "00:00:00"
                else value.isoformat(" ")
            )
        if isinstance(value, date):
            return value.isoformat()
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()

    def _table(self, sheet: Any) -> str:
        rows: list[list[str]] = []
        truncated = False
        for number, row in enumerate(sheet.iter_rows(values_only=True), 1):
            if number > MAX_SHEET_ROWS:
                truncated = True
                break
            cells = [self._cell(v) for v in row[:MAX_SHEET_COLUMNS]]
            while cells and not cells[-1]:
                cells.pop()
            rows.append(cells)
        while rows and not rows[-1]:
            rows.pop()
        width = max((len(r) for r in rows), default=0)
        if width == 0:
            return ""
        lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
        lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
        if truncated:
            lines.append(f"\n_(sheet cut at {MAX_SHEET_ROWS} rows)_")
        return "\n".join(lines)


# ------------------------------------------------------------------------------- HTML
class HtmlMainConverter(DocumentConverter):
    """The main content of a page (no menus or footers) as Markdown; MarkItDown's generic HTML
    converter is the fallback when `trafilatura` finds no article."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _extension(stream_info) in (".html", ".htm") or "html" in (
            stream_info.mimetype or ""
        )

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        data = file_stream.read()
        html = decode_file(data)  # reads the encoding the page declares
        text = trafilatura.extract(
            html,
            url=stream_info.url,
            output_format="markdown",
            include_tables=True,
            include_links=False,
            include_images=False,
            favor_recall=True,
        )
        meta = trafilatura.extract_metadata(html, default_url=stream_info.url)
        title = (meta.title or "").strip() if meta else ""
        if text and len(text.strip()) >= MIN_ARTICLE:
            return DocumentConverterResult(markdown=text.strip(), title=title or None)
        fallback = HtmlConverter().convert(io.BytesIO(data), stream_info, **kwargs)
        return DocumentConverterResult(markdown=fallback.markdown, title=title or fallback.title)


# ----------------------------------------------------------------------- pictures, text
class ImageFileConverter(DocumentConverter):
    """A picture the user added: its Markdown is just the picture; the OCR gives it text."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        return _extension(stream_info) in formats.IMAGE_EXTENSIONS

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        collector: ImageCollector | None = kwargs.get("collector")
        if collector is None:
            raise KnowledgeError("convert_error", "no place to keep the picture")
        n = collector.add(file_stream.read(), kind="file", keep_small=True)
        if n is None:
            raise KnowledgeError("convert_error", "unreadable picture")
        name = stream_info.filename or "imagen"
        return DocumentConverterResult(markdown=f"![{name}]({ref(n)})")


class TextConverter(DocumentConverter):
    """Text and code. Markdown and plain text stay as they are; code and data go in a fenced
    block so that a «# comment» is never taken for a heading."""

    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        ext = _extension(stream_info)
        return (ext in formats.TEXT_EXTENSIONS or ext in formats.CODE_EXTENSIONS) and ext not in (
            ".html",
            ".htm",
        )

    def convert(
        self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any
    ) -> DocumentConverterResult:
        # MarkItDown's own charset guess is ignored: it is wrong for short Spanish files.
        text = decode(file_stream.read()).replace("\r\n", "\n")
        ext = _extension(stream_info)
        if not text.strip():
            return DocumentConverterResult(markdown="")
        if ext in PLAIN:
            return DocumentConverterResult(markdown=text.strip())
        return DocumentConverterResult(markdown=_fence(text, LANGUAGES.get(ext, "")))


# --------------------------------------------------------------------------- the entry
_instance: MarkItDown | None = None


def markitdown() -> MarkItDown:
    """The converter of this process (created once: loading it takes a moment).

    Only the converters we want: with MarkItDown's own set, a damaged «.docx» that happens to
    be text would «succeed» as plain text."""
    global _instance
    if _instance is None:
        engine = MarkItDown(enable_builtins=False, enable_plugins=False)
        for converter in (
            DocxConverter(),
            PptxConverter(),
            PdfPagesConverter(),
            XlsxConverter(),
            HtmlMainConverter(),
            ImageFileConverter(),
            TextConverter(),
        ):
            engine.register_converter(converter, priority=-1.0)
        _instance = engine
    return _instance


def _unwrap(error: FileConversionException) -> KnowledgeError:
    """MarkItDown wraps what each converter raised; ours keeps its own code."""
    attempts = list(getattr(error, "attempts", None) or [])
    for attempt in attempts:
        raised = attempt.exc_info[1] if attempt.exc_info else None
        if isinstance(raised, KnowledgeError):
            return raised
    last = attempts[-1].exc_info[1] if attempts and attempts[-1].exc_info else error
    return KnowledgeError("convert_error", f"{type(last).__name__}: {last}"[:300])


def convert_file(
    path: Path,
    *,
    ext: str,
    workdir: Path,
    name: str = "",
    url: str | None = None,
    progress: Progress | None = None,
) -> Converted:
    """Converts one file (a web page that was downloaded is a file too) to Markdown.

    Raises `KnowledgeError`. The pictures found are written under `workdir/images`."""
    ext = ext.lower()
    if ext not in formats.SUPPORTED_EXTENSIONS and ext not in (".htm",):
        raise KnowledgeError("unsupported", f"unsupported format {ext or '(none)'}")
    collector = ImageCollector(workdir / "images")
    try:
        with path.open("rb") as stream:
            if ext in (".docx", ".xlsx", ".pptx") and stream.read(8) == OLE_SIGNATURE:
                raise KnowledgeError("encrypted", "the file is protected with a password")
            stream.seek(0)
            info = StreamInfo(
                extension=ext,
                filename=name or path.name,
                local_path=str(path),
                url=url,
                mimetype=MIME.get(ext),
            )
            try:
                # `_convert` with a single guess: `convert_stream` also sniffs the content
                # (magika) and would retry a damaged file as whatever it looks like.
                result = markitdown()._convert(
                    file_stream=stream,
                    stream_info_guesses=[info],
                    keep_data_uris=True,
                    collector=collector,
                    progress=progress,
                )
            except FileConversionException as error:
                raise _unwrap(error) from error
            except UnsupportedFormatException as error:
                raise KnowledgeError("unsupported", str(error)[:300]) from error
    except FileNotFoundError as error:
        raise KnowledgeError("not_found", "the file is not there") from error
    except zipfile.BadZipFile as error:
        raise KnowledgeError("convert_error", f"damaged file: {error}") from error
    markdown = extract_data_uris(result.markdown, collector)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    if not markdown and not collector.images:
        raise KnowledgeError("empty", "no text and no pictures in the document")
    return Converted(
        markdown=markdown,
        title=(result.title or "").strip() or None,
        images=collector.images,
        dropped_images=collector.dropped,
        pages=None,
    )
