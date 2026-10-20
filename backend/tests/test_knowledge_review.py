"""Regressions found by the phase 14 code review."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_helpers import FakeEmbedWorker, install_fake_model
from sqlalchemy import text
from test_local_models import Server, make_entry, manager, run, server  # noqa: F401 - fixtures

from agentic_os.models import DocStatus, KnowledgeDoc
from agentic_os.services.knowledge import index, search
from agentic_os.services.knowledge.worker import ProcessWorker

DOCS = "/api/knowledge/docs"


def folder(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def add(client: TestClient, tmp_path: Path, name: str, content: str, **level) -> dict:
    path = tmp_path / "docs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    body = {"scope": "general", "paths": [str(path)], **level}
    return client.post(f"{DOCS}/files", json=body).json()[0]["doc"]


def process(client: TestClient) -> None:
    client.app.state.knowledge.run_pending(FakeEmbedWorker())


# ------------------------------------------------------------------------- downloads
@pytest.mark.parametrize("code", [401, 403])
def test_a_download_that_needs_an_account_says_so(manager, server, code: int):  # noqa: F811
    from test_local_models import blob

    entry = make_entry(server, {"model.bin": blob(1000, 1)})
    server.statuses["/model.bin"] = code
    state = run(manager, entry)
    # Not a «network» or «checksum» error: the UI asks for the token by this code.
    assert (state.state, state.error_code) == ("error", f"http_{code}")


# --------------------------------------------------------------------------- the index
def test_the_vector_cache_is_dropped_when_the_change_is_committed(client: TestClient):
    with client.app.state.sessionmaker() as db:
        before = search.cache._version
        index.clear(db, "nothing")
        assert search.cache._version == before  # a search now would cache the old rows…
        db.commit()
        assert search.cache._version == before + 1  # …so the version moves after the commit


def test_the_words_are_searched_only_among_the_visible_documents(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_fake_model(client, monkeypatch)
    mine = client.post("/api/projects", json={"name": "Web", "path": str(folder(tmp_path, "web"))})
    other = client.post(
        "/api/projects", json={"name": "Otro", "path": str(folder(tmp_path, "otro"))}
    )
    add(
        client, tmp_path, "mio.md", "# Errores\n\nEl código ERR_9999 indica fallo.",
        scope="project", project_id=mine.json()["id"],
    )  # fmt: skip
    add(
        client, tmp_path, "ajeno.md", "# Otro\n\nERR_9999 ERR_9999 ERR_9999 ERR_9999 ERR_9999.",
        scope="project", project_id=other.json()["id"],
    )  # fmt: skip
    process(client)
    monkeypatch.setattr(search, "WORDS_FETCH", 1)  # a window the other project's text can fill
    found = client.post(
        "/api/knowledge/search", json={"query": "ERR_9999", "project_id": mine.json()["id"]}
    ).json()
    assert [h["title"] for h in found["hits"]] == ["mio.md"]


# ------------------------------------------------------------------------ documents
def test_a_document_being_processed_cannot_be_relocated(client: TestClient, tmp_path: Path):
    doc = add(client, tmp_path, "a.md", "# A\n\ntexto")
    other = tmp_path / "docs" / "b.md"
    other.write_text("# B\n\notro", encoding="utf-8")
    with client.app.state.sessionmaker() as db:
        db.get(KnowledgeDoc, doc["id"]).status = DocStatus.CONVERTING
        db.commit()
    response = client.post(
        f"{DOCS}/{doc['id']}/relocate", json={"path": str(other), "confirm": True}
    )
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "processing")


def count(client: TestClient, sql: str, **params) -> int:
    with client.app.state.sessionmaker() as db:
        return db.execute(text(sql), params).scalar()


def test_deleting_a_project_removes_its_documents_and_their_words(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_fake_model(client, monkeypatch)
    project = client.post(
        "/api/projects", json={"name": "Web", "path": str(folder(tmp_path, "web"))}
    ).json()
    doc = add(
        client, tmp_path, "p.md", "# P\n\nERR_1234", scope="project", project_id=project["id"]
    )
    process(client)
    assert count(client, "SELECT count(*) FROM knowledge_fts WHERE doc_id = :d", d=doc["id"]) == 1
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert count(client, "SELECT count(*) FROM knowledge_fts WHERE doc_id = :d", d=doc["id"]) == 0
    assert count(client, "SELECT count(*) FROM knowledge_docs") == 0


def test_deleting_an_agent_removes_its_documents_and_their_words(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_fake_model(client, monkeypatch)
    agent = client.post("/api/agents", json={"name": "Dev", "role": "R", "cli": "claude"}).json()
    doc = add(client, tmp_path, "a.md", "# A\n\nERR_4321", scope="agent", agent_id=agent["id"])
    process(client)
    assert client.delete(f"/api/agents/{agent['id']}").status_code == 204
    assert count(client, "SELECT count(*) FROM knowledge_fts WHERE doc_id = :d", d=doc["id"]) == 0
    assert count(client, "SELECT count(*) FROM knowledge_docs") == 0


# --------------------------------------------------------------------------- shutdown
def test_closing_the_worker_does_not_wait_for_the_request_in_flight():
    class Proc:
        killed = threading.Event()

        def kill(self):
            self.killed.set()

        def poll(self):
            return None if not self.killed.is_set() else 1

        def wait(self, timeout=None):
            return 1

    worker = ProcessWorker(command=lambda: [], idle_seconds=3600)
    proc = Proc()
    worker._proc = proc  # type: ignore[assignment]
    holding = threading.Event()

    def request_in_flight():
        with worker._lock:  # a long conversion: it ends only when its process dies
            holding.set()
            proc.killed.wait(timeout=10)

    thread = threading.Thread(target=request_in_flight)
    thread.start()
    holding.wait(timeout=5)
    closer = threading.Thread(target=worker.close)
    closer.start()
    closer.join(timeout=5)
    assert not closer.is_alive(), "close() waited for the request instead of ending it"
    thread.join(timeout=5)
