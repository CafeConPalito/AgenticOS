"""Knowledge library (phase 14, block 4): pictures found in documents, kept or dropped, and the
text the OCR read from them (a fake OCR here; the real one is in test_knowledge_ocr.py)."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.knowledge.images import compose, quoted
from agentic_os.services.knowledge.worker import InlineWorker
from agentic_os.services.localmodels import catalog

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
DOCS = "/api/knowledge/docs"


class FakeOcr(InlineWorker):
    """Answers the `ocr` operation with canned text per picture number; the rest is real."""

    def __init__(self, texts: dict[int, str] | None = None, answer: dict | None = None) -> None:
        self.texts = texts or {}
        self.answer = answer
        self.asked: list[dict] = []

    def request(self, request: dict, on_event=None) -> dict:
        if request.get("op") != "ocr":
            return super().request(request, on_event)
        self.asked.append(request)
        numbers = [int(n) for n in request["files"]]
        for done in range(1, len(numbers) + 1):
            if on_event:
                on_event(
                    {
                        "id": request.get("id"),
                        "event": "progress",
                        "done": done,
                        "total": len(numbers),
                    }
                )
        if self.answer is not None:
            return {**self.answer, "id": request.get("id")}
        return {
            "ok": True,
            "id": request.get("id"),
            "texts": {str(n): self.texts.get(n, "") for n in numbers},
            "failed": 0,
        }


@pytest.fixture
def ocr_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The OCR model is «installed» (files of the right size under the bundle folder)."""
    entry = catalog.entry("ocr-latin")
    bundle = tmp_path / "bundle"
    for f in entry.files:
        (bundle / entry.id).mkdir(parents=True, exist_ok=True)
        (bundle / entry.id / f.name).write_bytes(b"\0" * f.size)
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(bundle))


def add(client: TestClient, tmp_path: Path, name: str, as_name: str | None = None) -> dict:
    copy = tmp_path / "docs" / (as_name or name)
    copy.parent.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / name, copy)
    response = client.post(f"{DOCS}/files", json={"scope": "general", "paths": [str(copy)]})
    return response.json()[0]["doc"]


def process(client: TestClient, worker=None) -> None:
    client.app.state.knowledge.run_pending(worker)


def doc(client: TestClient, doc_id: str) -> dict:
    return client.get(f"{DOCS}/{doc_id}").json()


def markdown(client: TestClient, doc_id: str) -> str:
    return client.get(f"{DOCS}/{doc_id}/markdown").json()["markdown"]


def stored_files(client: TestClient) -> list[str]:
    folder = Path(client.app.state.settings.data_dir) / "knowledge" / "images"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


# ----------------------------------------------------------------------- composing text
def test_a_quote_has_the_text_line_by_line():
    assert quoted("") == "" and quoted("  \n ") == ""
    assert quoted("Hola\n\n  mundo  ") == "\n\n> Texto de la imagen: Hola\n> mundo"


def test_compose_puts_the_text_under_pictures_and_in_place_of_scanned_pages():
    images = [
        {"n": 0, "kind": "embedded"},
        {"n": 1, "kind": "page"},
        {"n": 2, "kind": "page"},
        {"n": 3, "kind": "file"},
    ]
    source = (
        "Antes ![Gráfico](kimg:0) y otra vez ![Gráfico](kimg:0)\n\n"
        "<!-- page: 1 -->\n\n![Página 1](kimg:1)\n\n"
        "<!-- page: 2 -->\n\n![Página 2](kimg:2)\n\n![x](kimg:9)\n\n![f](kimg:3)"
    )
    texts = {0: "Ventas 2024", 1: "Texto de la página uno", 2: "", 3: "Captura"}
    out, kept = compose(source, images, texts)
    assert out.count("> Texto de la imagen: Ventas 2024") == 1  # the same picture, said once
    assert "![Página 1]" not in out and "Texto de la página uno" in out  # the page is its text
    assert "![Página 2](kimg:2)" in out  # nobody could read it: it stays as a picture
    assert "kimg:9" not in out  # a reference to nothing disappears
    assert "![f](kimg:3)\n\n> Texto de la imagen: Captura" in out
    assert [i["n"] for i in kept] == [0, 2, 3]  # the read page is not kept


