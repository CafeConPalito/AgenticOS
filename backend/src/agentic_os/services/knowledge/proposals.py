"""Knowledge proposed by the agents (phase 15, block 2).

An agent calls `propose_knowledge` with a Markdown text and the documents it is based on. That
creates a document in *review* (`review = proposed`): it is not indexed, no agent reads it and it
never touches the documents it was built on. The person reviews it in the Inbox or the library,
edits it if they want, picks its level and accepts or rejects it. Accepting sends it through the
pipeline *without conversion* (the Markdown is the content); rejecting deletes it and keeps only a
fingerprint, so the agent is told if it proposes the same again.

Every refusal is an answer in words, not an error, so the agent can adjust and go on.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import datetime

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    DocStatus,
    InboxItem,
    InboxKind,
    InboxStatus,
    KnowledgeDoc,
    KnowledgeMode,
    KnowledgeProvenance,
    KnowledgeRejection,
    KnowledgeScope,
    KnowledgeSource,
    Origin,
    Presence,
    Resolution,
    Review,
    Run,
    SourceKind,
)
from agentic_os.services import inbox
from agentic_os.services.knowledge import chunking, docs, search, similarity
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge.agent_tools import find_document, scope_of
from agentic_os.services.knowledge.context import LEVELS
from agentic_os.services.knowledge.embeddings import vector_bytes, vector_from

TITLE_MAX = 200
MIN_CHARS = 200  # shorter than this is a note, not a document
SUMMARY_MAX = 200
EMBED_CHUNKS = 12  # chunks embedded to compare a proposal with the library (the first ones)
LEVEL_WORDS = ("general", "project", "agent")

_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s")
_SENTENCE = re.compile(r"(.+?[.!?…])(\s|$)", re.S)


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def summary_of(description: str, markdown: str) -> str:
    """One line to show next to the title: the description, else the first sentence of the text."""
    if description.strip():
        return " ".join(description.split())[:SUMMARY_MAX]
    lines = (line.strip() for line in markdown.splitlines())
    body = " ".join(line for line in lines if line and not _HEADING_LINE.match(line))
    found = _SENTENCE.match(body)
    return (found.group(1) if found else body)[:SUMMARY_MAX]


def fingerprint(markdown: str) -> str:
    return hashlib.sha256(" ".join(markdown.split()).lower().encode("utf-8")).hexdigest()


def _spanish_date(moment: datetime | None) -> str:
    return moment.strftime("%d/%m/%Y") if moment else "antes"


# ------------------------------------------------------------------------- the proposal
def propose(
    db: Session,
    service,
    run: Run,
    title: str,
    markdown: str,
    description: str = "",
    based_on: Sequence[str] = (),
    level: str = "",
    replaces: str = "",
) -> tuple[str, str]:
    """(the answer for the agent, a one-line detail for the run's events). Commits."""
    settings = knowledge_config.load(db)
    if not settings.proposals_enabled:
        return (
            "Las propuestas de conocimiento están desactivadas en los ajustes de la aplicación. "
            "Si lo que has aprendido es importante, cuéntalo en tu resumen o con `report_status`.",
            "desactivadas",
        )
    title = " ".join(title.split())[:TITLE_MAX]
    markdown = markdown.strip()
    if not title:
        return "Falta el título de la propuesta.", "sin título"
    if len(markdown) < MIN_CHARS:
        return (
            f"El texto es demasiado corto ({len(markdown)} caracteres): una propuesta es un "
            f"documento con contenido (al menos {MIN_CHARS}). Para una nota breve usa "
            "`write_project_memory`.",
            f"{title[:80]} → demasiado corta",
        )
    tokens = estimate_tokens(markdown)
    if tokens > settings.proposals_max_tokens:
        return (
            f"El texto es demasiado largo (~{tokens} tokens; el máximo es "
            f"{settings.proposals_max_tokens}). Divídelo en varios documentos, uno por tema.",
            f"{title[:80]} → demasiado larga",
        )
    made = db.scalar(
        select(func.count())
        .select_from(KnowledgeProvenance)
        .where(KnowledgeProvenance.run_id == run.id)
    )
    if (made or 0) >= settings.proposals_per_run:
        return (
            f"Ya has hecho {made} propuestas en esta ejecución (el máximo es "
            f"{settings.proposals_per_run}). Espera a que la persona las revise.",
            f"{title[:80]} → límite por ejecución",
        )

    project_id, agent_ids = scope_of(db, run)
    visible = search.visible_docs(db, project_id, agent_ids)
    sources: list[KnowledgeDoc] = []
    for reference in based_on:
        if not str(reference).strip():
            continue
        found, problem = find_document(visible, str(reference))
        if found is None:
            return f"En `based_on`: {problem}", f"{title[:80]} → origen no encontrado"
        if found not in sources:
            sources.append(found)
    replaced: KnowledgeDoc | None = None
    if replaces.strip():
        replaced, problem = find_document(visible, replaces)
        if replaced is None:
            return f"En `replaces`: {problem}", f"{title[:80]} → versión no encontrada"
        mine = replaced.provenance is not None and replaced.provenance.agent_id == run.agent_id
        if replaced.origin != Origin.AGENT or not mine:
            return (
                f"Solo puedes proponer una versión nueva de lo que propusiste tú y la persona "
                f"aceptó. «{replaced.title}» no lo es: propón un documento nuevo basado en él.",
                f"{title[:80]} → no es suyo",
            )
        if replaced not in sources:
            sources.append(replaced)

    suggested = level.strip().lower()
    if suggested not in ("", *LEVEL_WORDS):
        return (
            "`level` debe ser «general», «project» o «agent» (o vacío: lo decide la persona).",
            f"{title[:80]} → nivel no válido",
        )
    scope, owner_project, owner_agent = _provisional_level(suggested, sources, run)

    answer = _duplicate(db, service, run, visible, title, markdown, replaced)
    if isinstance(answer, str):
        return answer, f"{title[:80]} → duplicada"
    centroid, model = answer

    doc = KnowledgeDoc(
        workspace_id=DEFAULT_WORKSPACE,
        scope=scope,
        project_id=owner_project,
        agent_id=owner_agent,
        title=title,
        description=description.strip(),
        mode=KnowledgeMode.AUTO,
        source_kind=SourceKind.MARKDOWN,
        origin=Origin.AGENT,
        review=Review.PROPOSED,
        summary=summary_of(description, markdown),
        presence=Presence.OK,
        status=DocStatus.READY,
        markdown=markdown,
        md_tokens=tokens,
        centroid=vector_bytes(centroid) if centroid is not None else None,
        centroid_model=model,
        processed_at=utcnow(),
    )
    db.add(doc)
    db.flush()
    task_title = ""
    if run.task_id:
        from agentic_os.models import Task

        task = db.get(Task, run.task_id)
        task_title = task.title if task else ""
    db.add(
        KnowledgeProvenance(
            doc_id=doc.id,
            agent_id=run.agent_id,
            agent_name=run.agent_name,
            run_id=run.id,
            task_id=run.task_id,
            task_title=task_title,
            proposed_at=utcnow(),
            suggested_scope=suggested,
            replaces_id=replaced.id if replaced else None,
        )
    )
    for source in sources:
        db.add(KnowledgeSource(doc_id=doc.id, source_id=source.id, source_title=source.title))
    based = ", ".join(f"«{s.title}»" for s in sources)
    inbox.create(
        db,
        InboxKind.KNOWLEDGE,
        f"Conocimiento propuesto: {title}",
        (f"Basado en {based}. " if based else "") + doc.summary,
        run=run,
        knowledge_doc_id=doc.id,
    )
    db.commit()
    db.refresh(doc)
    from agentic_os.schemas.knowledge import read_doc

    service.events.doc(read_doc(doc).model_dump(mode="json"))
    service.mark_graph_dirty()
    left = settings.proposals_per_run - (made or 0) - 1
    return (
        f"Propuesta registrada: «{title}». Queda pendiente de que la persona la revise; hasta "
        "entonces no aparece en las búsquedas ni en el contexto de ningún agente. Sigue con tu "
        f"trabajo. (Te quedan {left} propuestas en esta ejecución.)",
        f"{title[:100]} → propuesta ({LEVELS.get(scope, scope)})",
    )


def _provisional_level(
    suggested: str, sources: list[KnowledgeDoc], run: Run
) -> tuple[str, str | None, str | None]:
    """The level the proposal starts with (the person changes it): the one the agent suggests,
    else the first source's, else the run's project."""
    if suggested == "agent" and run.agent_id:
        return KnowledgeScope.AGENT, None, run.agent_id
    if suggested == "project" and run.project_id:
        return KnowledgeScope.PROJECT, run.project_id, None
    if suggested == "general":
        return KnowledgeScope.GENERAL, None, None
    if sources:
        first = sources[0]
        return first.scope, first.project_id, first.agent_id
    if run.project_id:
        return KnowledgeScope.PROJECT, run.project_id, None
    return KnowledgeScope.GENERAL, None, None


def _duplicate(
    db: Session,
    service,
    run: Run,
    visible: list[KnowledgeDoc],
    title: str,
    markdown: str,
    replaced: KnowledgeDoc | None,
) -> str | tuple[np.ndarray | None, str]:
    """The refusal (a text) when the library already says this, else (centroid, model) of the
    proposal — None without a model of embeddings, when only the exact text and title count."""
    digest = fingerprint(markdown)
    same_title = search._plain(title)
    pending = list(
        db.scalars(
            select(KnowledgeDoc).where(
                KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
                KnowledgeDoc.review == Review.PROPOSED,
                KnowledgeDoc.id.in_(
                    select(KnowledgeProvenance.doc_id).where(
                        KnowledgeProvenance.agent_id == run.agent_id
                    )
                ),
            )
        )
    )
    candidates = [d for d in visible if d is not replaced] + pending
    for doc in candidates:
        if search._plain(doc.title) == same_title:
            return _exists(doc, "tiene ese mismo título")
        if fingerprint(doc.markdown) == digest:
            return _exists(doc, "tiene exactamente ese texto")
    mine = db.scalars(
        select(KnowledgeRejection).where(
            KnowledgeRejection.agent_id == run.agent_id, KnowledgeRejection.md_sha256 == digest
        )
    ).first()
    if mine is not None:
        return _rejected(mine)

    chunks = chunking.chunk(markdown)[:EMBED_CHUNKS]
    vectors = service.embed_passages([c.for_embedding(title) for c in chunks]) if chunks else None
    entry = service.embedding_model()
    if vectors is None or entry is None:
        return None, ""
    centroid = similarity.centroid_of(vectors)
    model = entry.id
    pool = [d for d in candidates if d.centroid and d.centroid_model == model]
    rejected = list(
        db.scalars(
            select(KnowledgeRejection).where(
                KnowledgeRejection.agent_id == run.agent_id,
                KnowledgeRejection.centroid_model == model,
                KnowledgeRejection.centroid.is_not(None),
            )
        )
    )
    rows = [vector_from(d.centroid) for d in pool] + [vector_from(r.centroid) for r in rejected]
    if rows:
        scores, centered = similarity.similarities(centroid, np.stack(rows))
        best = int(np.argmax(scores))
        if similarity.is_duplicate(float(scores[best]), centered):
            if best < len(pool):
                return _exists(pool[best], "dice prácticamente lo mismo")
            return _rejected(rejected[best - len(pool)])
    return centroid, model


def _exists(doc: KnowledgeDoc, why: str) -> str:
    where = (
        "una propuesta tuya pendiente de revisión"
        if doc.review == Review.PROPOSED
        else f"el conocimiento ({LEVELS.get(doc.scope, doc.scope)})"
    )
    return (
        f"Ya existe algo muy parecido: «{doc.title}» ({where}) {why}. No se ha creado la "
        "propuesta. Léelo con `read_knowledge`; si tienes algo nuevo que añadir, propón solo "
        "eso como documento aparte, o una versión nueva de lo tuyo con `replaces`."
    )


def _rejected(rejection: KnowledgeRejection) -> str:
    reason = f" Motivo: {rejection.reason}" if rejection.reason else ""
    return (
        f"La persona ya rechazó una propuesta muy parecida («{rejection.title}», el "
        f"{_spanish_date(rejection.created_at)}).{reason} No se ha creado la propuesta."
    )


# --------------------------------------------------------------------------- the decision
def _pending_items(db: Session, doc: KnowledgeDoc) -> list[InboxItem]:
    return list(
        db.scalars(
            select(InboxItem).where(
                InboxItem.knowledge_doc_id == doc.id, InboxItem.status == InboxStatus.PENDING
            )
        )
    )


def dismiss_items(db: Session, doc: KnowledgeDoc) -> None:
    """The document is going away without a decision: its Inbox item no longer applies."""
    for item in _pending_items(db, doc):
        inbox.resolve(db, item, Resolution.DISMISSED)


def accept(db: Session, doc: KnowledgeDoc, values: dict) -> None:
    """The person accepts the proposal, with the changes they made (`title`, `description`,
    `markdown`, a level and `replace`). It goes to the queue: the pipeline indexes it without
    conversion. The caller commits and wakes the queue."""
    if doc.review != Review.PROPOSED or doc.provenance is None:
        raise ApiError(409, "not_proposed", "the document is not a proposal waiting for review")
    edited = False
    if "title" in values and values["title"] is not None:
        title = " ".join(str(values["title"]).split())[:TITLE_MAX]
        if not title:
            raise ApiError(422, "title_required", "the title cannot be empty", "title")
        edited |= title != doc.title
        doc.title = title
    if "description" in values and values["description"] is not None:
        description = str(values["description"]).strip()
        edited |= description != doc.description
        doc.description = description
    if "markdown" in values and values["markdown"] is not None:
        markdown = str(values["markdown"]).strip()
        if not markdown:
            raise ApiError(422, "markdown_required", "the text cannot be empty", "markdown")
        edited |= markdown != doc.markdown
        doc.markdown = markdown
        doc.md_tokens = estimate_tokens(markdown)
    doc.summary = summary_of(doc.description, doc.markdown)
    if values.get("scope") is not None:
        docs.validate_level(db, values["scope"], values.get("project_id"), values.get("agent_id"))
        doc.scope = values["scope"]
        doc.project_id = values.get("project_id")
        doc.agent_id = values.get("agent_id")
    provenance = doc.provenance
    provenance.decided_at = utcnow()
    provenance.edited = edited
    provenance.replace_on_ready = bool(values.get("replace")) and provenance.replaces_id is not None
    doc.review = Review.NONE
    doc.status = DocStatus.QUEUED
    doc.progress_done = doc.progress_total = 0
    doc.error_code = doc.error_message = None
    for item in _pending_items(db, doc):
        inbox.resolve(db, item, Resolution.APPROVED)


def reject(db: Session, doc: KnowledgeDoc, reason: str = "") -> None:
    """The person rejects the proposal: it is deleted and only its fingerprint stays."""
    if doc.review != Review.PROPOSED or doc.provenance is None:
        raise ApiError(409, "not_proposed", "the document is not a proposal waiting for review")
    db.add(
        KnowledgeRejection(
            title=doc.title,
            md_sha256=fingerprint(doc.markdown),
            centroid=doc.centroid,
            centroid_model=doc.centroid_model,
            agent_id=doc.provenance.agent_id,
            reason=reason.strip()[:500],
        )
    )
    for item in _pending_items(db, doc):
        inbox.resolve(db, item, Resolution.REJECTED, reason.strip() or None)
    docs.remove(db, doc)
