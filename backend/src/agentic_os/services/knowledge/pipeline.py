"""Processing one document: the same steps for every format (phase 14).

  1. the original: is it there, what is its fingerprint (or download the web page);
  2. convert to Markdown (in the worker process), with progress; then read the text of the
     pictures it found (OCR, in the worker too) and keep the ones worth keeping;
  3. keep the result.

Later blocks add description of pictures (block 7) and the search index (block 5) between 2 and
3. The document goes through the states `converting`,
`images`, `describing`, `indexing` and ends `ready` or `failed`. A failed run keeps whatever the
document had before (its previous Markdown), but the document is not used until it succeeds.
"""

from __future__ import annotations

import contextlib
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, object_session, sessionmaker

from agentic_os import __version__
from agentic_os.db.base import utcnow
from agentic_os.models import DocStatus, KnowledgeDoc, KnowledgeImage, Presence, SourceKind
from agentic_os.schemas.knowledge import read_doc
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs, formats
from agentic_os.services.knowledge.errors import KnowledgeError
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.knowledge.images import compose
from agentic_os.services.knowledge.worker import Worker
from agentic_os.services.localmodels import catalog, selection, store

log = structlog.get_logger()

PROGRESS_INTERVAL = 0.25  # seconds between the progress writes of one document
DOWNLOAD_TIMEOUT = 30.0
GENERIC_TITLES = {"", "untitled", "anonymous"}
EXTENSION_OF_MIME = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


class Cancelled(Exception):
    """The document was deleted while it was being processed: nothing is left to write."""


@dataclass
class Source:
    path: Path
    ext: str
    name: str
    url: str | None = None
    size: int | None = None
    mtime: float | None = None
    sha256: str | None = None


def estimate_tokens(text: str) -> int:
    """About four characters per token: enough to budget a context, no tokenizer needed."""
    return (len(text) + 3) // 4