# ---------------------------------------------------------------------- the pictures
def test_a_documents_picture_is_kept_and_its_text_goes_below_it(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "informe.docx")
    ocr = FakeOcr({0: "Flujo de cobro\nEmitida Enviada Cobrada"})
    process(client, ocr)
    done = doc(client, record["id"])
    assert (done["status"], done["image_count"], done["notice"]) == ("ready", 1, None)
    text = markdown(client, record["id"])
    assert "![](kimg:0)\n\n> Texto de la imagen: Flujo de cobro\n> Emitida Enviada Cobrada" in text
    assert "base64" not in text

    images = client.get(f"{DOCS}/{record['id']}/images").json()
    assert [(i["ord"], i["kind"], i["width"], i["height"]) for i in images] == [
        (0, "embedded", 900, 126)
    ]
    assert images[0]["ocr_text"].startswith("Flujo de cobro")
    served = client.get(f"{DOCS}/{record['id']}/images/0")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(stored_files(client)) == 1 and stored_files(client)[0].endswith(".png")
    assert client.get(f"{DOCS}/{record['id']}/images/5").status_code == 404
    # The worker was asked for exactly that picture, with the model files and the thread limit.
    asked = ocr.asked[0]
    assert list(asked["files"]) == ["0"] and set(asked["models"]) == {"det", "cls", "rec"}


def test_the_progress_of_reading_pictures_is_shown(client: TestClient, tmp_path: Path, ocr_ready):
    record = add(client, tmp_path, "manual_escaneado.pdf")
    seen = []
    client.app.state.knowledge.events.publish = seen.append
    process(client, FakeOcr({0: "a", 1: "b", 2: "c"}))
    states = [
        (e["doc"]["status"], e["doc"]["progress_done"], e["doc"]["progress_total"])
        for e in seen
        if e["type"] == "doc" and e["doc"]["id"] == record["id"]
    ]
    assert ("images", 0, 3) in states and ("images", 3, 3) in states
    assert states[-1][0] == "ready"


def test_a_scanned_pdf_becomes_its_text_and_keeps_no_pictures(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "manual_escaneado.pdf")
    process(client, FakeOcr({0: "Error ERR_4012", 1: "Error ERR_5103", 2: "BIENVENIDA25"}))
    text = markdown(client, record["id"])
    assert "<!-- page: 2 -->\n\nError ERR_5103" in text
    assert "kimg" not in text
    assert doc(client, record["id"])["image_count"] == 0
    assert client.get(f"{DOCS}/{record['id']}/images").json() == []
    assert stored_files(client) == []  # the page renders were only for reading


def test_a_scanned_page_nobody_can_read_stays_a_picture(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "manual_escaneado.pdf")
    process(client, FakeOcr({0: "Primera", 1: "", 2: "Tercera"}))
    text = markdown(client, record["id"])
    assert "Primera" in text and "Tercera" in text
    assert "![Página 2](kimg:1)" in text
    assert [(i["ord"], i["kind"]) for i in client.get(f"{DOCS}/{record['id']}/images").json()] == [
        (1, "page")
    ]
    assert len(stored_files(client)) == 1


def test_a_picture_file_keeps_no_copy_and_is_served_from_its_original(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "captura_error.png")
    process(client, FakeOcr({0: "ERR_4012: el NIF del cliente no es válido"}))
    text = markdown(client, record["id"])
    assert text.startswith("![captura_error.png](kimg:0)\n\n> Texto de la imagen: ERR_4012")
    (image,) = client.get(f"{DOCS}/{record['id']}/images").json()
    assert (image["kind"], image["ocr_text"]) == (
        "file",
        "ERR_4012: el NIF del cliente no es válido",
    )
    assert stored_files(client) == []  # the app copies nothing of what the user added
    assert client.get(f"{DOCS}/{record['id']}/images/0").headers["content-type"] == "image/png"
    # If the user moves the original, the picture is as gone as the document's file.
    Path(record["path"]).unlink()
    assert client.get(f"{DOCS}/{record['id']}/images/0").status_code == 410


