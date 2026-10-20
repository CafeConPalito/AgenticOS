"""S4: compare embedding models (ONNX, CPU) on the synthetic Spanish corpus.

Metrics per model and mode (vector / words / hybrid RRF), split by question kind:
top-1, top-5 and MRR; plus load time, encode speed, query latency and peak memory.
Run: uv run s4_embed_eval.py [e5-small gemma2:model_quantized gemma2:model_q4 bge-m3]
"""

from __future__ import annotations

import re
import sqlite3
import sys
import time

import numpy as np
import onnxruntime as ort
import psutil
from facts import FACTS
from tokenizers import Tokenizer

sys.stdout.reconfigure(encoding="utf-8")
THREADS = 6  # half of the 12 logical cores, the plan's default
MAX_LEN = 512


class OnnxEmbedder:
    def __init__(self, name: str, file: str = "model_quantized") -> None:
        self.name = name
        base = f"models/{name}"
        t = time.perf_counter()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = THREADS
        self.session = ort.InferenceSession(
            f"{base}/onnx/{file}.onnx", opts, providers=["CPUExecutionProvider"]
        )
        self.load_s = time.perf_counter() - t
        self.tok = Tokenizer.from_file(f"{base}/tokenizer.json")
        self.tok.enable_truncation(max_length=MAX_LEN)
        pad_id = 0
        if name == "gemma2":
            pad_id = self.tok.token_to_id("<pad>") or 0
        elif name == "bge-m3" or name == "e5-small":
            pad_id = self.tok.token_to_id("<pad>") or 1
        self.tok.enable_padding(pad_id=pad_id, pad_token=self.tok.id_to_token(pad_id) or "<pad>")
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.q_prefix, self.d_prefix = {
            "e5-small": ("query: ", "passage: "),
            "bge-m3": ("", ""),
            "gemma2": ("task: search result | query: ", "title: none | text: "),
        }[name]

    def encode(self, texts: list[str], kind: str, batch: int = 16) -> np.ndarray:
        prefix = self.q_prefix if kind == "query" else self.d_prefix
        out = []
        # sort by length so padding stays small
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        for s in range(0, len(order), batch):
            idx = order[s : s + batch]
            enc = self.tok.encode_batch([prefix + texts[i] for i in idx])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            for extra in ("image_features", "video_features", "audio_features"):
                if extra in self.inputs:
                    feed[extra] = np.zeros((0, 512), dtype=np.float32)
            names = [o.name for o in self.session.get_outputs()]
            res = dict(zip(names, self.session.run(None, feed), strict=True))
            if "sentence_embedding" in res:
                vec = res["sentence_embedding"]
            else:
                hid = res["last_hidden_state"]
                if self.name == "bge-m3":
                    vec = hid[:, 0]
                else:
                    m = mask[:, :, None].astype(np.float32)
                    vec = (hid * m).sum(1) / m.sum(1)
            vec = vec / np.linalg.norm(vec, axis=1, keepdims=True)
            out.append((idx, vec))
        mat = np.zeros((len(texts), out[0][1].shape[1]), dtype=np.float32)
        for idx, vec in out:
            mat[idx] = vec
        return mat


STOP = set(
    [
        "a",
        "al",
        "algo",
        "algunos",
        "ante",
        "antes",
        "aqui",
        "asi",
        "aun",
        "cada",
        "como",
        "con",
        "contra",
        "cual",
        "cuando",
        "cuanto",
        "de",
        "del",
        "desde",
        "donde",
        "durante",
        "e",
        "el",
        "ella",
        "ellas",
        "ellos",
        "en",
        "entre",
        "era",
        "es",
        "esa",
        "esas",
        "ese",
        "eso",
        "esos",
        "esta",
        "estan",
        "estar",
        "este",
        "esto",
        "estos",
        "fue",
        "ha",
        "han",
        "hay",
        "hasta",
        "hace",
        "hacer",
        "hago",
        "la",
        "las",
        "le",
        "les",
        "lo",
        "los",
        "mas",
        "me",
        "mi",
        "mis",
        "mucho",
        "muy",
        "nada",
        "ni",
        "no",
        "nos",
        "o",
        "os",
        "otra",
        "otro",
        "para",
        "pero",
        "poco",
        "por",
        "porque",
        "puedo",
        "puede",
        "pueden",
        "que",
        "quien",
        "se",
        "ser",
        "si",
        "sin",
        "sobre",
        "su",
        "sus",
        "tambien",
        "tanto",
        "te",
        "tengo",
        "tiene",
        "todo",
        "todos",
        "tu",
        "tus",
        "un",
        "una",
        "uno",
        "unos",
        "va",
        "voy",
        "vez",
        "y",
        "ya",
        "yo",
    ]
)


