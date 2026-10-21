"""S2: topics (communities) over the graph, their stability and their names.

Graph = «related» edges (mean-centered cosine of centroids >= 0.25, 8 neighbours max, weight = cosine)
plus «derived from» edges (weight 1). Louvain from networkx with a fixed seed. Measures:
  purity   how well the communities match the ground-truth topics (NMI and pairwise F1)
  stability  same corpus -> same partition; shuffled insertion order; one document added
Naming: title of the most central document plus the most distinctive title words (TF-IDF).
"""

from __future__ import annotations

import math
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "knowledge"))

from corpus import DOCS  # noqa: E402
from s1_relations import centroid, embed_all  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
THRESHOLD = 0.20
NEAREST_FLOOR = 0.10
MAX_NEIGHBORS = 8


def related_edges(cen: np.ndarray) -> dict[tuple[int, int], float]:
    c = cen - cen.mean(axis=0)
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    sim = c @ c.T
    np.fill_diagonal(sim, -1)
    edges: dict[tuple[int, int], float] = {}
    for i in range(len(cen)):
        order = np.argsort(-sim[i])[:MAX_NEIGHBORS]
        for rank, j in enumerate(order):
            # strong links, plus the nearest document when it is at least somewhat close, so a
            # bridge document (Redis between Celery and Docker) is not left alone
            if sim[i, j] >= THRESHOLD or (rank == 0 and sim[i, j] >= NEAREST_FLOOR):
                edges[(min(i, j), max(i, j))] = float(sim[i, j])
    return edges


def build_graph(ids: list[str], cen: np.ndarray, derived: dict[str, list[str]]) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(ids)
    for (i, j), w in related_edges(cen).items():
        g.add_edge(ids[i], ids[j], weight=w)
    for doc_id, sources in derived.items():
        for s in sources:
            if s in g and doc_id in g:
                g.add_edge(doc_id, s, weight=1.0)
    return g


def communities(g: nx.Graph, seed: int = 0, resolution: float = 1.0) -> dict[str, int]:
    # Sort nodes so the result does not depend on insertion order, then number the groups by
    # the smallest id they contain (stable labels).
    h = nx.Graph()
    h.add_nodes_from(sorted(g.nodes))
    h.add_weighted_edges_from(sorted((a, b, d["weight"]) for a, b, d in g.edges(data=True)))
    groups = nx.community.louvain_communities(h, weight="weight", seed=seed, resolution=resolution)
    groups = sorted(groups, key=lambda s: min(s))
    return {n: k for k, grp in enumerate(groups) for n in grp}


def nmi(a: list, b: list) -> float:
    n = len(a)
    ca, cb, cab = Counter(a), Counter(b), Counter(zip(a, b, strict=True))
    mi = sum(v / n * math.log((v / n) / ((ca[x] / n) * (cb[y] / n))) for (x, y), v in cab.items())
    ha = -sum(v / n * math.log(v / n) for v in ca.values())
    hb = -sum(v / n * math.log(v / n) for v in cb.values())
    return mi / math.sqrt(ha * hb) if ha and hb else 1.0


def pair_f1(pred: list, truth: list) -> float:
    n = len(pred)
    tp = fp = fn = 0
    for i in range(n):
        for j in range(i + 1, n):
            p, t = pred[i] == pred[j], truth[i] == truth[j]
            tp += p and t
            fp += p and not t
            fn += t and not p
    return 2 * tp / (2 * tp + fp + fn)


STOP = set(
    [
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
    ]
)


def words(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-záéíóúñü0-9]+", text.lower()) if w not in STOP and len(w) > 2
    ]


def name_topics(part: dict[str, int], g: nx.Graph, titles: dict[str, str]) -> dict[int, str]:
    groups: dict[int, list[str]] = {}
    for n, k in part.items():
        groups.setdefault(k, []).append(n)
    df = Counter(w for k in groups for w in {w for n in groups[k] for w in words(titles[n])})
    names = {}
    for k, members in groups.items():
        sub = g.subgraph(members)
        central = max(members, key=lambda n: (sub.degree(n, weight="weight"), n))
        tf = Counter(w for n in members for w in words(titles[n]))
        scored = sorted(tf, key=lambda w: (-(tf[w] * math.log(1 + len(groups) / df[w])), w))
        extra = [w for w in scored if w not in words(titles[central])][:2]
        names[k] = " · ".join([titles[central], *extra]) if len(members) > 1 else titles[central]
    return names


def run(spec: str) -> None:
    name, _, file = spec.partition(":")
    chunks, _ = embed_all(name, file or "model_quantized")
    ids = [d["id"] for d in DOCS]
    titles = {d["id"]: d["title"] for d in DOCS}
    topic = {d["id"]: d["topic"] for d in DOCS}
    derived = {d["id"]: d["derived"] for d in DOCS}
    cen = np.stack([centroid(v) for v in chunks])
    print(f"\n=== {name} ===")
    g = build_graph(ids, cen, derived)
    print(f"graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    for res in (0.6, 0.8, 1.0, 1.2):
        t = time.perf_counter()
        part = communities(g, resolution=res)
        dt = time.perf_counter() - t
        pred = [part[i] for i in ids]
        truth = [topic[i] for i in ids]
        print(
            f"resolution {res}: {len(set(pred))} topics  NMI {nmi(pred, truth):.3f}  "
            f"pairF1 {pair_f1(pred, truth):.3f}  {dt * 1000:.1f} ms"
        )
    part = communities(g)
    names = name_topics(part, g, titles)
    for k in sorted(set(part.values())):
        members = [i for i in ids if part[i] == k]
        print(f"  [{k}] {names[k]}: {', '.join(members)}")

    # stability: same corpus several times, shuffled insertion order, one document less/more
    base = communities(g)
    same = all(communities(g) == base for _ in range(3))
    flips = []
    for seed in range(5):
        order = ids[:]
        random.Random(seed).shuffle(order)
        idx = [ids.index(i) for i in order]
        g2 = build_graph(order, cen[idx], derived)
        p2 = communities(g2)
        flips.append(nmi([base[i] for i in ids], [p2[i] for i in ids]))
    print(f"stability: identical reruns {same}; shuffled insertion NMI vs base {min(flips):.3f}")
    drop = ids.index("redis-broker")
    keep = [i for i in range(len(ids)) if i != drop]
    g3 = build_graph([ids[i] for i in keep], cen[keep], derived)
    p3 = communities(g3)
    common = [ids[i] for i in keep]
    print(
        f"without redis-broker: NMI vs base {nmi([base[i] for i in common], [p3[i] for i in common]):.3f}"
    )


if __name__ == "__main__":
    for spec in sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]:
        run(spec)