# ---------------------------------------------------------------------- when OCR fails
def test_without_the_ocr_model_the_document_is_ready_with_a_notice(
    client: TestClient, tmp_path: Path
):
    record = add(client, tmp_path, "informe.docx")
    scanned = add(client, tmp_path, "manual_escaneado.pdf")
    ocr = FakeOcr({0: "no se usa"})
    process(client, ocr)
    assert ocr.asked == []  # nothing to ask: the model is not there
    for item in (record, scanned):
        done = doc(client, item["id"])
        assert (done["status"], done["notice"]) == ("ready", "ocr_missing")
    assert "Texto de la imagen" not in markdown(client, record["id"])
    # Scanned pages stay as pictures: they are the only way to look at them.
    assert len(client.get(f"{DOCS}/{scanned['id']}/images").json()) == 3


@pytest.mark.parametrize(
    "answer",
    [
        {"ok": False, "code": "convert_error", "message": "model damaged"},
        {"ok": True, "texts": {"0": ""}, "failed": 1},
    ],
)
def test_an_ocr_that_fails_is_a_notice_not_a_failed_document(
    client: TestClient, tmp_path: Path, ocr_ready, answer: dict
):
    record = add(client, tmp_path, "informe.docx")
    process(client, FakeOcr(answer=answer))
    done = doc(client, record["id"])
    assert (done["status"], done["notice"], done["image_count"]) == ("ready", "ocr_failed", 1)


def test_the_notice_goes_away_when_the_document_is_processed_again_with_ocr(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    record = add(client, tmp_path, "informe.docx")
    process(client)
    assert doc(client, record["id"])["notice"] == "ocr_missing"
    entry = catalog.entry("ocr-latin")
    bundle = tmp_path / "bundle"
    for f in entry.files:
        (bundle / entry.id).mkdir(parents=True, exist_ok=True)
        (bundle / entry.id / f.name).write_bytes(b"\0" * f.size)
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(bundle))
    client.post(f"{DOCS}/{record['id']}/reprocess")
    process(client, FakeOcr({0: "Ahora sí"}))
    assert doc(client, record["id"])["notice"] is None
    assert "> Texto de la imagen: Ahora sí" in markdown(client, record["id"])


# ---------------------------------------------------------------- shared and old files
def test_two_documents_with_the_same_picture_share_one_file(
    client: TestClient, tmp_path: Path, ocr_ready
):
    first = add(client, tmp_path, "informe.docx", "uno.docx")
    second = add(client, tmp_path, "informe.docx", "dos.docx")
    process(client, FakeOcr({0: "x"}))
    assert len(stored_files(client)) == 1
    client.delete(f"{DOCS}/{first['id']}")
    assert len(stored_files(client)) == 1  # the other one still shows it
    assert client.get(f"{DOCS}/{second['id']}/images/0").status_code == 200
    client.delete(f"{DOCS}/{second['id']}")
    assert stored_files(client) == []


def test_reprocessing_replaces_the_pictures_and_removes_the_old_files(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "informe.docx")
    process(client, FakeOcr({0: "primera vez"}))
    (before,) = stored_files(client)
    # The document changes: the same text, a different picture.
    other = tmp_path / "docs" / "informe.docx"
    shutil.copy(FIXTURES / "presentacion.pptx", other.with_suffix(".pptx"))
    client.patch(f"{DOCS}/{record['id']}", json={"title": "mismo documento"})
    client.post(
        f"{DOCS}/{record['id']}/relocate",
        json={"path": str(other.with_suffix(".pptx")), "confirm": True},
    )
    process(client, FakeOcr({0: "segunda vez"}))
    after = stored_files(client)
    assert len(after) == 1 and after != [before]  # the old file is gone
    assert "segunda vez" in markdown(client, record["id"])
    assert "primera vez" not in markdown(client, record["id"])
    assert [i["location"] for i in client.get(f"{DOCS}/{record['id']}/images").json()] == [
        "diapositiva 2"
    ]


def test_deleting_a_document_removes_its_picture_rows_and_files(
    client: TestClient, tmp_path: Path, ocr_ready
):
    record = add(client, tmp_path, "informe.docx")
    process(client, FakeOcr({0: "x"}))
    assert stored_files(client)
    client.delete(f"{DOCS}/{record['id']}")
    assert stored_files(client) == []
    assert client.get(f"{DOCS}/{record['id']}/images").status_code == 404
