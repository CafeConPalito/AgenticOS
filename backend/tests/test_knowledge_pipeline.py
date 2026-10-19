"""Knowledge library (phase 14, block 2): the queue and the pipeline that processes documents."""

import shutil
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.models import KnowledgeDoc
from agentic_os.services.knowledge.service import KnowledgeService
from agentic_os.services.knowledge.worker import InlineWorker

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
DOCS = "/api/knowledge/docs"


def add_file(client: TestClient, path: Path | str) -> dict:
    response = client.post(f"{DOCS}/files", json={"scope": "general", "paths": [str(path)]})
    assert response.status_code == 201, response.text
    item = response.json()[0]
    assert item["doc"], item
    return item["doc"]


def get(client: TestClient, doc_id: str) -> dict:
    return client.get(f"{DOCS}/{doc_id}").json()


def service(client: TestClient) -> KnowledgeService:
    return client.app.state.knowledge


def run(client: TestClient) -> int:
    return service(client).run_pending()


@pytest.fixture
def web() -> Iterator[dict]:
    """A tiny web server: `pages[path] = (status, content type, body)`."""
    pages: dict[str, tuple[int, str, bytes]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, content_type, body = pages.get(self.path, (404, "text/plain", b"no"))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pages["base"] = (0, "", f"http://127.0.0.1:{server.server_port}".encode())
    try:
        yield pages
    finally:
        server.shutdown()


def url_of(web: dict, path: str) -> str:
    return web["base"][2].decode() + path


# ---------------------------------------------------------------------------- success
def test_a_queued_document_is_converted_and_ready(client: TestClient, tmp_path: Path):
    path = tmp_path / "notas.md"
    path.write_text("# Reunión\n\nHablamos de la baja del servicio.", encoding="utf-8")
    doc = add_file(client, path)
    assert doc["status"] == "queued"

    assert run(client) == 1
    done = get(client, doc["id"])
    assert (done["status"], done["presence"], done["error_code"]) == ("ready", "ok", None)
    assert done["has_markdown"] is True and done["md_tokens"] > 0
    assert done["processed_at"] is not None
    markdown = client.get(f"{DOCS}/{doc['id']}/markdown").json()
    assert markdown["markdown"].startswith("# Reunión")
    # The fingerprint of what was converted: a later change is detected from it.
    path.write_text("# Otro contenido", encoding="utf-8")
    assert get(client, doc["id"])["presence"] == "changed"


@pytest.mark.parametrize(
    "name",
    [
        "manual.pdf",
        "manual_escaneado.pdf",
        "informe.docx",
        "ventas.xlsx",
        "presentacion.pptx",
        "captura_error.png",
        "pagina.html",
        "notas.md",
        "ejemplo.py",
    ],
)
def test_every_format_goes_through_the_same_pipeline(client: TestClient, tmp_path: Path, name: str):
    copy = tmp_path / name
    shutil.copy(FIXTURES / name, copy)
    doc = add_file(client, copy)
    run(client)
    done = get(client, doc["id"])
    assert (done["status"], done["error_code"]) == ("ready", None), done
    assert done["has_markdown"] is True
    assert "base64" not in client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"]


def test_documents_are_processed_oldest_first_and_only_once(client: TestClient, tmp_path: Path):
    ids = []
    for name in ("uno.md", "dos.md", "tres.md"):
        (tmp_path / name).write_text(f"# {name}", encoding="utf-8")
        ids.append(add_file(client, tmp_path / name)["id"])
    order = []
    original = service(client).claim_next

    def spy():
        found = original()
        if found:
            order.append(found)
        return found

    service(client).claim_next = spy
    assert run(client) == 3
    assert order == ids
    assert run(client) == 0  # nothing left to do


def test_two_claims_never_take_the_same_document(client: TestClient, tmp_path: Path):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    add_file(client, tmp_path / "a.md")
    first, second = service(client).claim_next(), service(client).claim_next()
    assert first is not None and second is None
    assert get(client, first)["status"] == "converting"


# ---------------------------------------------------------------------------- progress
def test_the_events_tell_the_states_and_the_progress(client: TestClient, tmp_path: Path):
    shutil.copy(FIXTURES / "manual.pdf", tmp_path / "manual.pdf")
    doc = add_file(client, tmp_path / "manual.pdf")
    seen = []
    service(client).events.publish = seen.append
    run(client)
    docs = [e["doc"] for e in seen if e["type"] == "doc" and e["doc"]["id"] == doc["id"]]
    assert docs[0]["status"] == "converting"
    assert docs[-1]["status"] == "ready"
    progress = [(d["progress_done"], d["progress_total"]) for d in docs]
    assert (5, 5) in progress  # the last page is always reported
    assert [e["type"] for e in seen if e["type"] == "queue"]  # and the queue moved


def test_events_reach_a_websocket_client(client: TestClient, tmp_path: Path):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    doc = add_file(client, tmp_path / "a.md")
    with client.websocket_connect("/api/knowledge/events") as socket:
        run(client)
        statuses = []
        while "ready" not in statuses:
            event = socket.receive_json()
            if event["type"] == "doc" and event["doc"]["id"] == doc["id"]:
                statuses.append(event["doc"]["status"])
    assert statuses[0] == "converting" and statuses[-1] == "ready"


# ---------------------------------------------------------------------------- failures
def test_a_failure_is_marked_with_its_reason(client: TestClient, tmp_path: Path):
    (tmp_path / "vacio.md").write_text("   ", encoding="utf-8")
    (tmp_path / "roto.docx").write_bytes(b"no soy un docx" * 100)
    empty = add_file(client, tmp_path / "vacio.md")
    broken = add_file(client, tmp_path / "roto.docx")
    run(client)
    assert (get(client, empty["id"])["status"], get(client, empty["id"])["error_code"]) == (
        "failed",
        "empty",
    )
    assert get(client, broken["id"])["error_code"] == "convert_error"
    assert get(client, broken["id"])["error_message"]


def test_a_file_that_disappears_before_its_turn_is_not_found(client: TestClient, tmp_path: Path):
    path = tmp_path / "se-va.md"
    path.write_text("# adiós", encoding="utf-8")
    doc = add_file(client, path)
    path.unlink()
    run(client)
    done = get(client, doc["id"])
    assert (done["status"], done["error_code"], done["presence"]) == (
        "failed",
        "not_found",
        "missing",
    )


def test_a_failed_document_is_not_processed_again_until_asked(client: TestClient, tmp_path: Path):
    (tmp_path / "vacio.md").write_text("", encoding="utf-8")
    doc = add_file(client, tmp_path / "vacio.md")
    assert run(client) == 1
    assert run(client) == 0
    (tmp_path / "vacio.md").write_text("# ya tiene texto", encoding="utf-8")
    response = client.post(f"{DOCS}/{doc['id']}/reprocess")
    assert response.status_code == 200 and response.json()["status"] == "queued"
    assert run(client) == 1
    assert get(client, doc["id"])["status"] == "ready"


def test_a_failed_reprocess_keeps_the_previous_markdown(client: TestClient, tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text("# Versión buena", encoding="utf-8")
    doc = add_file(client, path)
    run(client)
    path.write_text("", encoding="utf-8")
    client.post(f"{DOCS}/{doc['id']}/reprocess")
    run(client)
    failed = get(client, doc["id"])
    assert (failed["status"], failed["error_code"]) == ("failed", "empty")
    # Not used by the agents (it is not ready) but still there to look at.
    assert client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"] == "# Versión buena"


def test_an_unsupported_format_stays_failed_after_reprocessing(client: TestClient, tmp_path: Path):
    (tmp_path / "programa.exe").write_bytes(b"MZ")
    doc = add_file(client, tmp_path / "programa.exe")
    assert doc["status"] == "failed"
    client.post(f"{DOCS}/{doc['id']}/reprocess")
    run(client)
    assert get(client, doc["id"])["error_code"] == "unsupported"


def test_a_file_grown_past_the_limit_is_refused_when_processed(client: TestClient, tmp_path: Path):
    path = tmp_path / "crece.md"
    path.write_text("# pequeño", encoding="utf-8")
    doc = add_file(client, path)
    with client.app.state.sessionmaker() as db:
        from agentic_os.services.knowledge import config

        config.save(db, {"max_file_mb": 1})
        db.commit()
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    run(client)
    assert get(client, doc["id"])["error_code"] == "too_large"


# ---------------------------------------------------------------------------- reprocess
def test_a_changed_original_is_processed_again_on_request(client: TestClient, tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text("# Antes", encoding="utf-8")
    doc = add_file(client, path)
    run(client)
    path.write_text("# Después", encoding="utf-8")
    assert get(client, doc["id"])["presence"] == "changed"
    assert client.post(f"{DOCS}/{doc['id']}/reprocess").status_code == 200
    run(client)
    done = get(client, doc["id"])
    assert (done["status"], done["presence"]) == ("ready", "ok")
    assert client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"] == "# Después"


def test_a_document_being_processed_cannot_be_queued_again(client: TestClient, tmp_path: Path):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    doc = add_file(client, tmp_path / "a.md")
    service(client).claim_next()  # now «converting»
    response = client.post(f"{DOCS}/{doc['id']}/reprocess")
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "processing")


def test_relocating_to_other_content_queues_it_again(client: TestClient, tmp_path: Path):
    first, second = tmp_path / "uno.md", tmp_path / "dos.md"
    first.write_text("# Uno", encoding="utf-8")
    second.write_text("# Dos", encoding="utf-8")
    doc = add_file(client, first)
    run(client)
    response = client.post(
        f"{DOCS}/{doc['id']}/relocate", json={"path": str(second), "confirm": True}
    )
    assert response.json()["reprocess"] is True
    run(client)
    assert client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"] == "# Dos"


# --------------------------------------------------------------------------- the queue
def test_pausing_stops_new_documents_and_resuming_continues(client: TestClient, tmp_path: Path):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    doc = add_file(client, tmp_path / "a.md")
    assert client.get("/api/knowledge/queue").json() == {
        "paused": False,
        "queued": 1,
        "active": [],
        "mode": "off",
    }
    assert client.post("/api/knowledge/queue/pause").json()["paused"] is True
    assert run(client) == 0
    assert get(client, doc["id"])["status"] == "queued"
    assert client.post("/api/knowledge/queue/resume").json()["paused"] is False
    assert run(client) == 1
    assert client.get("/api/knowledge/queue").json()["queued"] == 0


def test_what_a_closed_app_left_half_done_goes_back_to_the_queue(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    doc = add_file(client, tmp_path / "a.md")
    with client.app.state.sessionmaker() as db:
        row = db.get(KnowledgeDoc, doc["id"])
        row.status, row.progress_done, row.progress_total = "indexing", 3, 9
        db.commit()
    service(client).recover()
    back = get(client, doc["id"])
    assert (back["status"], back["progress_done"], back["progress_total"]) == ("queued", 0, 0)


def test_a_document_deleted_while_it_is_processed_leaves_no_trace(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "a.md").write_text("# a", encoding="utf-8")
    doc = add_file(client, tmp_path / "a.md")

    class DeletingWorker(InlineWorker):
        def request(self, request, on_event=None):
            assert client.delete(f"{DOCS}/{doc['id']}").status_code == 204
            return super().request(request, on_event)

    assert service(client).run_pending(DeletingWorker()) == 1
    assert client.get(f"{DOCS}/{doc['id']}").status_code == 404
    work = Path(client.app.state.settings.data_dir) / "knowledge" / "work"
    assert not work.exists() or not any(work.iterdir())  # the work folder is cleaned


def test_the_threads_process_documents_by_themselves(settings, tmp_path: Path):
    from agentic_os.app import create_app

    live = settings.model_copy(update={"knowledge_processing": "inline"})
    (tmp_path / "a.md").write_text("# solo", encoding="utf-8")
    with TestClient(create_app(live)) as client:
        doc = add_file(client, tmp_path / "a.md")
        import time

        deadline = time.monotonic() + 15
        while get(client, doc["id"])["status"] != "ready" and time.monotonic() < deadline:
            time.sleep(0.2)
        assert get(client, doc["id"])["status"] == "ready"


# ------------------------------------------------------------------------------ web pages
def test_a_web_page_is_downloaded_and_converted(client: TestClient, web: dict):
    html = (FIXTURES / "pagina.html").read_bytes()
    web["/ayuda"] = (200, "text/html; charset=utf-8", html)
    url = url_of(web, "/ayuda")
    doc = client.post(f"{DOCS}/url", json={"scope": "general", "url": url}).json()
    assert doc["title"].endswith("/ayuda")
    run(client)
    done = get(client, doc["id"])
    assert (done["status"], done["presence"]) == ("ready", "ok")
    assert done["title"] == "Centro de ayuda"  # the page's own title replaces the address
    markdown = client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"]
    assert "Usuarios y permisos" in markdown and "Inicio | Precios" not in markdown


def test_a_title_the_user_chose_is_kept(client: TestClient, web: dict):
    web["/p"] = (200, "text/html", (FIXTURES / "pagina.html").read_bytes())
    doc = client.post(f"{DOCS}/url", json={"scope": "general", "url": url_of(web, "/p")}).json()
    client.patch(f"{DOCS}/{doc['id']}", json={"title": "Mi guía"})
    run(client)
    assert get(client, doc["id"])["title"] == "Mi guía"


def test_a_url_can_point_to_a_pdf(client: TestClient, web: dict):
    web["/manual"] = (200, "application/pdf", (FIXTURES / "manual.pdf").read_bytes())
    doc = client.post(
        f"{DOCS}/url", json={"scope": "general", "url": url_of(web, "/manual")}
    ).json()
    run(client)
    assert get(client, doc["id"])["status"] == "ready"
    assert "<!-- page: 5 -->" in client.get(f"{DOCS}/{doc['id']}/markdown").json()["markdown"]


@pytest.mark.parametrize(
    ("page", "code", "message"),
    [
        ((404, "text/html", b"no"), "url_error", "HTTP 404"),
        ((500, "text/html", b"no"), "url_error", "HTTP 500"),
        ((200, "image/svg+xml", b"<svg/>"), "unsupported", "image/svg+xml"),
        ((200, "text/html", b"x" * (1024 * 1024 + 1)), "too_large", ""),
    ],
)
def test_a_web_page_that_cannot_be_used_says_why(
    client: TestClient, web: dict, page: tuple, code: str, message: str
):
    web["/x"] = page
    with client.app.state.sessionmaker() as db:
        from agentic_os.services.knowledge import config

        config.save(db, {"max_file_mb": 1})
        db.commit()
    doc = client.post(f"{DOCS}/url", json={"scope": "general", "url": url_of(web, "/x")}).json()
    run(client)
    done = get(client, doc["id"])
    assert (done["status"], done["error_code"]) == ("failed", code)
    assert message in done["error_message"]


def test_an_unreachable_server_is_a_url_error(client: TestClient):
    created = client.post(
        f"{DOCS}/url", json={"scope": "general", "url": "http://127.0.0.1:1/nada"}
    ).json()
    run(client)
    done = get(client, created["id"])
    assert (done["status"], done["error_code"]) == ("failed", "url_error")
