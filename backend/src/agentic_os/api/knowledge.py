"""Knowledge library (phase 14): documents by reference."""

import asyncio
import contextlib
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    KnowledgeDoc,
    KnowledgeImage,
    KnowledgeScope,
    Origin,
    Review,
    SourceKind,
)
from agentic_os.schemas.knowledge import (
    AcceptProposal,
    AddFiles,
    AddItem,
    AddUrl,
    DocRead,
    DocUpdate,
    ExplorationRead,
    ExploreRequest,
    GraphEdgeRead,
    GraphNodeRead,
    GraphRead,
    GraphTopicRead,
    HitRead,
    ImageRead,
    KnowledgeSettingsRead,
    KnowledgeSettingsWrite,
    MarkdownRead,
    RejectProposal,
    Relocate,
    RelocateRead,
    SearchRead,
    SearchRequest,
    read_doc,
)
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs, formats, graph, graph_tools, proposals
from agentic_os.services.knowledge.service import KnowledgeService
from agentic_os.services.proc import open_in_file_manager as open_path
from agentic_os.services.proc import reveal_in_file_manager as reveal_path

router = APIRouter(tags=["knowledge"])
DbSession = Annotated[Session, Depends(get_session)]
LEVEL_FIELDS = {"scope", "project_id", "agent_id"}


def service(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


def images_dir(request: Request) -> Path:
    return Path(request.app.state.settings.data_dir) / "knowledge" / "images"


# --------------------------------------------------------------------------- listing
@router.get("/knowledge/docs")
def list_docs(
    db: DbSession,
    scope: KnowledgeScope | None = None,
    project_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    review: Review | None = None,
    origin: Origin | None = None,
) -> list[DocRead]:
    """The documents of one level (or all of them), with the state of their originals.
    `review=proposed`: the agents' proposals waiting for the person."""
    query = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE)
        .options(defer(KnowledgeDoc.markdown))
    )
    if scope is not None:
        query = query.where(KnowledgeDoc.scope == scope)
    if project_id is not None:
        query = query.where(KnowledgeDoc.project_id == project_id)
    if agent_id is not None:
        query = query.where(KnowledgeDoc.agent_id == agent_id)
    if review is not None:
        query = query.where(KnowledgeDoc.review == review)
    if origin is not None:
        query = query.where(KnowledgeDoc.origin == origin)
    found = list(db.scalars(query.order_by(KnowledgeDoc.created_at, KnowledgeDoc.id)))
    docs.check_all(db, found)
    db.commit()
    return [read_doc(doc) for doc in found]


@router.get("/knowledge/graph")
def read_graph(
    request: Request,
    db: DbSession,
    project_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    everything: bool = Query(False, alias="all"),
    include_proposed: bool = True,
) -> GraphRead:
    """The graph of the documents: what an agent of that project (and agent) sees — the general
    documents, the project's and the agent's — or, with `all=true`, the whole library."""
    data = graph.read(
        db,
        project_id=project_id,
        agent_ids=[agent_id] if agent_id else [],
        everything=everything,
        include_proposed=include_proposed,
    )
    nodes = [
        GraphNodeRead(
            id=d.id,
            title=d.title,
            summary=d.summary,
            origin=d.origin,
            source_kind=d.source_kind,
            review=d.review,
            scope=d.scope,
            project_id=d.project_id,
            agent_id=d.agent_id,
            mode=d.mode,
            status=d.status,
            presence=d.presence,
            md_tokens=d.md_tokens,
            topic=data.topic_of.get(d.id),
        )
        for d in data.docs
    ] + [GraphNodeRead(id=i, title=t, summary="", ghost=True) for i, t in data.ghosts]
    return GraphRead(
        version=service(request).graph_version,
        nodes=nodes,
        edges=[GraphEdgeRead(**vars(e)) for e in data.edges],
        topics=[
            GraphTopicRead(
                id=t.id,
                name=t.name,
                size=len(t.doc_ids),
                loose=t.loose,
                central=t.central,
                neighbors=t.neighbors,
            )
            for t in data.topics
        ],
    )


