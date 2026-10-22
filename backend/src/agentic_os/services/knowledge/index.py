"""Keeping a document's index: its chunks, their vectors and their words (phase 14, block 5)."""

from __future__ import annotations

import numpy as np
from sqlalchemy import delete, event, text
from sqlalchemy.orm import Session

from agentic_os.models import KnowledgeChunk, KnowledgeDoc
from agentic_os.services.knowledge import search, similarity
from agentic_os.services.knowledge.chunking import Chunk
from agentic_os.services.knowledge.embeddings import vector_bytes


def bump_when_committed(db: Session) -> None:
    """The search keeps the vectors in memory. It must forget them when the change is visible to
    other connections, not before: a search in between would cache the old rows as current."""
    event.listen(db, "after_commit", lambda _session: search.cache.bump(), once=True)


def replace(
    db: Session,
    doc: KnowledgeDoc,
    chunks: list[Chunk],
    vectors: np.ndarray | None,
    model: str,
) -> None:
    """Swaps the document's index for the new one in the caller's transaction.
    `vectors` None: no model of embeddings, only the words are indexed."""
    clear(db, doc.id)
    for chunk in chunks:
        row = KnowledgeChunk(
            doc_id=doc.id,
            ord=chunk.ord,
            heading=chunk.heading,
            location=chunk.location,
            start=chunk.start,
            end=chunk.end,
            tokens=chunk.tokens,
            vector=vector_bytes(vectors[chunk.ord]) if vectors is not None else None,
            vector_model=model if vectors is not None else "",
        )
        db.add(row)
        db.flush()
        db.execute(
            text("INSERT INTO knowledge_fts (text, chunk_id, doc_id) VALUES (:t, :c, :d)"),
            {"t": chunk.for_words(), "c": row.id, "d": doc.id},
        )
    doc.embed_model = model if vectors is not None else ""
    # The document as one point (phase 15): what its links to other documents are measured with.
    if vectors is not None and len(chunks):
        doc.centroid = vector_bytes(similarity.centroid_of(vectors))
        doc.centroid_model = model
    else:
        doc.centroid, doc.centroid_model = None, ""
    bump_when_committed(db)


def clear(db: Session, doc_id: str) -> None:
    db.execute(text("DELETE FROM knowledge_fts WHERE doc_id = :d"), {"d": doc_id})
    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
    bump_when_committed(db)
