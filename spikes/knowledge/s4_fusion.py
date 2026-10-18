"""S4b: fusion strategies for words + vectors. Encodes the 30 passages/queries once per model."""

import re
import sqlite3
import sys

import numpy as np
from facts import FACTS
from s4_embed_eval import STOP, OnnxEmbedder, metrics, strip_accents

sys.stdout.reconfigure(encoding="utf-8")

passages = [f"{f['title']}\n{f['body']}" for f in FACTS]
queries = [f["q"] for f in FACTS]
kinds = [f["kind"] for f in FACTS]
gold = list(range(len(FACTS)))

db = sqlite3.connect(":memory:")
db.execute("create virtual table t using fts5(body, tokenize='unicode61 remove_diacritics 2')")
for i, p in enumerate(passages):
    db.execute("insert into t(rowid, body) values (?, ?)", (i, p))


def is_ident(t):  # codes, versions, paths, flags: the terms where exact match matters
    return bool(re.search(r"[\d_/.\-+]", t)) or (t.isupper() and len(t) > 2)


def words(q, mode):
    terms = [t for t in re.findall(r"[\w./+\-]+", q)]
    terms = [
        t
        for t in terms
        if strip_accents(t.lower()) not in STOP and (len(t) > 2 or any(c.isdigit() for c in t))
    ]
    if mode == "ident":
        terms = [t for t in terms if is_ident(t)]
    if not terms:
        return [], {}
    expr = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    rows = db.execute(
        "select rowid, bm25(t) from t where t match ? order by bm25(t) limit 50", (expr,)
    ).fetchall()
    return [r[0] for r in rows], {r[0]: -r[1] for r in rows}


def rrf(lists, weights, k=60):
    sc = {}
    for lst, w in zip(lists, weights):
        for pos, d in enumerate(lst):
            sc[d] = sc.get(d, 0) + w / (k + pos + 1)
    return sorted(sc, key=sc.get, reverse=True)


def evaluate(pm, qm):
    res = {}
    for qi, q in enumerate(queries):
        cos = pm @ qm[qi]
        vec = list(np.argsort(-cos)[:50])
        w_all, _ = words(q, "all")
        w_id, id_sc = words(q, "ident")
        has_id = bool(w_id)
        r = {
            "vector": vec,
            "rrf_all": rrf([vec, w_all], [1, 1]),
            "rrf_all_w3": rrf([vec, w_all], [3, 1]),
            "rrf_all_top3": rrf([vec, w_all[:3]], [1, 1]),
            "rrf_ident_only": rrf([vec, w_id], [1, 1]),
            "rrf_ident_w2": rrf([vec, w_id], [1, 2]),
            "gated": rrf([vec, w_id if has_id else []], [1, 2]),
        }
        res[qi] = r
    out = {}
    for mode in res[0]:
        row = {}
        for label, sel in (
            ("all", range(30)),
            ("para", [i for i, k in enumerate(kinds) if k == "paraphrase"]),
            ("exact", [i for i, k in enumerate(kinds) if k == "exact"]),
        ):
            row[label] = metrics([res[i][mode] for i in sel], [gold[i] for i in sel])
        out[mode] = row
    return out


if __name__ == "__main__":
    for name, f in (
        ("e5-small", "model_quantized"),
        ("gemma2", "model_q4"),
        ("bge-m3", "model_quantized"),
    ):
        e = OnnxEmbedder(name, f)
        pm, qm = e.encode(passages, "passage"), e.encode(queries, "query")
        print(f"\n### {name}")
        for mode, row in evaluate(pm, qm).items():
            print(
                f"  {mode:15} "
                + "  ".join(f"{k}: t1={v[0]:.2f} t5={v[1]:.2f}" for k, v in row.items())
            )