class Pipeline:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        data_dir: Path,
        worker: Worker,
        events: KnowledgeEvents,
        http: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.sessions = sessions
        self.data_dir = Path(data_dir)
        self.worker = worker
        self.events = events
        self._http = http or self._default_client

    @staticmethod
    def _default_client() -> httpx.Client:
        return httpx.Client(
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"User-Agent": f"AgenticOS/{__version__}"},
        )

    @property
    def work_root(self) -> Path:
        return self.data_dir / "knowledge" / "work"

    # ------------------------------------------------------------------ the run
    def process(self, doc_id: str) -> None:
        """Runs the steps for a claimed document (`converting`). Never raises."""
        workdir = self.work_root / f"{doc_id}-{uuid.uuid4().hex[:8]}"
        try:
            with self.sessions() as db:
                doc = db.get(KnowledgeDoc, doc_id)
                if doc is None:
                    return
                origin = (doc.source_kind, doc.path, doc.url)
                limits = knowledge_config.load(db)
            workdir.mkdir(parents=True, exist_ok=True)
            source = self._source(*origin, workdir=workdir, max_bytes=limits.max_file_bytes)
            answer = self.worker.request(
                {
                    "op": "convert",
                    "path": str(source.path),
                    "ext": source.ext,
                    "workdir": str(workdir),
                    "name": source.name,
                    "url": source.url,
                },
                on_event=self._progress(doc_id),
            )
            if not answer.get("ok"):
                raise KnowledgeError(answer.get("code", "convert_error"), answer.get("message", ""))
            images = answer.get("images") or []
            texts, notice = self._read_images(doc_id, images, workdir, limits.threads)
            self._finish(doc_id, source, answer, images, texts, notice, workdir)
        except Cancelled:
            log.info("knowledge_doc_gone", doc_id=doc_id)
        except KnowledgeError as error:
            self._fail(doc_id, error)
        except Exception as error:
            log.exception("knowledge_pipeline_failed", doc_id=doc_id)
            self._fail(doc_id, KnowledgeError("convert_error", f"{type(error).__name__}: {error}"))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ------------------------------------------------------------- step 1: the original
    def _source(
        self, kind: str, path: str | None, url: str | None, *, workdir: Path, max_bytes: int
    ) -> Source:
        if kind == SourceKind.URL and url:
            return self._download(url, workdir, max_bytes)
        if not path:
            raise KnowledgeError("not_found", "the document has no file")
        original = Path(path)
        try:
            info = original.stat()
            readable = original.is_file()
        except OSError:
            readable = False
        if not readable:
            raise KnowledgeError("not_found", "the file was deleted or moved")
        if info.st_size > max_bytes:
            raise KnowledgeError("too_large", f"the file is bigger than {max_bytes} bytes")
        ext = formats.extension(path)
        if not formats.is_supported(path):
            raise KnowledgeError("unsupported", f"unsupported format {ext or '(none)'}")
        return Source(
            original,
            ext,
            original.name,
            size=info.st_size,
            mtime=info.st_mtime,
            sha256=docs.sha256_of(original),
        )

    def _download(self, url: str, workdir: Path, max_bytes: int) -> Source:
        try:
            with self._http() as client, client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise KnowledgeError("url_error", f"HTTP {response.status_code}")
                mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
                ext = EXTENSION_OF_MIME.get(mime) or (
                    "" if mime else formats.extension(urlparse(url).path)
                )
                if ext not in formats.SUPPORTED_EXTENSIONS:
                    raise KnowledgeError("unsupported", f"unsupported content type {mime or '?'}")
                target = workdir / f"source{ext}"
                size = 0
                with target.open("wb") as out:
                    for block in response.iter_bytes():
                        size += len(block)
                        if size > max_bytes:
                            raise KnowledgeError("too_large", "the page is too big")
                        out.write(block)
        except httpx.HTTPError as error:
            raise KnowledgeError("url_error", f"{type(error).__name__}: {error}"[:300]) from error
        return Source(target, ext, urlparse(url).netloc, url=url, size=size)

    # ------------------------------------------------------------------ the writes
    def _write(self, doc_id: str, change: Callable[[KnowledgeDoc], None]) -> None:
        """One short transaction on the document; the world may have deleted it meanwhile."""
        with self.sessions() as db:
            doc = db.get(KnowledgeDoc, doc_id)
            if doc is None:
                raise Cancelled
            change(doc)
            db.commit()
            self.events.doc(read_doc(doc).model_dump(mode="json"))

    def _progress(self, doc_id: str) -> Callable[[dict], None]:
        last = 0.0

        def on_event(event: dict) -> None:
            nonlocal last
            done, total = int(event.get("done", 0)), int(event.get("total", 0))
            now = time.monotonic()
            if done < total and now - last < PROGRESS_INTERVAL:
                return
            last = now

            def change(doc: KnowledgeDoc) -> None:
                doc.progress_done, doc.progress_total = done, total

            with contextlib.suppress(Cancelled):  # the final answer will find it gone
                self._write(doc_id, change)

        return on_event

    # ----------------------------------------------------------- step 2b: pictures and OCR
    def _ocr_models(self) -> dict[str, str] | None:
        """The paths of the chosen OCR model, or None if it is not available."""
        with self.sessions() as db:
            entry = selection.active(db, self.data_dir, catalog.OCR)
        if entry is None:
            return None
        return {
            key: str(store.file_path(self.data_dir, entry, entry.usage[name]))
            for key, name in (("det", "detector"), ("cls", "classifier"), ("rec", "recognizer"))
        }

    def _read_images(
        self, doc_id: str, images: list[dict], workdir: Path, threads: int
    ) -> tuple[dict[int, str], str | None]:
        """Reads the text of the pictures found. Returns {number: text} and a notice: the OCR is
        missing or failed (the document is still processed, just without that text)."""
        if not images:
            return {}, None

        def entering(doc: KnowledgeDoc) -> None:
            doc.status = DocStatus.IMAGES
            doc.progress_done, doc.progress_total = 0, len(images)

        self._write(doc_id, entering)
        models = self._ocr_models()
        if models is None:
            return {}, "ocr_missing"
        try:
            answer = self.worker.request(
                {
                    "op": "ocr",
                    "folder": str(workdir / "images"),
                    "files": {str(image["n"]): image["file"] for image in images},
                    "models": models,
                    "threads": threads,
                },
                on_event=self._progress(doc_id),
            )
        except KnowledgeError:
            return {}, "ocr_failed"
        if not answer.get("ok"):
            log.warning("knowledge_ocr_failed", doc_id=doc_id, answer=answer)
            return {}, "ocr_failed"
        texts = {int(n): text for n, text in answer["texts"].items()}
        everything_failed = answer.get("failed", 0) >= len(images)
        return texts, "ocr_failed" if everything_failed else None

    def _store_images(
        self, db: Session, doc: KnowledgeDoc, kept: list[dict], texts: dict[int, str], folder: Path
    ) -> list[str]:
        """Replaces the document's pictures by the ones kept. Returns the files the old ones used,
        to delete those nobody else needs."""
        old = [
            name
            for name in db.scalars(
                select(KnowledgeImage.file).where(
                    KnowledgeImage.doc_id == doc.id, KnowledgeImage.file.is_not(None)
                )
            )
        ]
        db.execute(delete(KnowledgeImage).where(KnowledgeImage.doc_id == doc.id))
        target = self.data_dir / "knowledge" / "images"
        for image in kept:
            file = None
            if image["kind"] != "file":  # a picture the user added stays where they have it
                file = image["sha256"] + Path(image["file"]).suffix
                destination = target / file
                if not destination.exists():
                    target.mkdir(parents=True, exist_ok=True)
                    partial = destination.with_name(destination.name + ".tmp")
                    shutil.copyfile(folder / image["file"], partial)
                    partial.replace(destination)
            db.add(
                KnowledgeImage(
                    doc_id=doc.id,
                    ord=image["n"],
                    kind=image["kind"],
                    sha256=image["sha256"],
                    file=file,
                    location=image["location"],
                    width=image["width"],
                    height=image["height"],
                    ocr_text=texts.get(image["n"], ""),
                )
            )
        doc.image_count = len(kept)
        return old

    # ----------------------------------------------------------------- step 3: the result
    def _finish(
        self,
        doc_id: str,
        source: Source,
        answer: dict,
        images: list[dict],
        texts: dict[int, str],
        notice: str | None,
        workdir: Path,
    ) -> None:
        markdown, kept = compose(answer.get("markdown", ""), images, texts)
        title = (answer.get("title") or "").strip()
        stale: list[str] = []

        def change(doc: KnowledgeDoc) -> None:
            stale.extend(
                self._store_images(object_session(doc), doc, kept, texts, workdir / "images")
            )
            doc.notice = notice
            doc.markdown = markdown
            doc.md_tokens = estimate_tokens(markdown)
            if source.sha256 is not None:  # the fingerprint of what was converted
                doc.size, doc.source_mtime, doc.sha256 = source.size, source.mtime, source.sha256
                doc.presence = Presence.OK
            if (
                doc.source_kind == SourceKind.URL
                and title.lower() not in GENERIC_TITLES
                and doc.url
                and doc.title == docs.default_url_title(doc.url)
            ):
                doc.title = title[: docs.TITLE_MAX]
            doc.status = DocStatus.READY
            doc.progress_done = doc.progress_total = max(doc.progress_total, 1)
            doc.error_code = doc.error_message = None
            doc.processed_at = utcnow()
            doc.checked_at = utcnow()

        self._write(doc_id, change)
        if stale:  # the pictures of the previous run that nobody uses any more
            with self.sessions() as db:
                docs.prune_image_files(db, stale, self.data_dir / "knowledge" / "images")

    def _fail(self, doc_id: str, error: KnowledgeError) -> None:
        log.info("knowledge_doc_failed", doc_id=doc_id, code=error.code, message=error.message)

        def change(doc: KnowledgeDoc) -> None:
            doc.status = DocStatus.FAILED
            doc.error_code, doc.error_message = error.code, error.message
            if error.code == "not_found" and doc.source_kind != SourceKind.URL:
                doc.presence = Presence.MISSING

        with contextlib.suppress(Cancelled):
            self._write(doc_id, change)
