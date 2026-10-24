"""Phase 17 · spike S4: which skills to offer for a task.

Corpus: the registry skills cached by s5_format.py (spikes/out/skills-corpus) plus OWN_SKILLS;
tasks in s4_tasks.py (48 with a fitting skill, 10 without). For every method it reports hit@1,
hit@3 and MRR on the positive tasks and the best threshold on the top score to tell positive
from negative tasks.

Methods: BM25 over «name + description» (no model) · cosine with e5-small, EmbeddingGemma 2 (q4)
and bge-m3, raw and centred on the library mean (phase 15, S1) · hybrid RRF (vector + BM25) ·
the same with the first section of the body added to the skill text.

Run from spikes/knowledge (its models and env):
    uv run --with pyyaml ../skills/s4_selection.py [e5-small gemma2:model_q4 bge-m3]
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "knowledge"))
sys.stdout.reconfigure(encoding="utf-8")

from s4_embed_eval import OnnxEmbedder  # noqa: E402
from s4_tasks import OWN_SKILLS, TASKS  # noqa: E402

REPO = HERE.parents[1]
CORPUS = REPO / "spikes" / "out" / "skills-corpus"
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"
FRONT = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)(.*)", re.S)
WORD = re.compile(r"[\wáéíóúüñ]+", re.I)
STOP = set(
    [
        "a",
        "al",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "la",
        "las",
        "los",
        "of",
        "on",
        "or",
        "para",
        "por",
        "que",
        "se",
        "the",
        "this",
        "to",
        "un",
        "una",
        "use",
        "used",
        "uses",
        "using",
        "when",
        "with",
        "y",
    ]
)
RRF_K = 60


def load_skills() -> list[dict]:
    skills = [dict(s, body="") for s in OWN_SKILLS]
    for path in sorted(CORPUS.glob("*.json")):
        files = {f["path"]: f["contents"] for f in json.loads(path.read_text("utf-8"))["files"]}
        md = next(v for k, v in files.items() if k.lower() == "skill.md").lstrip("﻿")
        match = FRONT.match(md)
        meta = yaml.safe_load(match.group(1))
        body = match.group(2).strip()
        first = re.split(r"\n#{1,3} ", "\n" + body, maxsplit=2)
        section = (first[1] if len(first) > 1 else body)[:600]
        skills.append(
            {"name": meta["name"], "description": str(meta["description"]), "body": section}
        )
    seen, unique = set(), []
    for skill in skills:  # the same skill may be in several rankings
        if skill["name"] not in seen:
            seen.add(skill["name"])
            unique.append(skill)
    return unique


def skill_text(skill: dict, with_body: bool) -> str:
    text = f"{skill['name'].replace('-', ' ')}: {skill['description']}"
    return f"{text}\n{skill['body']}" if with_body and skill["body"] else text


def task_text(task: tuple) -> str:
    title, description, stage, role, _ = task
    return f"{title}. {description} Etapa: {stage}. Rol: {role}."


def tokens(text: str) -> list[str]:
    return [w for w in (m.lower() for m in WORD.findall(text)) if w not in STOP and len(w) > 1]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75) -> None:
        self.docs = [Counter(tokens(d)) for d in docs]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths)
        df = Counter(w for d in self.docs for w in d)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(len(self.docs))
        for w in set(tokens(query)):
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i, doc in enumerate(self.docs):
                tf = doc.get(w)
                if tf:
                    norm = (
                        tf
                        * (self.k1 + 1)
                        / (tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg))
                    )
                    out[i] += idf * norm
        return out


def rrf(*rankings: np.ndarray) -> np.ndarray:
    out = np.zeros(len(rankings[0]))
    for scores in rankings:
        order = np.argsort(-scores)
        for rank, index in enumerate(order):
            out[index] += 1 / (RRF_K + rank + 1)
    return out


def evaluate(name: str, matrix: np.ndarray, skills: list[dict]) -> dict:
    """`matrix`: tasks × skills scores. Hit metrics on positives; threshold on top score."""
    names = [s["name"] for s in skills]
    hit1 = hit3 = 0
    mrr = 0.0
    misses = []
    top_pos, top_neg = [], []
    for row, task in zip(matrix, TASKS, strict=True):
        order = np.argsort(-row)
        expected = task[4]
        if not expected:
            top_neg.append(float(row[order[0]]))
            continue
        ranks = [i for i, idx in enumerate(order) if names[idx] in expected]
        first = ranks[0] if ranks else len(order)
        hit1 += first == 0
        hit3 += first < 3
        mrr += 1 / (first + 1)
        top_pos.append(float(row[order[0]]))
        if first >= 3:
            misses.append(f"{task[0]} → {[names[i] for i in order[:3]]} (esperada {expected})")
    positives = len(top_pos)
    # best threshold: positives whose top passes and that were a hit@3, vs negatives filtered
    best = None
    for t in sorted(set(top_pos + top_neg)):
        kept = sum(1 for s in top_pos if s >= t)
        rejected = sum(1 for s in top_neg if s < t)
        score = kept / positives + rejected / len(top_neg)
        if best is None or score > best[0]:
            best = (score, t, kept, rejected)
    return {
        "method": name,
        "hit@1": round(hit1 / positives, 3),
        "hit@3": round(hit3 / positives, 3),
        "mrr": round(mrr / positives, 3),
        "threshold": round(best[1], 4),
        "positives_kept": f"{best[2]}/{positives}",
        "negatives_filtered": f"{best[3]}/{len(top_neg)}",
        "misses": misses,
    }


def main() -> None:
    models = sys.argv[1:] or ["e5-small", "gemma2:model_q4", "bge-m3"]
    skills = load_skills()
    queries = [task_text(t) for t in TASKS]
    results = []
    for with_body in (False, True):
        tag = "+cuerpo" if with_body else ""
        docs = [skill_text(s, with_body) for s in skills]
        bm25 = BM25(docs)
        lexical = np.array([bm25.scores(q) for q in queries])
        results.append(evaluate(f"bm25{tag}", lexical, skills))
        for spec in models:
            model, _, file = spec.partition(":")
            started = time.perf_counter()
            embedder = OnnxEmbedder(model, file or "model_quantized")
            doc_vecs = embedder.encode(docs, "doc")
            query_vecs = embedder.encode(queries, "query")
            took = time.perf_counter() - started
            raw = query_vecs @ doc_vecs.T
            mean = doc_vecs.mean(axis=0)
            d = doc_vecs - mean
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            q = query_vecs - mean
            q /= np.linalg.norm(q, axis=1, keepdims=True)
            centred = q @ d.T
            for label, matrix in ((model, raw), (f"{model} centrado", centred)):
                entry = evaluate(f"{label}{tag}", matrix, skills)
                entry["seconds"] = round(took, 1)
                results.append(entry)
            hybrid = np.array([rrf(c, w) for c, w in zip(centred, lexical, strict=True)])
            results.append(evaluate(f"híbrido {model}{tag}", hybrid, skills))
    for entry in results:
        print(
            f"{entry['method']:<32} hit@1 {entry['hit@1']:.3f}  hit@3 {entry['hit@3']:.3f}  "
            f"mrr {entry['mrr']:.3f}  umbral {entry['threshold']:<8} "
            f"pos {entry['positives_kept']:<6} neg {entry['negatives_filtered']}"
        )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s4-selection-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps(
            {"skills": len(skills), "tasks": len(TASKS), "results": results},
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )
    print(f"{len(skills)} skills, {len(TASKS)} tareas · evidence: {out}")


if __name__ == "__main__":
    main()