@router.post("/knowledge/explore")
def explore_graph(payload: ExploreRequest, request: Request, db: DbSession) -> ExplorationRead:
    """The search tester's «Explorar»: what an agent of that project would reach walking the
    graph from a question or a document."""
    nodes, message = graph_tools.explore_data(
        db,
        service(request),
        payload.project_id,
        [payload.agent_id] if payload.agent_id else [],
        document=payload.document,
        query=payload.query,
        hops=payload.hops,
        kinds=payload.kinds,
        origin=payload.origin,
        level=payload.level,
        max_docs=payload.max_docs,
    )
    return ExplorationRead(nodes=nodes, message=message)


@router.get("/knowledge/docs/{doc_id}")
def get_doc(doc_id: str, db: DbSession) -> DocRead:
    doc = docs.get_doc(db, doc_id)
    docs.check_presence(db, doc)
    db.commit()
    return read_doc(doc)


# --------------------------------------------------------------------------- adding
@router.post("/knowledge/docs/files", status_code=status.HTTP_201_CREATED)
def add_files(payload: AddFiles, request: Request, db: DbSession) -> list[AddItem]:
    results = docs.add_files(
        db,
        payload.scope,
        payload.project_id,
        payload.agent_id,
        payload.paths,
        knowledge_config.load(db),
    )
    db.commit()
    service(request).poke()
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
def add_url(payload: AddUrl, request: Request, db: DbSession) -> DocRead:
    doc = docs.add_url(db, payload.scope, payload.project_id, payload.agent_id, payload.url)
    db.commit()
    service(request).poke()
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
    request.app.state.knowledge_events.doc_removed(doc_id)
    service(request).mark_graph_dirty()


@router.post("/knowledge/docs/{doc_id}/accept")
def accept_proposal(
    doc_id: str, payload: AcceptProposal, request: Request, db: DbSession
) -> DocRead:
    """The person accepts an agent's proposal (with the changes they made, and the level they
    chose). It goes to the queue and, once indexed, the agents can read it."""
    doc = docs.get_doc(db, doc_id)
    proposals.accept(db, doc, payload.model_dump(exclude_unset=True))
    db.commit()
    service(request).poke()
    service(request).mark_graph_dirty()
    read = read_doc(doc)
    request.app.state.knowledge_events.doc(read.model_dump(mode="json"))
    return read


@router.post("/knowledge/docs/{doc_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_proposal(
    doc_id: str, request: Request, db: DbSession, payload: RejectProposal | None = None
) -> None:
    """The person rejects an agent's proposal: it is deleted; only its fingerprint stays, so the
    agent is told if it proposes the same again."""
    proposals.reject(db, docs.get_doc(db, doc_id), payload.reason if payload else "")
    db.commit()
    request.app.state.knowledge_events.doc_removed(doc_id)
    service(request).mark_graph_dirty()


@router.post("/knowledge/docs/{doc_id}/relocate")
def relocate_doc(doc_id: str, payload: Relocate, request: Request, db: DbSession) -> RelocateRead:
    doc = docs.get_doc(db, doc_id)
    reprocess = docs.relocate(db, doc, payload.path, knowledge_config.load(db), payload.confirm)
    db.commit()
    if reprocess:
        service(request).poke()
    return RelocateRead(doc=read_doc(doc), reprocess=reprocess)


@router.post("/knowledge/docs/{doc_id}/reprocess")
def reprocess_doc(doc_id: str, request: Request, db: DbSession) -> DocRead:
    """Converts and indexes the document again (after a failure, a change of the original…)."""
    doc = docs.get_doc(db, doc_id)
    docs.reprocess(doc)
    db.commit()
    service(request).poke()
    request.app.state.knowledge_events.doc(read_doc(doc).model_dump(mode="json"))
    return read_doc(doc)


# ---------------------------------------------------------------------- the content
@router.get("/knowledge/docs/{doc_id}/markdown")
def get_markdown(doc_id: str, db: DbSession) -> MarkdownRead:
    doc = docs.get_doc(db, doc_id)
    if not doc.markdown:
        raise ApiError(409, "not_processed", "the document has no Markdown yet")
    return MarkdownRead(title=doc.title, markdown=doc.markdown, tokens=doc.md_tokens)


@router.get("/knowledge/docs/{doc_id}/images")
def list_images(doc_id: str, db: DbSession) -> list[ImageRead]:
    docs.get_doc(db, doc_id)
    found = db.scalars(
        select(KnowledgeImage).where(KnowledgeImage.doc_id == doc_id).order_by(KnowledgeImage.ord)
    )
    return [ImageRead.model_validate(image, from_attributes=True) for image in found]


