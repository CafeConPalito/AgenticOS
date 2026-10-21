"""The knowledge graph (phase 15, block 3).

Nodes are documents. Two kinds of edge join them:
  - «derived from»: set by the agent that proposed the document (table `knowledge_sources`);
  - «related»: documents whose content is close, computed here from the centroids of their chunks
    (table `knowledge_related`). The cosine is measured after subtracting the library's mean, which
    puts every embedding model on one scale (spike S1); only the strong links stay, with a cap of
    neighbours per document, and each document keeps at least its closest neighbour.

The related links are recomputed whole, in memory (9 ms for 1 000 documents), and only the
difference is written. Reading the graph for an agent or for the screen is filtering these tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, defer

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import KnowledgeDoc, KnowledgeRelated, KnowledgeSource, Review
from agentic_os.services.knowledge import search, similarity, topics
from agentic_os.services.knowledge.embeddings import vector_from

WEIGHT_EPSILON = 1e-4  # a weight that moved less than this is not worth a write


@dataclass(frozen=True)
class Link:
    a: str  # a < b
    b: str
    weight: float


def related_links(
    ids: list[str],
    matrix: np.ndarray,
    *,
    threshold: float,
    max_neighbors: int,
    raw_threshold: float,
) -> list[Link]:
    """The «related» links among documents whose normalised centroids are the rows of `matrix`."""
    count = len(ids)
    if count < 2:
        return []
    centered = count >= similarity.MIN_FOR_CENTERING
    if centered:
        points = similarity.center(matrix, matrix.mean(axis=0))
        floor, nearest = threshold, similarity.NEAREST_FLOOR
    else:  # no reliable mean in a tiny library: the raw cosine, with the model's own threshold
        points = matrix
        floor = nearest = raw_threshold
    sim = points @ points.T
    np.fill_diagonal(sim, -np.inf)
    order = np.argsort(-sim, axis=1, kind="stable")[:, : min(max_neighbors, count - 1)]
    found: dict[tuple[str, str], float] = {}
    for i in range(count):
        for rank, j in enumerate(order[i]):
            score = float(sim[i, j])
            if score >= floor or (rank == 0 and score >= nearest):
                a, b = sorted((ids[i], ids[int(j)]))
                found[(a, b)] = score
    return [Link(a, b, w) for (a, b), w in sorted(found.items())]


def recompute(
    db: Session,
    model: str | None,
    *,
    threshold: float,
    max_neighbors: int,
    raw_threshold: float,
) -> bool:
    """Brings the stored «related» links up to date with the centroids made by `model` (None: no
    model, so no links). Returns whether anything changed. The caller commits."""
    rows = (
        db.execute(
            select(KnowledgeDoc.id, KnowledgeDoc.centroid).where(
                KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
                KnowledgeDoc.review == Review.NONE,
                KnowledgeDoc.centroid.is_not(None),
                KnowledgeDoc.centroid_model == model,
            )
        ).all()
        if model
        else []
    )
    wanted: dict[tuple[str, str], float] = {}
    if rows:
        ids = [r[0] for r in rows]
        matrix = np.stack([vector_from(r[1]) for r in rows])
        for link in related_links(
            ids,
            matrix,
            threshold=threshold,
            max_neighbors=max_neighbors,
            raw_threshold=raw_threshold,
        ):
            wanted[(link.a, link.b)] = link.weight
    stored = {(r.a_id, r.b_id): r for r in db.scalars(select(KnowledgeRelated))}
    changed = False
    for key, row in stored.items():
        if key not in wanted or row.model != model:
            db.execute(
                delete(KnowledgeRelated).where(
                    KnowledgeRelated.a_id == key[0], KnowledgeRelated.b_id == key[1]
                )
            )
            changed = True
    for (a, b), weight in wanted.items():
        row = stored.get((a, b))
        if row is None or row.model != model:
            db.add(KnowledgeRelated(a_id=a, b_id=b, weight=weight, model=model or ""))
            changed = True
        elif abs(row.weight - weight) > WEIGHT_EPSILON:
            row.weight = weight
            changed = True
    return changed


# ------------------------------------------------------------------------------- reading
@dataclass(frozen=True)
class Edge:
    kind: str  # "derived" or "related"
    source: str  # for «derived»: the document it was derived from
    target: str
    weight: float


@dataclass
class GraphData:
    docs: list[KnowledgeDoc]
    ghosts: list[tuple[str, str]] = field(
        default_factory=list
    )  # (node id, title) of removed sources
    edges: list[Edge] = field(default_factory=list)
    topics: list[topics.Topic] = field(default_factory=list)
    topic_of: dict[str, int] = field(default_factory=dict)


def ghost_id(link_id: str) -> str:
    return f"removed:{link_id}"


def read(
    db: Session,
    *,
    project_id: str | None = None,
    agent_ids: list[str] | None = None,
    everything: bool = False,
    include_proposed: bool = True,
) -> GraphData:
    """The graph an agent of `project_id` and `agent_ids` sees (general documents, its project's
    and its own) or, with `everything`, the whole library. Accepted documents only, plus the
    pending proposals (with their «derived from» links, nothing else) if `include_proposed`."""
    query = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE)
        .options(defer(KnowledgeDoc.markdown))
        .order_by(KnowledgeDoc.created_at, KnowledgeDoc.id)
    )
    if not everything:
        query = query.where(search.level_clause(project_id, agent_ids or []))
    if not include_proposed:
        query = query.where(KnowledgeDoc.review == Review.NONE)
    docs = list(db.scalars(query))
    accepted = {d.id for d in docs if d.review == Review.NONE}
    shown = {d.id for d in docs}
    data = GraphData(docs=docs)
    if not shown:
        return data

    derived: list[tuple[str, str]] = []
    for link in db.scalars(select(KnowledgeSource).where(KnowledgeSource.doc_id.in_(shown))):
        if link.source_id is None:
            node = ghost_id(link.id)
            data.ghosts.append((node, link.source_title))
            data.edges.append(Edge("derived", node, link.doc_id, 1.0))
        elif link.source_id in shown:
            derived.append((link.doc_id, link.source_id))
            data.edges.append(Edge("derived", link.source_id, link.doc_id, 1.0))

    related: list[tuple[str, str, float]] = []
    for row in db.scalars(
        select(KnowledgeRelated).where(
            KnowledgeRelated.a_id.in_(accepted), KnowledgeRelated.b_id.in_(accepted)
        )
    ):
        related.append((row.a_id, row.b_id, row.weight))
        data.edges.append(Edge("related", row.a_id, row.b_id, row.weight))

    titles = {d.id: d.title for d in docs}
    data.topics = topics.compute(sorted(accepted), titles, derived, related)
    data.topic_of = {n: t.id for t in data.topics for n in t.doc_ids}
    # A pending proposal sits in the topic of the first document it was built on.
    for doc_id, source_id in sorted(derived):
        if doc_id not in accepted and source_id in data.topic_of:
            data.topic_of.setdefault(doc_id, data.topic_of[source_id])
    return data


__all__ = ["Edge", "GraphData", "Link", "read", "recompute", "related_links"]
