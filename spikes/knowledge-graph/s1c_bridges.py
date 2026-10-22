"""S1c: do the bridge documents (Redis between Celery and Docker) get linked? Prints the top
neighbours (mean-centered cosine of centroids) of a few documents, per model."""

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
ids = [d["id"] for d in DOCS]
SHOW = [
    "redis-broker",
    "celery-manual",
    "docker-compose",
    "celery-colas",
    "auth-oauth",
    "pg-indices",
]

for spec in sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]:
    name, _, file = spec.partition(":")
    chunks, _ = embed_all(name, file or "model_quantized")
    cen = np.stack([centroid(v) for v in chunks])
    c = cen - cen.mean(axis=0)
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    sim = c @ c.T
    print(f"\n=== {name} ===")
    for doc in SHOW:
        i = ids.index(doc)
        order = [j for j in np.argsort(-sim[i]) if j != i][:4]
        print(f"{doc:16s} " + "  ".join(f"{ids[j]} {sim[i, j]:.2f}" for j in order))
