"""Phase 17 · spike S4c: the selection measured like the product does it (block 11).

S4 embedded in batches; the product embeds each skill and each task alone, and padding moves the
vectors a little (cosine 0.997 between the same text alone and in a batch), which matters with e5,
whose scores sit within thousandths of each other. With every text embedded alone, on the S4
corpus (82 skills) and on the test corpus (20 skills, 7 of them Spanish), it compares:
  raw      cosine, skills with the document prefix, tasks with the query prefix (S4's choice);
  sym      both with the query prefix (e5's advice for symmetric similarity);
  centred  raw, centred on the library's mean (removes what every skill shares, e.g. language);
  csym     sym, centred;
  hybrid   RRF of raw and the product's BM25 (stems, relative score).
and the floor that keeps 90 % of the hits.

Run from spikes/knowledge:  uv run --with pyyaml python ../skills/s4c_single.py [models…]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "knowledge"))
sys.stdout.reconfigure(encoding="utf-8")

from s4_embed_eval import OnnxEmbedder  # noqa: E402
from s4_selection import load_skills, task_text  # noqa: E402
from s4_tasks import TASKS  # noqa: E402
from s4b_words import bm25  # noqa: E402

REPO = HERE.parents[1]
TEST_CORPUS = REPO / "backend" / "tests" / "fixtures" / "skills" / "corpus.json"
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"


def corpora() -> dict[str, tuple[list[tuple[str, str]], list[tuple[str, list[str]]]]]:
    s4 = load_skills()
    test = json.loads(TEST_CORPUS.read_text("utf-8"))
    return {
        "S4 (82)": (
            [(s["name"], s["description"]) for s in s4],
            [(task_text(t), t[4]) for t in TASKS if t[4]],
        ),
        "test (20)": (
            [(s["name"], s["description"]) for s in test["skills"]],
            [(t["text"], t["expected"]) for t in test["tasks"]],
        ),
    }


def one_by_one(embedder: OnnxEmbedder, texts: list[str], kind: str) -> np.ndarray:
    return np.concatenate([embedder.encode([t], kind) for t in texts])


def rrf(*rows: np.ndarray, k: int = 60) -> np.ndarray:
    out = np.zeros(len(rows[0]))
    for row in rows:
        for rank, index in enumerate(np.argsort(-row)):
            out[index] += 1 / (k + rank + 1)
    return out


def hit3(matrix: np.ndarray, names: list[str], tasks) -> tuple[float, float]:
    """hit@3 and the score that keeps 90 % of the hits (the floor to choose)."""
    hits, scores = 0, []
    for row, (_, expected) in zip(matrix, tasks, strict=True):
        top = list(np.argsort(-row)[:3])
        found = [row[i] for i in top if names[i] in expected]
        if found:
            hits += 1
            scores.append(max(found))
    return hits / len(tasks), float(np.percentile(scores, 10)) if scores else 0.0


def main() -> None:
    models = sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]
    data = corpora()
    report: dict = {}
    for spec in models:
        model, _, file = spec.partition(":")
        embedder = OnnxEmbedder(model, file or "model_quantized")
        for corpus, (skills, tasks) in data.items():
            names = [n for n, _ in skills]
            docs = [f"{n.replace('-', ' ')}: {d}" for n, d in skills]
            queries = [t for t, _ in tasks]
            started = time.perf_counter()
            d_doc = one_by_one(embedder, docs, "doc")
            d_query = one_by_one(embedder, docs, "query")
            q = one_by_one(embedder, queries, "query")
            took = time.perf_counter() - started

            def centred(d: np.ndarray, qq: np.ndarray) -> np.ndarray:
                mean = d.mean(axis=0)
                dc = d - mean
                qc = qq - mean
                dc /= np.linalg.norm(dc, axis=1, keepdims=True)
                qc /= np.linalg.norm(qc, axis=1, keepdims=True)
                return qc @ dc.T

            words = np.array([bm25(query, docs, True)[0] for query in queries])
            variants = {
                "raw": q @ d_doc.T,
                "sym": q @ d_query.T,
                "centred": centred(d_doc, q),
                "csym": centred(d_query, q),
            }
            variants["hybrid"] = np.array(
                [rrf(r, w) for r, w in zip(variants["raw"], words, strict=True)]
            )
            variants["hybrid csym"] = np.array(
                [rrf(r, w) for r, w in zip(variants["csym"], words, strict=True)]
            )
            for name, matrix in variants.items():
                rate, floor = hit3(matrix, names, tasks)
                report.setdefault(corpus, {}).setdefault(model, {})[name] = {
                    "hit@3": round(rate, 3),
                    "floor_p10": round(floor, 3),
                }
                print(f"{corpus:<10} {model:<10} {name:<12} hit@3 {rate:.3f}  p10 {floor:.3f}")
            print(f"{corpus:<10} {model:<10} ({took:.1f} s)")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "s4c-single.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
