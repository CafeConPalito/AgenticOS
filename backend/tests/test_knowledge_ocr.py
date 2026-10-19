"""The real OCR (phase 14, block 4): RapidOCR with the pinned models, reading Spanish.

The models are the ones the installer carries; the first run downloads them once into a cache
folder in the system's temp (a few seconds, ~18 MB) and the tests skip if there is no network."""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.knowledge import ocr
from agentic_os.services.knowledge.worker import InlineWorker, ProcessWorker
from agentic_os.services.localmodels import catalog, store
from agentic_os.services.localmodels.stage import stage

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
CACHE = Path(tempfile.gettempdir()) / "agentic-os-test-ocr"


@pytest.fixture(scope="session")
def models() -> dict[str, str]:
    entry = catalog.entry("ocr-latin")
    if not stage(CACHE, [entry], log=lambda _: None):
        pytest.skip("the OCR models cannot be downloaded (no network?)")
    folder = store.downloaded_folder(CACHE, entry)
    return {
        key: str(folder / entry.usage[name])
        for key, name in (("det", "detector"), ("cls", "classifier"), ("rec", "recognizer"))
    }


@pytest.fixture
def bundled(models: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The app «carries» the models, as the installer does."""
    root = CACHE / "bundle"
    folder = root / "ocr-latin"
    folder.mkdir(parents=True, exist_ok=True)
    for path in models.values():
        target = folder / Path(path).name
        if not target.exists():
            shutil.copyfile(path, target)
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(root))


def test_it_reads_spanish_with_accents_and_codes(models: dict[str, str]):
    engine = ocr.engine(models, threads=2)
    text = ocr.read(engine, FIXTURES / "captura_error.png")
    assert "ERR_4012" in text and "NIF" in text
    assert "válido" in text and "inténtelo" in text  # accents survive


def test_it_reads_a_whole_batch_and_reports_progress(models: dict[str, str]):
    from PIL import Image

    work = CACHE / "batch"
    work.mkdir(exist_ok=True)
    Image.new("RGB", (400, 100), "white").save(work / "blank.png")  # nothing to read
    shutil.copy(FIXTURES / "captura_error.png", work / "captura.png")
    steps = []
    texts, failed = ocr.read_all(
        work,
        {0: "captura.png", 1: "blank.png", 2: "missing.png"},
        models,
        threads=2,
        progress=lambda done, total: steps.append((done, total)),
    )
    assert "ERR_4012" in texts[0] and texts[1] == ""
    assert texts[2] == "" and failed == 1  # a picture that cannot be opened is not fatal
    assert steps == [(1, 3), (2, 3), (3, 3)]


def test_a_scanned_pdf_is_read_through_the_whole_pipeline(
    client: TestClient, tmp_path: Path, bundled
):
    copy = tmp_path / "escaneado.pdf"
    shutil.copy(FIXTURES / "manual_escaneado.pdf", copy)
    record = client.post(
        "/api/knowledge/docs/files", json={"scope": "general", "paths": [str(copy)]}
    ).json()[0]["doc"]
    client.app.state.knowledge.run_pending(InlineWorker())
    done = client.get(f"/api/knowledge/docs/{record['id']}").json()
    assert (done["status"], done["notice"], done["image_count"]) == ("ready", None, 0)
    text = client.get(f"/api/knowledge/docs/{record['id']}/markdown").json()["markdown"]
    # The three scanned pages came out as text (the 2nd and 3rd carry codes).
    assert text.count("<!-- page: ") == 3
    assert "ERR_4012" in text and "ERR_5103" in text and "BIENVENIDA25" in text
    assert "kimg" not in text


def test_the_picture_of_a_word_document_gets_its_text(client: TestClient, tmp_path: Path, bundled):
    copy = tmp_path / "informe.docx"
    shutil.copy(FIXTURES / "informe.docx", copy)
    record = client.post(
        "/api/knowledge/docs/files", json={"scope": "general", "paths": [str(copy)]}
    ).json()[0]["doc"]
    client.app.state.knowledge.run_pending(InlineWorker())
    text = client.get(f"/api/knowledge/docs/{record['id']}/markdown").json()["markdown"]
    assert "![](kimg:0)\n\n> Texto de la imagen:" in text
    assert "Emitida" in text and "Cobrada" in text  # the diagram's words


def test_the_worker_process_reads_pictures_too(models: dict[str, str]):
    worker = ProcessWorker(idle_seconds=5)
    events = []
    try:
        answer = worker.request(
            {
                "op": "ocr",
                "folder": str(FIXTURES),
                "files": {"0": "captura_error.png"},
                "models": models,
                "threads": 2,
            },
            events.append,
        )
    finally:
        worker.close()
    assert answer["ok"] is True and answer["failed"] == 0
    assert "válido" in answer["texts"]["0"]  # accents cross the pipe intact
    assert events[-1]["done"] == events[-1]["total"] == 1
