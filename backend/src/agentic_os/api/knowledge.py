"""Knowledge library (phase 14): documents by reference."""

import webbrowser
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.models import KnowledgeDoc, KnowledgeScope, SourceKind
from agentic_os.schemas.knowledge import (
    AddFiles,
    AddItem,
    AddUrl,
    DocRead,
    DocUpdate,
    MarkdownRead,
    Relocate,
    RelocateRead,
    read_doc,
)
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs, formats
from agentic_os.services.proc import open_in_file_manager as open_path
from agentic_os.services.proc import reveal_in_file_manager as reveal_path

router = APIRouter(tags=["knowledge"])
DbSession = Annotated[Session, Depends(get_session)]
LEVEL_FIELDS = {"scope", "project_id", "agent_id"}


def images_dir(request: Request) -> Path:
    return Path(request.app.state.settings.data_dir) / "knowledge" / "images"


# --------------------------------------------------------------------------- listing
@router.get("/knowledge/docs")
def list_docs(
    db: DbSession,
    scope: KnowledgeScope | None = None,
    project_id: str | None = Query(None),
    agent_id: str | None = Query(None),
) -> list[DocRead]:
    """The documents of one level (or all of them), with the state of their originals."""
    query = select(KnowledgeDoc).where(KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE)
    if scope is not None:
        query = query.where(KnowledgeDoc.scope == scope)
    if project_id is not None:
        query = query.where(KnowledgeDoc.project_id == project_id)
    if agent_id is not None:
        query = query.where(KnowledgeDoc.agent_id == agent_id)
    found = list(db.scalars(query.order_by(KnowledgeDoc.created_at, KnowledgeDoc.id)))
    docs.check_all(db, found)
    db.commit()
    return [read_doc(doc) for doc in found]


@router.get("/knowledge/docs/{doc_id}")
def get_doc(doc_id: str, db: DbSession) -> DocRead:
    doc = docs.get_doc(db, doc_id)
    docs.check_presence(db, doc)
    db.commit()
    return read_doc(doc)


# --------------------------------------------------------------------------- adding
@router.post("/knowledge/docs/files", status_code=status.HTTP_201_CREATED)
def add_files(payload: AddFiles, db: DbSession) -> list[AddItem]:
    results = docs.add_files(
        db,
        payload.scope,
        payload.project_id,
        payload.agent_id,
        payload.paths,
        knowledge_config.load(db),
    )
    db.commit()
    return [
        AddItem(
            path=r.path,
            doc=read_doc(r.doc) if r.doc else None,
            error_code=r.error_code,
            message=r.message,
        )
        for r in results
    ]


@router.post("/knowledge/docs/url", status_code=status.HTTP_201_CREATED)
def add_url(payload: AddUrl, db: DbSession) -> DocRead:
    doc = docs.add_url(db, payload.scope, payload.project_id, payload.agent_id, payload.url)
    db.commit()
    return read_doc(doc)


# --------------------------------------------------------------------------- changes
@router.patch("/knowledge/docs/{doc_id}")
def update_doc(doc_id: str, payload: DocUpdate, db: DbSession) -> DocRead:
    doc = docs.get_doc(db, doc_id)
    sent = payload.model_fields_set
    if "scope" in sent:
        if payload.scope is None:
            raise ApiError(422, "level_mismatch", "the level cannot be empty", "scope")
        docs.move(db, doc, payload.scope, payload.project_id, payload.agent_id)
    elif sent & LEVEL_FIELDS:
        raise ApiError(422, "level_mismatch", "send the level (scope) with its owner", "scope")
    docs.update(db, doc, {k: getattr(payload, k) for k in sent - LEVEL_FIELDS})
    db.commit()
    return read_doc(doc)


@router.delete("/knowledge/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(doc_id: str, request: Request, db: DbSession) -> None:
    docs.remove(db, docs.get_doc(db, doc_id), images_dir(request))
    db.commit()


@router.post("/knowledge/docs/{doc_id}/relocate")
def relocate_doc(doc_id: str, payload: Relocate, db: DbSession) -> RelocateRead:
    doc = docs.get_doc(db, doc_id)
    reprocess = docs.relocate(db, doc, payload.path, knowledge_config.load(db), payload.confirm)
    db.commit()
    return RelocateRead(doc=read_doc(doc), reprocess=reprocess)


# ---------------------------------------------------------------------- the content
@router.get("/knowledge/docs/{doc_id}/markdown")
def get_markdown(doc_id: str, db: DbSession) -> MarkdownRead:
    doc = docs.get_doc(db, doc_id)
    if not doc.markdown:
        raise ApiError(409, "not_processed", "the document has no Markdown yet")
    return MarkdownRead(title=doc.title, markdown=doc.markdown, tokens=doc.md_tokens)


@router.get("/knowledge/docs/{doc_id}/original")
def get_original(doc_id: str, db: DbSession) -> FileResponse:
    """The original for the in-app viewer. Only a registered document's file is ever served."""
    doc = docs.get_doc(db, doc_id)
    path = docs.original_path(db, doc)
    db.commit()
    return FileResponse(
        path,
        media_type=formats.mime_of(str(path)),
        filename=path.name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/knowledge/docs/{doc_id}/open", status_code=status.HTTP_204_NO_CONTENT)
def open_doc(doc_id: str, db: DbSession) -> None:
    """Opens the original with the system's application (a web address, with the browser)."""
    doc = docs.get_doc(db, doc_id)
    if doc.source_kind == SourceKind.URL and doc.url:
        webbrowser.open(doc.url)
        return
    path = docs.original_path(db, doc)
    db.commit()
    open_path(str(path))


@router.post("/knowledge/docs/{doc_id}/reveal", status_code=status.HTTP_204_NO_CONTENT)
def reveal_doc(doc_id: str, db: DbSession) -> None:
    path = docs.original_path(db, docs.get_doc(db, doc_id))
    db.commit()
    reveal_path(str(path))
