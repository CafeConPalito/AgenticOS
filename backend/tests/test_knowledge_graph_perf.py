"""The graph stays cheap with a big library (phase 15, CA10): the links of 1 000 documents, the
topics of 300 and the graph read by the screen. Generous limits; the measured times are in the
spike (9 ms for the links of 1 000 documents)."""

import time

import numpy as np

from agentic_os.services.knowledge import graph, topics


def clustered(count: int, groups: int, dims: int = 384, seed: int = 3):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(groups, dims))
    rows = centers[np.arange(count) % groups] + rng.normal(0, 0.6, size=(count, dims))
    rows /= np.linalg.norm(rows, axis=1, keepdims=True)
    return [f"doc-{i:04d}" for i in range(count)], rows.astype(np.float32)


def test_the_links_of_a_thousand_documents_take_a_blink():
    ids, matrix = clustered(1000, 20)
    started = time.perf_counter()
    links = graph.related_links(ids, matrix, threshold=0.2, max_neighbors=8, raw_threshold=0.9)
    elapsed = time.perf_counter() - started
    assert len(links) > 500
    assert len(links) <= 8 * len(ids)
    assert elapsed < 2.0, elapsed


def test_the_topics_of_three_hundred_documents_with_a_thousand_links():
    ids, matrix = clustered(300, 12)
    links = graph.related_links(ids, matrix, threshold=0.2, max_neighbors=8, raw_threshold=0.9)
    related = [(link.a, link.b, link.weight) for link in links]
    titles = {i: f"Documento {i}" for i in ids}
    started = time.perf_counter()
    found = topics.compute(ids, titles, [], related)
    elapsed = time.perf_counter() - started
    assert 2 <= len([t for t in found if not t.loose]) <= 40
    assert sum(len(t.doc_ids) for t in found) == 300
    assert elapsed < 2.0, elapsed
