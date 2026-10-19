"""Helpers for the knowledge tests that need an embedding model without running one: a fake
model whose vectors capture a few synonyms, installed in the data folder like a real download."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import zlib
from pathlib import Path

import numpy as np
import pytest

from agentic_os.services.knowledge import embeddings
from agentic_os.services.knowledge.worker import InlineWorker
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.catalog import CatalogEntry, RemoteFile

DIMENSIONS = 64
# Words of a group «mean» the same: the fake model puts them in the same place.
GROUPS = [
    {"cancelar", "baja", "dejar", "desuscribir", "suscripcion", "pagar", "cobro"},
    {"respaldo", "copia", "seguridad", "backup", "restaurar"},
    {"contrasena", "clave", "password", "acceso", "entrar"},
    {"factura", "facturas", "rectificativa", "rectificativas", "corregir", "equivoque", "error"},
]
STOP = {
    "de",
    "la",
    "el",
    "los",
    "las",
    "un",
    "una",
    "y",
    "o",
    "en",
    "a",
    "que",
    "como",
    "me",
    "mi",
    "se",
}


def _plain(word: str) -> str:
    folded = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in folded if unicodedata.category(c) != "Mn")


def _bucket(word: str) -> int:
    for number, group in enumerate(GROUPS):
        if word in group:
            return number
    return len(GROUPS) + zlib.crc32(word.encode()) % (DIMENSIONS - len(GROUPS))


def fake_vectors(texts: list[str], kind: str = "passage") -> np.ndarray:
    """Bag of buckets: a word counts in its synonym group's slot, anything else in a hashed one.
    L2-normalized like the real models, deterministic across processes."""
    out = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in re.findall(r"\w+", text):
            word = _plain(word)
            if word and word not in STOP:
                out[row, _bucket(word)] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(norms, 1e-12)


class FakeEmbedWorker(InlineWorker):
    """Answers `embed` with the fake model; every other operation is the real one."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.asked: list[dict] = []

    def request(self, request: dict, on_event=None) -> dict:
        if request.get("op") != "embed":
            return super().request(request, on_event)
        self.asked.append(request)
        if self.fail:
            return {
                "ok": False,
                "code": "embed_error",
                "message": "the model is broken",
                "id": request.get("id"),
            }
        vectors = fake_vectors(request["texts"], request["kind"])
        return {
            "ok": True,
            "id": request.get("id"),
            "vectors": embeddings.pack(vectors),
            "count": len(vectors),
        }


def install_fake_model(
    client, monkeypatch: pytest.MonkeyPatch, model_id: str = "fake-emb", choose: bool = True
) -> CatalogEntry:
    """A model of embeddings «downloaded» into the data folder and chosen for the search."""
    files = {"model.onnx": b"model " + model_id.encode(), "tokenizer.json": b"{}"}
    entry = CatalogEntry(
        model_id,
        catalog.EMBEDDING,
        "Fake",
        "mit",
        tuple(
            RemoteFile(name, len(data), hashlib.sha256(data).hexdigest(), ())
            for name, data in files.items()
        ),
        usage={
            "model": "model.onnx",
            "tokenizer": "tokenizer.json",
            "dimensions": DIMENSIONS,
            "max_length": 512,
            "query_prefix": "",
            "document_prefix": "",
            "pooling": "mean",
        },
    )
    monkeypatch.setattr(catalog, "CATALOG", (*catalog.CATALOG, entry))
    monkeypatch.setattr(catalog, "BY_ID", {**catalog.BY_ID, entry.id: entry})
    data_dir = Path(client.app.state.settings.data_dir)
    folder = store.downloaded_folder(data_dir, entry)
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    store.write_manifest(data_dir, entry)
    # The questions are embedded by the service's own worker: here, the fake one.
    service = client.app.state.knowledge
    service._factory = FakeEmbedWorker
    service._query_worker = None
    if choose:
        with client.app.state.sessionmaker() as db:
            selection.choose(db, catalog.EMBEDDING, model_id)
            db.commit()
    return entry