@router.get("/knowledge/docs/{doc_id}/images/{number}")
def get_image(doc_id: str, number: int, request: Request, db: DbSession) -> FileResponse:
    """A picture of the document for the Markdown view: the extracted file, or, when the document
    is itself a picture, the original."""
    doc = docs.get_doc(db, doc_id)
    image = db.scalar(
        select(KnowledgeImage).where(KnowledgeImage.doc_id == doc_id, KnowledgeImage.ord == number)
    )
    if image is None:
        raise NotFound("image")
    if image.file is None:
        path = docs.original_path(db, doc)
        db.commit()
    else:
        path = images_dir(request) / image.file
        if not path.is_file():
            raise ApiError(410, "missing", "the picture file is gone")
    return FileResponse(
        path,
        media_type=formats.mime_of(str(path)),
        headers={"X-Content-Type-Options": "nosniff"},
    )


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


# -------------------------------------------------------------------------- settings
@router.get("/settings/knowledge")
def get_settings(db: DbSession) -> KnowledgeSettingsRead:
    return KnowledgeSettingsRead(**asdict(knowledge_config.load(db)))


@router.put("/settings/knowledge")
def put_settings(
    payload: KnowledgeSettingsWrite, request: Request, db: DbSession
) -> KnowledgeSettingsRead:
    values = payload.model_dump(exclude_unset=True)
    before = knowledge_config.load(db)
    saved = knowledge_config.save(db, {k: v for k, v in values.items() if v is not None})
    db.commit()
    if (saved.graph_threshold, saved.graph_max_neighbors) != (
        before.graph_threshold,
        before.graph_max_neighbors,
    ):
        service(request).mark_graph_dirty()
    return KnowledgeSettingsRead(**asdict(saved))


# ---------------------------------------------------------------------------- search
@router.post("/knowledge/search")
def search_library(payload: SearchRequest, request: Request, db: DbSession) -> SearchRead:
    """The search test: what an agent of that project would get for that question."""
    knowledge = service(request)
    model = knowledge.embedding_model()
    agents = [payload.agent_id] if payload.agent_id else []
    hits = knowledge.search(db, payload.query, payload.project_id, agents, payload.limit)
    return SearchRead(
        hits=[
            HitRead(
                doc_id=hit.doc.id,
                title=hit.doc.title,
                scope=hit.doc.scope,
                chunk=hit.chunk.ord,
                heading=hit.chunk.heading,
                location=hit.chunk.location,
                text=hit.text,
                score=round(hit.score, 5),
                found_by=hit.found_by,
                via=hit.via,
                images=hit.images,
            )
            for hit in hits
        ],
        mode="hybrid" if model else "words",
        model=model.id if model else None,
    )


# ------------------------------------------------------------------------------ the queue
@router.get("/knowledge/queue")
def get_queue(request: Request) -> dict:
    """`{paused, queued, active: [doc ids], mode}`."""
    return service(request).state()


@router.get("/knowledge/system")
def get_system(request: Request) -> dict:
    """`{cpu, memory, gpu}` of the machine and the app's share of each (`gpu: null` if it cannot
    be read). The same figures arrive as `system` events while documents are processed."""
    return service(request).system()


@router.post("/knowledge/queue/pause")
def pause_queue(request: Request) -> dict:
    service(request).pause()
    return service(request).state()


@router.post("/knowledge/queue/resume")
def resume_queue(request: Request) -> dict:
    service(request).resume()
    return service(request).state()


@router.websocket("/knowledge/events")
async def events(websocket: WebSocket) -> None:
    """`{"type": "doc", "doc": …}` as a document changes, `{"type": "doc_removed", "id": …}` and
    `{"type": "queue", paused, queued, active}`."""
    await websocket.accept()
    hub = websocket.app.state.knowledge_events
    queue = hub.subscribe()
    listening = asyncio.ensure_future(websocket.receive_text())  # only to notice the client leaving
    try:
        while True:
            getting = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getting, listening}, return_when=asyncio.FIRST_COMPLETED)
            if listening in done:
                getting.cancel()
                listening.result()  # raises WebSocketDisconnect when the client left
                listening = asyncio.ensure_future(websocket.receive_text())
                continue
            await websocket.send_json(getting.result())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        listening.cancel()
        with contextlib.suppress(Exception):
            await websocket.close()
