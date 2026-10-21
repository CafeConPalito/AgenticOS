"""Walking the graph to find things (phase 15, block 4): the neighbours of a document, the best
path between two, and what lies within a few hops. Pure functions over an `Adjacency` built from
the documents an agent may read, so nothing outside what it sees is ever reached.

The cost of a hop is `-log(weight)` plus a small constant, so a strong link is cheap and a long
chain of weak ones is not worth following. A «derived from» link weighs 1 (it is a fact, not a
guess): it costs only the constant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import KnowledgeDoc, KnowledgeRelated, KnowledgeSource
from agentic_os.services.knowledge import topics

HOP_COST = 0.05
MAX_HOPS = 3
MAX_PATH_HOPS = 6

DERIVES_FROM = "derives_from"  # this document was built on the other one
SOURCE_OF = "source_of"  # the other document was built on this one
RELATED = "related"


@dataclass(frozen=True)
class Link:
    other: str
    kind: str  # DERIVES_FROM, SOURCE_OF or RELATED
    weight: float


@dataclass
class Adjacency:
    ids: list[str]
    links: dict[str, list[Link]] = field(default_factory=dict)
    derived: list[tuple[str, str]] = field(default_factory=list)  # (document, its source)
    related: list[tuple[str, str, float]] = field(default_factory=list)

    @classmethod
    def build(cls, db: Session, docs: list[KnowledgeDoc]) -> Adjacency:
        ids = [d.id for d in docs]
        graph = cls(ids, {i: [] for i in ids})
        if not ids:
            return graph
        known = set(ids)
        for link in db.scalars(select(KnowledgeSource).where(KnowledgeSource.doc_id.in_(known))):
            if link.source_id in known:
                graph.derived.append((link.doc_id, link.source_id))
                graph.links[link.doc_id].append(Link(link.source_id, DERIVES_FROM, 1.0))
                graph.links[link.source_id].append(Link(link.doc_id, SOURCE_OF, 1.0))
        for row in db.scalars(
            select(KnowledgeRelated).where(
                KnowledgeRelated.a_id.in_(known), KnowledgeRelated.b_id.in_(known)
            )
        ):
            graph.related.append((row.a_id, row.b_id, row.weight))
            graph.links[row.a_id].append(Link(row.b_id, RELATED, row.weight))
            graph.links[row.b_id].append(Link(row.a_id, RELATED, row.weight))
        for found in graph.links.values():  # facts first, then the strongest guesses
            found.sort(key=lambda link: (link.kind == RELATED, -link.weight, link.other))
        return graph

    def of(self, doc_id: str) -> list[Link]:
        return self.links.get(doc_id, [])

    def topics(self, titles: dict[str, str]) -> list[topics.Topic]:
        return topics.compute(self.ids, titles, self.derived, self.related)


def cost(link: Link) -> float:
    return HOP_COST - math.log(max(link.weight, 1e-6))


@dataclass(frozen=True)
class Reached:
    """A document reached by walking the graph, and how: `chain` goes from the starting point to
    it, each step being (document, the link taken to get there; None for the starting point)."""

    id: str
    cost: float
    chain: tuple[tuple[str, Link | None], ...]

    @property
    def depth(self) -> int:
        return len(self.chain) - 1

    @property
    def strength(self) -> float:
        """1 for a starting point, smaller the longer and weaker the path."""
        return math.exp(-max(self.cost - HOP_COST * self.depth, 0.0))


def _layers(
    graph: Adjacency,
    starts: list[str],
    hops: int,
    kinds: frozenset[str] | None,
    allowed: frozenset[str] | None,
) -> list[dict[str, Reached]]:
    """The cheapest way to each document with exactly 0, 1, … `hops` hops. (A hop limit needs
    this: the cheapest path overall may be longer than the limit while a dearer, shorter one is
    fine.)"""
    first = {s: Reached(s, 0.0, ((s, None),)) for s in dict.fromkeys(starts) if s in graph.links}
    layers = [first]
    for _ in range(hops):
        step: dict[str, Reached] = {}
        for here in sorted(layers[-1]):
            reached = layers[-1][here]
            for link in graph.of(here):
                if kinds is not None and link.kind not in kinds:
                    continue
                if allowed is not None and link.other not in allowed:
                    continue
                total = reached.cost + cost(link)
                known = step.get(link.other)
                if known is None or total < known.cost - 1e-9:
                    step[link.other] = Reached(
                        link.other, total, (*reached.chain, (link.other, link))
                    )
        layers.append(step)
    return layers


def explore(
    graph: Adjacency,
    starts: list[str],
    *,
    hops: int = 2,
    kinds: frozenset[str] | None = None,
    allowed: frozenset[str] | None = None,
    max_docs: int = 15,
) -> list[Reached]:
    """The documents within `hops` of the `starts`, each by its cheapest path, nearest and
    strongest first. `kinds`: link kinds that may be followed (None: all). `allowed`: ids that
    may be reached (None: all); a starting point is always kept. At most `max_docs`, starts
    included."""
    layers = _layers(graph, starts, max(0, min(hops, MAX_HOPS)), kinds, allowed)
    best: dict[str, Reached] = {}
    for layer in layers:  # a document in several layers keeps its cheapest (nearest on a tie)
        for node, reached in layer.items():
            known = best.get(node)
            if known is None or reached.cost < known.cost - 1e-9:
                best[node] = reached
    ordered = sorted(best.values(), key=lambda r: (r.depth > 0, r.cost, r.depth, r.id))
    return ordered[: max(1, max_docs)]


def shortest_path(graph: Adjacency, source: str, target: str, max_hops: int = 4) -> Reached | None:
    """The cheapest chain of links from `source` to `target`, or None when there is none within
    `max_hops`."""
    if source not in graph.links or target not in graph.links:
        return None
    layers = _layers(graph, [source], max(1, min(max_hops, MAX_PATH_HOPS)), None, None)
    found = [layer[target] for layer in layers if target in layer]
    return min(found, key=lambda r: (r.cost, r.depth)) if found else None
