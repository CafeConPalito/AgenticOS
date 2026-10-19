"""Searching the library: by meaning and, for identifiers, by words (phase 14, block 5).

What the spikes (S4) showed, and this follows:
  - the vectors (the meaning) do the work: they find what is asked with other words;
  - the words (SQLite FTS5) only help with *identifiers* — `ERR_4012`, `/v2/invoices`,
    `AURORA_PROXY`, `4.18` — so the words channel is used only for those, and ignored for a
    question without any: with all the words of a question it returns noise that outvotes the
    vectors;
  - the two rankings are fused with Reciprocal Rank Fusion (vector 1, words 2);
  - without a model of embeddings the search is by words only, with every meaningful word.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import (
    DocStatus,
    KnowledgeChunk,
    KnowledgeDoc,
    KnowledgeMode,
    KnowledgeScope,
)
from agentic_os.services.knowledge.embeddings import vector_from

DEFAULT_LIMIT = 8
MAX_LIMIT = 20
CANDIDATES = 50  # per channel, before fusing
WORDS_FETCH = 200  # rows asked of the full-text index (the visible ones are kept)
RRF_K = 60
WEIGHT_VECTOR = 1.0
WEIGHT_WORDS = 2.0

_TERM = re.compile(r"[\w./+\-]+", re.UNICODE)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_IMAGE_REF = re.compile(r"kimg:(\d+)")
STOP = frozenset(
    (
        "a",
        "al",
        "algo",
        "algunos",
        "ante",
        "antes",
        "aqui",
        "asi",
        "aun",
        "cada",
        "como",
        "con",
        "contra",
        "cual",
        "cuando",
        "cuanto",
        "de",
        "del",
        "desde",
        "donde",
        "durante",
        "e",
        "el",
        "ella",
        "ellas",
        "ellos",
        "en",
        "entre",
        "era",
        "es",
        "esa",
        "esas",
        "ese",
        "eso",
        "esos",
        "esta",
        "estan",
        "estar",
        "este",
        "esto",
        "estos",
        "fue",
        "ha",
        "han",
        "hay",
        "hasta",
        "hace",
        "hacer",
        "hago",
        "la",
        "las",
        "le",
        "les",
        "lo",
        "los",
        "mas",
        "me",
        "mi",
        "mis",
        "mucho",
        "muy",
        "nada",
        "ni",
        "no",
        "nos",
        "o",
        "os",
        "otra",
        "otro",
        "para",
        "pero",
        "poco",
        "por",
        "porque",
        "puedo",
        "puede",
        "pueden",
        "que",
        "quien",
        "se",
        "ser",
        "si",
        "sin",
        "sobre",
        "su",
        "sus",
        "tambien",
        "tanto",
        "te",
        "tengo",
        "tiene",
        "todo",
        "todos",
        "tu",
        "tus",
        "un",
        "una",
        "uno",
        "unos",
        "va",
        "voy",
        "vez",
        "y",
        "ya",
        "yo",
        "the",
        "of",
        "and",
        "to",
        "in",
        "is",
        "it",
        "for",
        "on",
        "with",
        "as",
        "at",
        "by",
        "an",
        "be",
        "this",
        "that",
        "from",
        "or",
        "are",
        "was",
    )
)


def _plain(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_identifier(term: str) -> bool:
    """A code, a version, a path, a variable name: the terms where the exact word matters."""
    return bool(re.search(r"[\d_/.\-+]", term)) or (term.isupper() and len(term) > 2)


def terms_of(query: str) -> list[str]:
    return [t.strip(".-+/") for t in _TERM.findall(query) if t.strip(".-+/")]


def meaningful(term: str) -> bool:
    return _plain(term) not in STOP and (len(term) > 2 or any(c.isdigit() for c in term))


def words_query(query: str, with_vectors: bool) -> str | None:
    """The FTS5 expression for the words channel, or None if it has nothing to look for."""
    terms = [t for t in terms_of(query) if meaningful(t)]
    if with_vectors:
        terms = [t for t in terms if is_identifier(t)]
    if not terms:
        return None
    return " OR ".join('"' + t.replace('"', "") + '"' for t in dict.fromkeys(terms))


# ------------------------------------------------------------------------ who sees what
def visible_docs(
    db: Session, project_id: str | None, agent_ids: Iterable[str]
) -> list[KnowledgeDoc]:
    """The documents an agent working in `project_id` reads: the general ones, the project's and
    its own (a subagent also reads its parent's), that are ready and not switched off."""
    levels = [KnowledgeDoc.scope == KnowledgeScope.GENERAL]
    if project_id:
        levels.append(
            (KnowledgeDoc.scope == KnowledgeScope.PROJECT) & (KnowledgeDoc.project_id == project_id)
        )
    agents = [a for a in agent_ids if a]
    if agents:
        levels.append(
            (KnowledgeDoc.scope == KnowledgeScope.AGENT) & KnowledgeDoc.agent_id.in_(agents)
        )
    query = (
        select(KnowledgeDoc)
        .where(
            KnowledgeDoc.workspace_id == DEFAULT_WORKSPACE,
            KnowledgeDoc.status == DocStatus.READY,
            KnowledgeDoc.mode != KnowledgeMode.OFF,
            or_(*levels),
        )
        .order_by(KnowledgeDoc.created_at, KnowledgeDoc.id)
    )
    return list(db.scalars(query))


# ----------------------------------------------------------------- the vectors in memory
@dataclass
class _Matrix:
    version: int
    chunk_ids: list[str] = field(default_factory=list)
    doc_ids: np.ndarray = field(default_factory=lambda: np.array([], dtype=object))
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))


