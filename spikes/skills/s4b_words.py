"""Phase 17 · spike S4b: the no-model ranking (BM25) for any library size.

The fixed floor of S4 (BM25 ≥ ~6 on 82 skills) does not hold for a library of five: scores grow
with the IDF, i.e. with the number of skills. This compares, on the S4 corpus and on random
subsets of 5, 10 and 20 skills that contain the expected one:
  - tokens as in S4, or without accents and cut to a 5-letter stem («migración» ~ «migraciones»);
  - an absolute floor, or a floor on the score divided by the best score a query could get
    (the sum of the IDF of its words that appear in the library).

Run from the repo root:  uv run --project backend python spikes/skills/s4b_words.py
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8")

from s4_selection import STOP, load_skills, task_text  # noqa: E402
from s4_tasks import TASKS  # noqa: E402

WORD = re.compile(r"[\w]+", re.U)


def plain(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def tokens(text: str, stem: bool) -> list[str]:
    words = [w for w in WORD.findall(plain(text)) if w not in STOP and len(w) > 1]
    return [w[:5] if stem else w for w in words]


def bm25(query: str, docs: list[str], stem: bool) -> tuple[list[float], float]:
    """Scores and the best score the query could get in this library."""
    bags = [Counter(tokens(d, stem)) for d in docs]
    lengths = [sum(b.values()) for b in bags]
    avg = sum(lengths) / len(lengths)
    df = Counter(w for b in bags for w in b)
    n = len(bags)
    scores = [0.0] * n
    best = 0.0
    for w in set(tokens(query, stem)):
        if w not in df:
            continue
        idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
        best += idf * 2.2  # tf = 1, k1 + 1
        for i, b in enumerate(bags):
            tf = b.get(w)
            if tf:
                scores[i] += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / avg))
    return scores, best


def evaluate(skills: list[dict], tasks: list, stem: bool, floor: float, relative: bool) -> dict:
    docs = [f"{s['name'].replace('-', ' ')}: {s['description']}" for s in skills]
    names = [s["name"] for s in skills]
    hit = pos = neg_ok = neg = 0
    for task in tasks:
        scores, best = bm25(task_text(task), docs, stem)
        value = [s / best if relative and best else s for s in scores]
        order = [i for i in sorted(range(len(docs)), key=lambda i: -value[i]) if value[i] >= floor]
        top = [names[i] for i in order[:3]]
        if task[4]:
            pos += 1
            hit += any(n in task[4] for n in top)
        else:
            neg += 1
            neg_ok += not top
    return {
        "hit@3": round(hit / pos, 3) if pos else None,
        "neg_filtered": round(neg_ok / neg, 2) if neg else None,
    }


def main() -> None:
    skills = load_skills()
    by_name = {s["name"]: s for s in skills}
    random.seed(0)
    results = {}
    configs = [
        ("S4 (sin raíz, absoluto 3.0)", False, 3.0, False),
        ("raíz, absoluto 3.0", True, 3.0, False),
        ("raíz, relativo 0.10", True, 0.10, True),
        ("raíz, relativo 0.15", True, 0.15, True),
        ("raíz, relativo 0.20", True, 0.20, True),
        ("raíz, relativo 0.30", True, 0.30, True),
    ]
    for size in (5, 10, 20, len(skills)):
        for label, stem, floor, relative in configs:
            hits, negs = [], []
            for task in TASKS:
                for _ in range(1 if size == len(skills) else 5):
                    if size == len(skills):
                        sample = skills
                    else:
                        wanted = [by_name[n] for n in task[4] if n in by_name][:1]
                        rest = [s for s in skills if s not in wanted]
                        sample = wanted + random.sample(rest, size - len(wanted))
                    r = evaluate(sample, [task], stem, floor, relative)
                    (hits if task[4] else negs).append(r["hit@3"] if task[4] else r["neg_filtered"])
            key = f"{size:>3} skills · {label}"
            results[key] = {
                "hit@3": round(sum(hits) / len(hits), 3),
                "neg_filtered": round(sum(negs) / len(negs), 2),
            }
            print(
                f"{key:<42} hit@3 {results[key]['hit@3']:.3f}  sin skill filtradas "
                f"{results[key]['neg_filtered']:.2f}"
            )
    out = HERE.parents[1] / "docs" / "phases" / "17-skills" / "evidencias" / "s4b-words.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
