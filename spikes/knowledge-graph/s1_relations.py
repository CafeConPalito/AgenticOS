"""S1: how to measure «related» between documents, and which threshold to use.

Compares, per embedding model, three document similarities:
  centroid  cosine of the mean chunk vectors (one vector per document)
  topk      mean of the 3 best chunk-pair cosines
  maxpair   best chunk-pair cosine
Metrics: separation of same-topic vs other-topic pairs (AUC), neighbour precision@3 by topic,
the best absolute threshold (F1) and the percentile that gives the same quality, and timing
with 300 and 1 000 synthetic documents.
Run from spikes/knowledge:  uv run ../knowledge-graph/s1_relations.py [e5-small gemma2:model_q4 bge-m3]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "knowledge"))

from corpus import DOCS  # noqa: E402
from s4_embed_eval import OnnxEmbedder  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def doc_text(doc: dict, chunk: str) -> str:
    return f"{doc['title']} › {chunk}"


def embed_all(model: str, file: str) -> tuple[list[np.ndarray], float]:
    emb = OnnxEmbedder(model, file)
    t = time.perf_counter()
    out = [emb.encode([doc_text(d, c) for c in d["chunks"]], "passage") for d in DOCS]
    return out, time.perf_counter() - t


def centroid(vecs: np.ndarray) -> np.ndarray:
    c = vecs.mean(axis=0)
    return c / np.linalg.norm(c)


def sim_matrices(chunks: list[np.ndarray]) -> dict[str, np.ndarray]:
    n = len(chunks)
    cen = np.stack([centroid(v) for v in chunks])
    out = {"centroid": cen @ cen.T}
    topk = np.zeros((n, n))
    maxp = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            pair = np.sort((chunks[i] @ chunks[j].T).ravel())[::-1]
            topk[i, j] = pair[:3].mean()
            maxp[i, j] = pair[0]
    out["topk"] = topk
    out["maxpair"] = maxp
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score of a same-topic pair > score of a different-topic pair)."""
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def best_f1(pos: np.ndarray, neg: np.ndarray) -> tuple[float, float]:
    best = (0.0, 0.0)
    for th in np.unique(np.concatenate([pos, neg])):
        tp = (pos >= th).sum()
        fp = (neg >= th).sum()
        fn = (pos < th).sum()
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 > best[0]:
            best = (f1, float(th))
    return best


def precision_at(sim: np.ndarray, topics: list[str], k: int = 3) -> float:
    hits = []
    for i in range(len(topics)):
        order = [j for j in np.argsort(-sim[i]) if j != i][:k]
        hits.append(np.mean([topics[j] == topics[i] for j in order]))
    return float(np.mean(hits))


def scale(chunks: list[np.ndarray], n_docs: int) -> dict[str, float]:
    """Timing of the neighbour computation with n synthetic documents (6 chunks of dim d)."""
    d = chunks[0].shape[1]
    rng = np.random.default_rng(0)
    cen = rng.normal(size=(n_docs, d)).astype(np.float32)
    cen /= np.linalg.norm(cen, axis=1, keepdims=True)
    t = time.perf_counter()
    sim = cen @ cen.T
    np.fill_diagonal(sim, -1)
    np.argpartition(-sim, 8, axis=1)[:, :8]
    full = time.perf_counter() - t
    t = time.perf_counter()
    one = cen @ cen[0]
    np.argpartition(-one, 8)[:8]
    single = time.perf_counter() - t
    ch = rng.normal(size=(n_docs * 6, d)).astype(np.float32)
    ch /= np.linalg.norm(ch, axis=1, keepdims=True)
    t = time.perf_counter()
    _ = ch[:6] @ ch.T  # one document against every chunk
    pairs_one = time.perf_counter() - t
    return {"all_vs_all_s": full, "one_doc_s": single, "one_doc_pairs_s": pairs_one}


def run(spec: str) -> None:
    name, _, file = spec.partition(":")
    file = file or "model_quantized"
    print(f"\n=== {name} ({file}) ===")
    chunks, secs = embed_all(name, file)
    print(f"embedding of {len(DOCS)} docs / {sum(len(c) for c in chunks)} chunks: {secs:.1f}s")
    topics = [d["topic"] for d in DOCS]
    n = len(DOCS)
    iu = np.triu_indices(n, k=1)
    same = np.array([topics[i] == topics[j] for i, j in zip(*iu, strict=True)])
    for kind, sim in sim_matrices(chunks).items():
        v = sim[iu]
        pos, neg = v[same], v[~same]
        f1, th = best_f1(pos, neg)
        print(
            f"{kind:9s} AUC {auc(pos, neg):.3f}  P@3 {precision_at(sim, topics):.3f}  "
            f"same {pos.mean():.3f}±{pos.std():.3f}  other {neg.mean():.3f}±{neg.std():.3f}  "
            f"bestF1 {f1:.3f} @ {th:.3f}"
        )
        if kind == "centroid":
            # threshold as «top p % of all pairs»: how stable is it across models?
            for p in (5, 10, 15):
                cut = np.percentile(v, 100 - p)
                tp = (pos >= cut).sum()
                fp = (neg >= cut).sum()
                print(f"   top {p:2d}% pairs: cut {cut:.3f} precision {tp / max(tp + fp, 1):.2f}")
    print("scale:", {k: round(v, 5) for k, v in scale(chunks, 1000).items()})
    print("scale300:", {k: round(v, 5) for k, v in scale(chunks, 300).items()})


if __name__ == "__main__":
    for spec in sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]:
        run(spec)
