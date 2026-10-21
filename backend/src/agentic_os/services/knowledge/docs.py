"""Documents by reference: add, check that the original is still there, relocate, move, remove.

The library never copies an original. It keeps the path and a fingerprint (size, modification
time and SHA-256 of what was processed); whether the file is still the same is checked on demand
(when a page lists the documents and before an action), not by watching the disk.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session, defer

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    Agent,
    DocStatus,
    KnowledgeDoc,
    KnowledgeImage,
    KnowledgeMode,
    KnowledgeScope,
    KnowledgeSource,
    Presence,
    Project,
    SourceKind,
)
from agentic_os.services.knowledge import formats, index
from agentic_os.services.knowledge.config import KnowledgeSettings
from agentic_os.services.paths import normalize

TITLE_MAX = 200
IN_PROGRESS = (DocStatus.CONVERTING, DocStatus.IMAGES, DocStatus.DESCRIBING, DocStatus.INDEXING)


@dataclass
class AddResult:
    """What happened to one path of a batch: the document, or why it was refused."""

    path: str
    doc: KnowledgeDoc | None = None
    error_code: str | None = None
    message: str = ""


# ------------------------------------------------------------------------------- levels
def validate_level(db: Session, scope: str, project_id: str | None, agent_id: str | None) -> None:
    """The three levels: general (no owner), project (a project) and agent (an agent)."""
    if scope == KnowledgeScope.GENERAL:
        if project_id or agent_id:
            raise ApiError(422, "level_mismatch", "a general document has no project or agent")
    elif scope == KnowledgeScope.PROJECT:
        if agent_id or not project_id:
            raise ApiError(422, "level_mismatch", "a project document needs only a project")
        project = db.get(Project, project_id)
        if project is None or project.workspace_id != DEFAULT_WORKSPACE:
            raise NotFound("project")
    elif scope == KnowledgeScope.AGENT:
        if project_id or not agent_id:
            raise ApiError(422, "level_mismatch", "an agent document needs only an agent")
        agent = db.get(Agent, agent_id)
        if agent is None or agent.workspace_id != DEFAULT_WORKSPACE:
            raise NotFound("agent")
    else:
        raise ApiError(422, "level_mismatch", f"unknown level {scope!r}")


def _at_level(scope: str, project_id: str | None, agent_id: str | None):
    """The WHERE clauses of one level: its owner column is set, the other one is NULL."""
    project = KnowledgeDoc.project_id
    agent = KnowledgeDoc.agent_id
    return (
        KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
        KnowledgeDoc.scope == scope,
        project.is_(None) if project_id is None else project == project_id,
        agent.is_(None) if agent_id is None else agent == agent_id,
    )


def _keys_at_level(
    db: Session, scope: str, project_id: str | None, agent_id: str | None
) -> set[str]:
    """Comparison keys of the origins already in a level: paths (folded) and URLs."""
    keys: set[str] = set()
    found = select(KnowledgeDoc).where(*_at_level(scope, project_id, agent_id))
    for doc in db.scalars(found.options(defer(KnowledgeDoc.markdown))):
        if doc.path:
            keys.add(os.path.normcase(doc.path))
        if doc.url:
            keys.add(doc.url)
    return keys


def get_doc(db: Session, doc_id: str) -> KnowledgeDoc:
    doc = db.get(KnowledgeDoc, doc_id)
    if doc is None or doc.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("document")
    return doc


# ------------------------------------------------------------------------------- adding
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_file(raw: str, limits: KnowledgeSettings) -> tuple[str, str, os.stat_result]:
    """(path to keep, comparison key, stat) of a file that can be added, or an ApiError."""
    shown, key = normalize(raw)
    path = Path(shown)
    try:
        info = path.stat()
    except OSError as error:
        raise ApiError(404, "file_not_found", "the file does not exist", "path") from error
    if not path.is_file():
        raise ApiError(422, "not_a_file", "the path is not a file", "path")
    if info.st_size > limits.max_file_bytes:
        raise ApiError(
            422,
            "too_large",
            f"the file is bigger than {limits.max_file_mb} MB",
            "path",
            {"max_mb": limits.max_file_mb},
        )
    return shown, key, info


def _title_of(name: str) -> str:
    return (name.strip() or "Documento")[:TITLE_MAX]


def add_files(
    db: Session,
    scope: str,
    project_id: str | None,
    agent_id: str | None,
    paths: list[str],
    limits: KnowledgeSettings,
) -> list[AddResult]:
    """Registers each file of the batch on its own: one bad path does not stop the rest."""
    validate_level(db, scope, project_id, agent_id)
    known = _keys_at_level(db, scope, project_id, agent_id)
    results: list[AddResult] = []
    for raw in paths:
        try:
            shown, key, info = _check_file(raw, limits)
        except ApiError as error:
            results.append(AddResult(raw, error_code=error.code, message=error.message))
            continue
        if key in known:
            results.append(
                AddResult(raw, error_code="already_added", message="already in the level")
            )
            continue
        known.add(key)
        doc = KnowledgeDoc(
            scope=scope,
            project_id=project_id,
            agent_id=agent_id,
            title=_title_of(Path(shown).name),
            source_kind=formats.source_kind_of(shown),
            path=shown,
            size=info.st_size,
            source_mtime=info.st_mtime,
            checked_at=utcnow(),
        )
        if not formats.is_supported(shown):
            ext = formats.extension(shown) or "(sin extensión)"
            doc.status = DocStatus.FAILED
            doc.error_code = "unsupported"
            doc.error_message = f"unsupported format {ext}"
        db.add(doc)
        results.append(AddResult(raw, doc=doc))
    db.flush()
    return results


def default_url_title(url: str) -> str:
    """What a web address is called until its page gives a title: host and path."""
    parts = urlparse(url)
    return _title_of(parts.netloc + parts.path.rstrip("/"))


def add_url(
    db: Session, scope: str, project_id: str | None, agent_id: str | None, url: str
) -> KnowledgeDoc:
    validate_level(db, scope, project_id, agent_id)
    url = url.strip()
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ApiError(422, "invalid_url", "use a full http(s) address", "url")
    if url in _keys_at_level(db, scope, project_id, agent_id):
        raise ApiError(409, "already_added", "the address is already in the level", "url")
    doc = KnowledgeDoc(
        scope=scope,
        project_id=project_id,
        agent_id=agent_id,
        title=default_url_title(url),
        source_kind=SourceKind.URL,
        url=url,
        checked_at=utcnow(),
    )
    db.add(doc)
    db.flush()
    return doc


# ---------------------------------------------------------------------------- presence
def check_presence(db: Session, doc: KnowledgeDoc) -> str:
    """Is the original still where it was and unchanged? Updates `presence` and returns it.

    The cheap test is size and modification time; the SHA-256 is read only when they differ, so
    a file that was merely «touched» does not count as changed."""
    presence = Presence.OK
    if doc.source_kind != SourceKind.URL and doc.path:
        path = Path(doc.path)
        try:
            info = path.stat()
            exists = path.is_file()
        except OSError:
            exists = False
        if not exists:
            presence = Presence.MISSING
        elif doc.sha256 is not None and (
            info.st_size != doc.size or info.st_mtime != doc.source_mtime
        ):
            if sha256_of(path) == doc.sha256:
                doc.size, doc.source_mtime = info.st_size, info.st_mtime
            else:
                presence = Presence.CHANGED
    doc.presence = presence
    doc.checked_at = utcnow()
    return presence


def check_all(db: Session, docs: list[KnowledgeDoc]) -> None:
    for doc in docs:
        check_presence(db, doc)


def original_path(db: Session, doc: KnowledgeDoc) -> Path:
    """The original file to open, or the error that tells the user what happened to it."""
    if doc.source_kind in (SourceKind.URL, SourceKind.MARKDOWN) or not doc.path:
        raise ApiError(422, "not_a_file", "this document has no file to open")
    if check_presence(db, doc) == Presence.MISSING:
        raise ApiError(410, "missing", "the file was deleted or moved")
    return Path(doc.path)


# ------------------------------------------------------------------------------ changes
def relocate(
    db: Session, doc: KnowledgeDoc, raw: str, limits: KnowledgeSettings, confirm: bool = False
) -> bool:
    """Points the document at the file's new place. Returns True when the content differs and
    the document must be processed again.

    Same content (same SHA-256): the index is kept. Different content: refused unless the user
    confirms, because it is another document."""
    if doc.source_kind == SourceKind.URL:
        raise ApiError(422, "not_a_file", "a web address cannot be relocated")
    if doc.status in IN_PROGRESS:
        raise ApiError(409, "processing", "the document is being processed right now")
    shown, key, info = _check_file(raw, limits)
    others = _keys_at_level(db, doc.scope, doc.project_id, doc.agent_id) - {
        os.path.normcase(doc.path or "")
    }
    if key in others:
        raise ApiError(409, "already_added", "that file is already in the level", "path")
    same = doc.sha256 is None or sha256_of(Path(shown)) == doc.sha256
    if not same and not confirm:
        raise ApiError(409, "different_content", "the file at that path is not the same one")
    doc.path = shown
    doc.size, doc.source_mtime = info.st_size, info.st_mtime
    doc.source_kind = formats.source_kind_of(shown)
    doc.presence = Presence.OK
    doc.checked_at = utcnow()
    if not same:
        doc.status = DocStatus.QUEUED
        doc.error_code = doc.error_message = None
    return not same


def reprocess(doc: KnowledgeDoc) -> None:
    """Puts the document back in the queue. What it had (its Markdown) stays until the new run
    succeeds."""
    if doc.status in IN_PROGRESS:
        raise ApiError(409, "processing", "the document is being processed right now")
    doc.status = DocStatus.QUEUED
    doc.progress_done = doc.progress_total = 0
    doc.error_code = doc.error_message = None


def move(
    db: Session, doc: KnowledgeDoc, scope: str, project_id: str | None, agent_id: str | None
) -> None:
    validate_level(db, scope, project_id, agent_id)
    if (doc.scope, doc.project_id, doc.agent_id) != (scope, project_id, agent_id):
        origin = os.path.normcase(doc.path) if doc.path else doc.url
        if origin in _keys_at_level(db, scope, project_id, agent_id):
            raise ApiError(409, "already_added", "the original is already in that level")
    doc.scope, doc.project_id, doc.agent_id = scope, project_id, agent_id


def update(db: Session, doc: KnowledgeDoc, values: dict) -> None:
    """Title, description, mode and «describe images» (None: what the settings say)."""
    if "title" in values:
        title = (values["title"] or "").strip()
        if not title:
            raise ApiError(422, "title_required", "the title cannot be empty", "title")
        doc.title = title[:TITLE_MAX]
        # The documents built on this one remember its name; keep that copy up to date.
        db.execute(
            sql_update(KnowledgeSource)
            .where(KnowledgeSource.source_id == doc.id)
            .values(source_title=doc.title)
        )
    if "description" in values:
        doc.description = (values["description"] or "").strip()
    if "mode" in values:
        if values["mode"] not in {m.value for m in KnowledgeMode}:
            raise ApiError(422, "invalid_mode", "unknown mode", "mode")
        doc.mode = values["mode"]
    if "describe_images" in values:
        doc.describe_images = values["describe_images"]


def remove(db: Session, doc: KnowledgeDoc, images_dir: Path | None = None) -> None:
    """Deletes the document: its Markdown, its index and the images extracted from it (those
    another document does not use)."""
    files = [
        name
        for name in db.scalars(select(KnowledgeImage.file).where(KnowledgeImage.doc_id == doc.id))
        if name
    ]
    db.execute(text("DELETE FROM knowledge_fts WHERE doc_id = :doc"), {"doc": doc.id})
    index.bump_when_committed(db)
    db.delete(doc)
    db.flush()  # the chunks and image rows go with it (ON DELETE CASCADE)
    if images_dir is not None:
        prune_image_files(db, files, images_dir)


def remove_owned(
    db: Session,
    images_dir: Path,
    *,
    project_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Deletes the documents of a project or an agent that is going away. The database cascade
    alone would leave their words in the index and their pictures on disk."""
    column = KnowledgeDoc.project_id if project_id else KnowledgeDoc.agent_id
    owner = project_id or agent_id
    for doc in list(db.scalars(select(KnowledgeDoc).where(column == owner))):
        remove(db, doc, images_dir)


def prune_image_files(db: Session, names: list[str], images_dir: Path) -> None:
    """Deletes the picture files in `names` that no document uses any more."""
    for name in set(names):
        still_used = db.scalar(
            select(KnowledgeImage.id).where(KnowledgeImage.file == name).limit(1)
        )
        if still_used is None:
            with contextlib.suppress(OSError):
                (images_dir / name).unlink()
