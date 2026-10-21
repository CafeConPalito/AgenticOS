"""Topics: groups of documents that talk about the same thing (phase 15, block 3).

They are the communities of the graph (Louvain, from networkx, with a fixed seed and the nodes and
edges sorted, so the same library always gives the same topics — spike S2), found with no model.
A topic is named after its most central document plus the words that set its documents apart
(TF-IDF over the titles). Documents with no link at all are not a topic of their own: they are
gathered under «Sueltos».
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import networkx as nx

LOOSE = "Sueltos"
_STOP = frozenset(
    (
        "de",
        "la",
        "el",
        "en",
        "y",
        "a",
        "los",
        "las",
        "del",
        "con",
        "para",
        "por",
        "un",
        "una",
        "al",
        "se",
        "que",
        "es",
        "lo",
        "como",
        "o",
        "su",
        "sus",
        "the",
        "of",
        "and",
    )
)
_WORD = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


@dataclass
class Topic:
    id: int
    name: str
    doc_ids: list[str]
    central: list[str]  # the documents with the most links, first the most linked
    neighbors: list[int] = field(default_factory=list)  # topics it is linked to
    loose: bool = False


def _words(text: str) -> list[str]:
    return [w for w in (m.lower() for m in _WORD.findall(text)) if w not in _STOP and len(w) > 2]


def build_graph(
    ids: list[str],
    derived: list[tuple[str, str]],
    related: list[tuple[str, str, float]],
) -> nx.Graph:
    """The graph the topics are found on: «related» weighs its cosine, «derived from» weighs 1."""
    graph = nx.Graph()
    graph.add_nodes_from(sorted(ids))
    known = set(ids)
    for a, b, weight in sorted(related):
        if a in known and b in known:
            graph.add_edge(a, b, weight=weight)
    for doc_id, source_id in sorted(derived):
        if doc_id in known and source_id in known:
            graph.add_edge(doc_id, source_id, weight=1.0)
    return graph


def compute(
    ids: list[str],
    titles: dict[str, str],
    derived: list[tuple[str, str]],
    related: list[tuple[str, str, float]],
) -> list[Topic]:
    """The topics of these documents, the biggest first. The «Sueltos» one, if any, goes last."""
    if not ids:
        return []
    graph = build_graph(ids, derived, related)
    groups = nx.community.louvain_communities(graph, weight="weight", seed=0)
    linked = [sorted(g) for g in groups if len(g) > 1 or graph.degree(next(iter(g))) > 0]
    loose = sorted(n for g in groups if len(g) == 1 for n in g if graph.degree(n) == 0)
    linked.sort(key=lambda g: (-len(g), g[0]))

    frequency = Counter(w for g in linked for w in {w for n in g for w in _words(titles[n])})
    topics: list[Topic] = []
    for members in linked:
        sub = graph.subgraph(members)
        ranked = sorted(members, key=lambda n: (-sub.degree(n, weight="weight"), n))
        topics.append(
            Topic(
                len(topics),
                _name(ranked[0], members, titles, frequency, len(linked)),
                members,
                ranked[:3],
            )
        )
    if loose:
        topics.append(Topic(len(topics), LOOSE, loose, loose[:3], loose=True))

    where = {n: topic.id for topic in topics for n in topic.doc_ids}
    for a, b in graph.edges:
        if where[a] != where[b]:
            topics[where[a]].neighbors.append(where[b])
            topics[where[b]].neighbors.append(where[a])
    for topic in topics:
        topic.neighbors = sorted(set(topic.neighbors))
    return topics


def _name(
    central: str, members: list[str], titles: dict[str, str], frequency: Counter, total: int
) -> str:
    """The central document's title and up to two words that tell this topic from the others."""
    own = Counter(w for n in members for w in _words(titles[n]))
    already = set(_words(titles[central]))
    scored = sorted(
        (w for w in own if w not in already),
        key=lambda w: (-(own[w] * math.log(1 + total / frequency[w])), w),
    )
    if len(members) == 1 or not scored:
        return titles[central]
    return " · ".join([titles[central], *scored[:2]])
