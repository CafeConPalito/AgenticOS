"""Turning text into vectors, for the search by meaning (phase 14, block 5).

`OnnxEmbedder` runs inside the knowledge worker (ONNX Runtime on the CPU plus `tokenizers`, no
PyTorch): it follows the model's own recipe from the catalog (prefixes, pooling, extra inputs) and
returns L2-normalized vectors, so a dot product is the cosine similarity. The backend side
(`embed`) sends texts to a worker in batches and gets the vectors back packed as `float32`.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from agentic_os.services.knowledge.errors import KnowledgeError

BATCH = 16  # texts run through the model together (sorted by length so padding stays small)
REQUEST = 64  # texts per request to the worker: progress and memory stay reasonable

Progress = Callable[[int, int], None]
_embedders: dict[tuple, OnnxEmbedder] = {}


class OnnxEmbedder:
    def __init__(self, spec: dict[str, Any], threads: int) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.usage = spec["usage"]
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            spec["model"], options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(spec["tokenizer"])
        self.tokenizer.enable_truncation(max_length=int(self.usage["max_length"]))
        pad = self.tokenizer.token_to_id("<pad>")
        pad_id = 0 if pad is None else pad
        self.tokenizer.enable_padding(pad_id=pad_id, pad_token=self.tokenizer.id_to_token(pad_id))
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.outputs = [o.name for o in self.session.get_outputs()]
        self.dimensions = int(self.usage["dimensions"])

    def encode(self, texts: Sequence[str], kind: str) -> np.ndarray:
        """`kind`: «passage» for the text of a document, «query» for what is searched."""
        prefix = self.usage["query_prefix" if kind == "query" else "document_prefix"]
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        result = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for offset in range(0, len(order), BATCH):
            indexes = order[offset : offset + BATCH]
            result[indexes] = self._run([prefix + texts[i] for i in indexes])
        return result

    def _run(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed: dict[str, np.ndarray] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        for name in self.usage.get("empty_inputs", ()):
            if name in self.inputs:  # the text model of EmbeddingGemma still asks for these
                feed[name] = np.zeros((0, 512), dtype=np.float32)
        outputs = dict(zip(self.outputs, self.session.run(None, feed), strict=True))
        pooling = self.usage["pooling"]
        if pooling == "sentence_embedding":
            vectors = outputs["sentence_embedding"]
        else:
            hidden = outputs["last_hidden_state"]
            if pooling == "cls":
                vectors = hidden[:, 0]
            else:  # mean of the real tokens
                weights = mask[:, :, None].astype(np.float32)
                vectors = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return (vectors / np.maximum(norms, 1e-12)).astype(np.float32)


def embedder(spec: dict[str, Any], threads: int) -> OnnxEmbedder:
    """The embedder for this model, created once per worker process (loading takes a moment)."""
    key = (spec["model"], threads)
    if key not in _embedders:
        _embedders.clear()  # one model in memory at a time
        _embedders[key] = OnnxEmbedder(spec, threads)
    return _embedders[key]


# ------------------------------------------------------------------ packing for the pipe
def pack(vectors: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(vectors, dtype=np.float32).tobytes()).decode()


def unpack(data: str, dimensions: int) -> np.ndarray:
    flat = np.frombuffer(base64.b64decode(data), dtype=np.float32)
    return flat.reshape(-1, dimensions).copy()


def vector_bytes(vector: np.ndarray) -> bytes:
    return np.ascontiguousarray(vector, dtype=np.float32).tobytes()


def vector_from(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# --------------------------------------------------------------------- the backend side
def embed(
    worker,
    spec: dict[str, Any],
    texts: Sequence[str],
    kind: str,
    threads: int = 0,
    progress: Progress | None = None,
) -> np.ndarray:
    """The vectors of `texts`, asked of `worker` in batches. Raises `KnowledgeError`."""
    dimensions = int(spec["usage"]["dimensions"])
    parts: list[np.ndarray] = []
    done = 0
    for offset in range(0, len(texts), REQUEST):
        batch = list(texts[offset : offset + REQUEST])
        answer = worker.request(
            {"op": "embed", "model": spec, "texts": batch, "kind": kind, "threads": threads}
        )
        if not answer.get("ok"):
            raise KnowledgeError(
                answer.get("code", "embed_error"), answer.get("message", "the embedding failed")
            )
        parts.append(unpack(answer["vectors"], dimensions))
        done += len(batch)
        if progress:
            progress(done, len(texts))
    return np.concatenate(parts) if parts else np.zeros((0, dimensions), dtype=np.float32)