def strip_accents(w: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")


def fts_terms(query: str, drop_stop: bool) -> list[str]:
    terms = re.findall(r"\w+", query)
    if not drop_stop:
        return terms
    return [
        t
        for t in terms
        if strip_accents(t.lower()) not in STOP and (len(t) > 2 or any(c.isdigit() for c in t))
    ]


def fts_rank(passages: list[str], query: str, drop_stop: bool = False) -> list[int]:
    db = sqlite3.connect(":memory:")
    db.execute("create virtual table t using fts5(body, tokenize='unicode61 remove_diacritics 2')")
    for i, p in enumerate(passages):
        db.execute("insert into t(rowid, body) values (?, ?)", (i, p))
    terms = fts_terms(query, drop_stop)
    if not terms:
        return []
    expr = " OR ".join(f'"{w}"' for w in terms)
    return [
        r[0]
        for r in db.execute(
            "select rowid from t where t match ? order by bm25(t) limit 50", (expr,)
        )
    ]


def rrf(*rankings: list[int], k: int = 60, weights: tuple[float, ...] | None = None) -> list[int]:
    score: dict[int, float] = {}
    for n, r in enumerate(rankings):
        w = weights[n] if weights else 1.0
        for pos, doc in enumerate(r):
            score[doc] = score.get(doc, 0.0) + w / (k + pos + 1)
    return sorted(score, key=score.get, reverse=True)


def metrics(ranks: list[list[int]], gold: list[int]) -> tuple[float, float, float]:
    top1 = top5 = mrr = 0.0
    for r, g in zip(ranks, gold, strict=True):
        if r[:1] == [g]:
            top1 += 1
        if g in r[:5]:
            top5 += 1
        if g in r:
            mrr += 1.0 / (r.index(g) + 1)
    n = len(gold)
    return top1 / n, top5 / n, mrr / n


def quantize_int8(m: np.ndarray) -> np.ndarray:
    scale = np.abs(m).max(axis=1, keepdims=True) / 127.0
    return (np.round(m / scale).astype(np.int8).astype(np.float32)) * scale


def evaluate(spec: str) -> None:
    name, _, file = spec.partition(":")
    file = file or "model_quantized"
    proc = psutil.Process()
    rss0 = proc.memory_info().rss
    emb = OnnxEmbedder(name, file)
    passages = [f"{f['title']}\n{f['body']}" for f in FACTS]
    queries = [f["q"] for f in FACTS]
    gold = list(range(len(FACTS)))
    kinds = [f["kind"] for f in FACTS]

    t = time.perf_counter()
    pm = emb.encode(passages, "passage")
    enc_small = time.perf_counter() - t
    qm = emb.encode(queries, "query")
    peak = proc.memory_info().rss

    # speed on realistic chunks (~350 tokens): 5 facts glued together, 48 chunks
    long = ["\n\n".join(passages[(i + j) % len(passages)] for j in range(5)) for i in range(48)]
    t = time.perf_counter()
    emb.encode(long, "passage")
    long_s = time.perf_counter() - t
    t = time.perf_counter()
    for q in queries[:10]:
        emb.encode([q], "query", batch=1)
    q_ms = (time.perf_counter() - t) / 10 * 1000
    peak = max(peak, proc.memory_info().rss)

    def run(mode: str, pmat: np.ndarray) -> dict[str, tuple[float, float, float]]:
        ranks = []
        for qi, q in enumerate(queries):
            vec = list(np.argsort(-(pmat @ qm[qi]))[:50])
            words = fts_rank(passages, q)
            words_sw = fts_rank(passages, q, drop_stop=True)
            ranks.append(
                {
                    "vector": vec,
                    "words": words_sw,
                    "hybrid_raw": rrf(vec, words),
                    "hybrid": rrf(vec, words_sw),
                    "hybrid_w2": rrf(vec, words_sw, weights=(2.0, 1.0)),
                }[mode]
            )
        res = {}
        for label, sel in (
            ("all", range(len(gold))),
            ("paraphrase", [i for i, k in enumerate(kinds) if k == "paraphrase"]),
            ("exact", [i for i, k in enumerate(kinds) if k == "exact"]),
        ):
            res[label] = metrics([ranks[i] for i in sel], [gold[i] for i in sel])
        return res

    print(
        f"\n### {name}:{file}  dim={pm.shape[1]}  load={emb.load_s:.1f}s  encode30={enc_small:.1f}s  "
        f"48x~350tok={long_s:.1f}s ({48 / long_s:.1f} chunks/s -> 1000 chunks ~ {1000 * long_s / 48:.0f}s)  "
        f"query={q_ms:.0f}ms  peakRSS=+{(peak - rss0) / 1e6:.0f}MB"
    )
    for mode in ("vector", "words", "hybrid_raw", "hybrid", "hybrid_w2"):
        r = run(mode, pm)
        print(
            f"  {mode:7} "
            + "  ".join(
                f"{k}: top1={v[0]:.2f} top5={v[1]:.2f} mrr={v[2]:.2f}" for k, v in r.items()
            )
        )
    r8 = run("hybrid_w2", quantize_int8(pm))
    print(
        "  hybrid_w2+int8 vectors: "
        + "  ".join(f"{k}: top1={v[0]:.2f} top5={v[1]:.2f}" for k, v in r8.items())
    )


if __name__ == "__main__":
    for spec in sys.argv[1:] or ["e5-small", "gemma2:model_quantized", "gemma2:model_q4", "bge-m3"]:
        evaluate(spec)
