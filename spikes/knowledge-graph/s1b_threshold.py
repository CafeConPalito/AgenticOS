"""S1b: a threshold that works across models. Raw cosines are model-dependent (e5: 0.87 vs 0.91).

Tries on the centroids: (a) raw cosine, (b) cosine after subtracting the corpus mean vector
(removes the shared direction that squeezes e5's range), (c) per-row z-score. For each, the edge
precision/recall at a few cut points against the topic ground truth, with a neighbour cap of 8.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "knowledge"))

from corpus import DOCS  # noqa: E402
from s1_relations import centroid, embed_all  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

TOPICS = [d["topic"] for d in DOCS]
N = len(DOCS)
IU = np.triu_indices(N, k=1)
TRUE = np.array([TOPICS[i] == TOPICS[j] for i, j in zip(*IU, strict=True)])


def report(label: str, sim: np.ndarray, cuts: list[float]) -> None:
    v = sim[IU]
    line = []
    for c in cuts:
        pred = v >= c
        tp = (pred & TRUE).sum()
        prec = tp / max(pred.sum(), 1)
        rec = tp / TRUE.sum()
        line.append(f"{c:+.2f}: P{prec:.2f} R{rec:.2f}")
    print(f"  {label:16s} " + " | ".join(line))


def run(spec: str) -> None:
    name, _, file = spec.partition(":")
    chunks, _ = embed_all(name, file or "model_quantized")
    cen = np.stack([centroid(v) for v in chunks])
    print(f"\n=== {name} ===")
    raw = cen @ cen.T
    report("raw cosine", raw, [float(np.percentile(raw[IU], p)) for p in (80, 88, 94)])

    mean = cen.mean(axis=0)
    c2 = cen - mean
    c2 /= np.linalg.norm(c2, axis=1, keepdims=True)
    centered = c2 @ c2.T
    report("mean-centered", centered, [0.2, 0.3, 0.4, 0.5, 0.6])

    z = (raw - raw.mean(axis=1, keepdims=True)) / raw.std(axis=1, keepdims=True)
    zs = np.minimum(z, z.T)  # an edge needs both ends to find the other unusual
    report("row z-score", zs, [1.0, 1.5, 2.0, 2.5])


if __name__ == "__main__":
    for spec in sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]:
        run(spec)