class VectorCache:
    """The vectors of one model as a matrix, rebuilt only when the index changed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._matrices: dict[str, _Matrix] = {}

    def bump(self) -> None:
        with self._lock:
            self._version += 1

    def matrix(self, db: Session, model: str) -> _Matrix:
        with self._lock:
            found = self._matrices.get(model)
            if found is not None and found.version == self._version:
                return found
            version = self._version
        rows = db.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.doc_id, KnowledgeChunk.vector).where(
                KnowledgeChunk.vector_model == model, KnowledgeChunk.vector.is_not(None)
            )
        ).all()
        built = _Matrix(version)
        if rows:
            built.chunk_ids = [r[0] for r in rows]
            built.doc_ids = np.array([r[1] for r in rows], dtype=object)
            built.vectors = np.stack([vector_from(r[2]) for r in rows])
        with self._lock:
            self._matrices[model] = built
        return built


cache = VectorCache()


# ------------------------------------------------------------------------------ the search
@dataclass
class Hit:
    doc: KnowledgeDoc
    chunk: KnowledgeChunk
    text: str  # the chunk's Markdown, without page markers
    score: float
    found_by: str  # "meaning", "words" or "both"
    images: list[int]  # numbers of the pictures the chunk shows (`kimg:N`)


def _words_ranking(db: Session, expression: str, allowed: set[str]) -> list[str]:
    rows = db.execute(
        text(
            "SELECT chunk_id, doc_id FROM knowledge_fts WHERE knowledge_fts MATCH :q"
            " ORDER BY bm25(knowledge_fts) LIMIT :n"
        ),
        {"q": expression, "n": WORDS_FETCH},
    ).all()
    return [chunk_id for chunk_id, doc_id in rows if doc_id in allowed][:CANDIDATES]


def _meaning_ranking(
    db: Session, query_vector: np.ndarray, model: str, allowed: set[str]
) -> list[str]:
    matrix = cache.matrix(db, model)
    if not matrix.chunk_ids:
        return []
    mask = np.isin(matrix.doc_ids, list(allowed))
    if not mask.any():
        return []
    indexes = np.flatnonzero(mask)
    scores = matrix.vectors[indexes] @ query_vector
    best = np.argsort(-scores)[:CANDIDATES]
    return [matrix.chunk_ids[indexes[i]] for i in best]


def _fuse(rankings: list[tuple[list[str], float]]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking, weight in rankings:
        for position, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (RRF_K + position + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def search(
    db: Session,
    query: str,
    docs: list[KnowledgeDoc],
    *,
    limit: int = DEFAULT_LIMIT,
    embed_query: Callable[[str], np.ndarray | None] | None = None,
    model: str | None = None,
) -> list[Hit]:
    """The chunks of `docs` that best answer `query`. `embed_query` turns the question into a
    vector (None, or returning None: there is no model, so only words); `model` is the id of the
    model that made the vectors the index must have to be used."""
    query = query.strip()
    if not query or not docs:
        return []
    limit = max(1, min(limit, MAX_LIMIT))
    allowed = {d.id for d in docs}
    vector = embed_query(query) if (embed_query and model) else None
    # The documents the meaning can speak for; the rest are searched by their words.
    vectored = {d.id for d in docs if d.embed_model == model} if vector is not None else set()
    rankings: list[tuple[list[str], float]] = []
    meaning: list[str] = []
    if vector is not None:
        meaning = _meaning_ranking(db, vector, model, vectored)
        rankings.append((meaning, WEIGHT_VECTOR))
    words: list[str] = []
    for ids, with_vectors, weight in (
        (vectored, True, WEIGHT_WORDS),  # identifiers only, trusted
        (allowed - vectored, False, 1.0),  # every meaningful word
    ):
        expression = words_query(query, with_vectors=with_vectors) if ids else None
        if not expression:
            continue
        try:
            found = _words_ranking(db, expression, ids)
        except Exception:  # a query the index cannot parse finds nothing, it is not a 500
            found = []
        words += found
        rankings.append((found, weight))
    top = _fuse(rankings)[:limit]
    if not top:
        return []
    chunks = {
        c.id: c
        for c in db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.id.in_([i for i, _ in top]))
        )
    }
    by_id = {d.id: d for d in docs}
    in_meaning, in_words = set(meaning), set(words)
    hits: list[Hit] = []
    for chunk_id, score in top:
        chunk = chunks.get(chunk_id)
        if chunk is None:
            continue
        doc = by_id[chunk.doc_id]
        body = _COMMENT.sub("", doc.markdown[chunk.start : chunk.end]).strip()
        found = (
            "both"
            if chunk_id in in_meaning and chunk_id in in_words
            else ("words" if chunk_id in in_words else "meaning")
        )
        hits.append(
            Hit(doc, chunk, body, score, found, sorted({int(n) for n in _IMAGE_REF.findall(body)}))
        )
    return hits
