"""Does the search find the right passage? (phase 14, block 5) The experiment of spike S4 through
the whole product: real documents, the real `multilingual-e5-small`, the real pipeline and API.

30 questions about a fictional manual (half asked with other words, half with an identifier) among
127 passages, 97 of them near-duplicates with other codes. The model is downloaded once into a
cache folder in the system's temp (135 MB) and the test skips without network."""

import json
import random
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.knowledge.worker import InlineWorker
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.stage import stage

CACHE = Path(tempfile.gettempdir()) / "agentic-os-test-models"
FACTS = json.loads(
    (Path(__file__).parent / "fixtures" / "knowledge" / "facts.json").read_text("utf-8")
)

REASONS = [
    "el NIF del cliente no supera la validación", "la serie de numeración está bloqueada",
    "falta el domicilio fiscal", "el importe no coincide con el desglose",
    "la fecha de la factura es anterior al cierre", "el cliente está dado de baja",
    "el certificado de firma ha caducado", "el tipo de IVA no es válido para el país",
    "el formato del fichero no es correcto",
]  # fmt: skip
ACTIONS = [
    "que no tiene espacios ni guiones", "que los datos del cliente están completos",
    "la configuración en Ajustes", "que el periodo no está cerrado",
    "que el certificado está vigente", "el formato indicado en la documentación",
]  # fmt: skip


def distractors() -> list[tuple[str, str]]:
    """97 passages that look like the codes, endpoints, events and variables of the manual."""
    rng = random.Random(7)
    found: list[tuple[str, str]] = []
    for n in rng.sample(range(4000, 6000), 45):
        found.append((
            f"Error ERR_{n}",
            f"El código ERR_{n} aparece cuando {rng.choice(REASONS)}. Compruebe "
            f"{rng.choice(ACTIONS)}. Si el problema continúa, contacte con soporte.",
        ))  # fmt: skip
    for resource in ["customers", "payments", "taxes", "series", "reports", "products",
                     "contacts", "refunds", "templates", "users"]:  # fmt: skip
        for verb in ("GET", "PUT", "DELETE"):
            found.append((
                f"API: endpoint /v2/{resource}",
                f"El endpoint {verb} /v2/{resource} gestiona los recursos de tipo {resource}. "
                "Requiere la cabecera Authorization con un token Bearer.",
            ))  # fmt: skip
    for event in ["invoice.created", "invoice.sent", "invoice.overdue", "customer.created",
                  "payment.failed", "payment.refunded", "series.closed"]:  # fmt: skip
        found.append((
            f"Webhook: evento {event}",
            f"El evento {event} se envía cuando se produce el cambio correspondiente.",
        ))  # fmt: skip
    for name in ["AURORA_HOME", "AURORA_LOG", "AURORA_DEBUG", "AURORA_TIMEOUT", "AURORA_CACHE",
                 "AURORA_LANG", "AURORA_TOKEN", "AURORA_PORT"]:  # fmt: skip
        found.append((
            f"Variable de entorno {name}",
            f"La variable {name} permite ajustar el comportamiento de la versión de escritorio.",
        ))  # fmt: skip
    for template in ["PLT-FACTURA-EN", "PLT-FACTURA-FR", "PLT-PRESUPUESTO-ES", "PLT-ALBARAN-ES",
                     "PLT-RECIBO-ES", "PLT-ABONO-ES", "PLT-PROFORMA-ES"]:  # fmt: skip
        found.append((
            f"Plantilla {template}",
            f"La plantilla {template} es una de las plantillas incluidas con el programa.",
        ))  # fmt: skip
    return found


@pytest.fixture(scope="module")
def e5_files() -> Path:
    entry = catalog.entry("e5-small")
    if not stage(CACHE, [entry], log=lambda _: None):
        pytest.skip("the embedding model cannot be downloaded (no network?)")
    return store.downloaded_folder(CACHE, entry)


@pytest.fixture
def library(client: TestClient, tmp_path: Path, e5_files: Path) -> list[dict]:
    """The 127 passages indexed with the real model."""
    entry = catalog.entry("e5-small")
    data_dir = Path(client.app.state.settings.data_dir)
    target = store.downloaded_folder(data_dir, entry)
    shutil.copytree(e5_files, target, dirs_exist_ok=True)
    assert store.is_installed(data_dir, entry)
    with client.app.state.sessionmaker() as db:
        assert selection.chosen(db)["embedding"] == "e5-small"
    folder = tmp_path / "manual"
    folder.mkdir()
    passages = [(f["title"], f["body"]) for f in FACTS] + distractors()
    paths = []
    for number, (title, body) in enumerate(passages):
        path = folder / f"{number:03d}.md"
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        paths.append(str(path))
    client.post("/api/knowledge/docs/files", json={"scope": "general", "paths": paths})
    client.app.state.knowledge.run_pending(InlineWorker())
    return FACTS


def ranks(client: TestClient, facts: list[dict]) -> list[tuple[dict, int | None]]:
    """For each question, the position (0-based) of its right passage in the answer."""
    result = []
    for number, fact in enumerate(facts):
        answer = client.post("/api/knowledge/search", json={"query": fact["q"], "limit": 8}).json()
        assert answer["mode"] == "hybrid" and answer["model"] == "e5-small"
        wanted = f"{number:03d}.md"
        position = next((i for i, h in enumerate(answer["hits"]) if h["title"] == wanted), None)
        result.append((fact, position))
    return result


def rate(found: list[tuple[dict, int | None]], kind: str | None, top: int) -> float:
    chosen = [p for fact, p in found if kind is None or fact["kind"] == kind]
    return sum(1 for p in chosen if p is not None and p < top) / len(chosen)


def test_the_right_passage_is_found_among_near_duplicates(client: TestClient, library):
    assert client.get("/api/knowledge/queue").json()["queued"] == 0
    found = ranks(client, library)
    report = {
        "top5 all": rate(found, None, 5),
        "top5 paraphrase": rate(found, "paraphrase", 5),
        "top1 exact": rate(found, "exact", 1),
        "top1 all": rate(found, None, 1),
    }
    print("quality:", {k: round(v, 2) for k, v in report.items()})
    # Spike S4 (127 passages, e5-small, identifier-gated hybrid): 0.90 / 0.80 top-5 / 1.00 / 0.80.
    assert report["top5 all"] >= 0.85, report
    assert report["top5 paraphrase"] >= 0.75, report
    assert report["top1 exact"] >= 0.90, report
    assert report["top1 all"] >= 0.65, report


def test_an_identifier_is_found_by_its_words_even_among_look_alikes(client: TestClient, library):
    for code in ("ERR_4012", "ERR_5103"):
        hits = client.post("/api/knowledge/search", json={"query": code}).json()["hits"]
        assert code in hits[0]["text"], (code, [h["title"] for h in hits[:3]])
        assert hits[0]["found_by"] in ("words", "both")
