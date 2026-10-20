"""Knowledge library (phase 14, block 1): documents by reference."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agentic_os.api import knowledge as knowledge_api
from agentic_os.models import KnowledgeDoc
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs as doc_ops

DOCS = "/api/knowledge/docs"


def make_file(folder: Path, name: str, content: str | bytes = "hola") -> str:
    path = folder / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return str(path)


def add(client: TestClient, paths: list[str], **level) -> list[dict]:
    body = {"scope": "general", "paths": paths, **level}
    response = client.post(f"{DOCS}/files", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def add_one(client: TestClient, path: str, **level) -> dict:
    item = add(client, [path], **level)[0]
    assert item["doc"] is not None, item
    return item["doc"]


def project(client: TestClient, tmp_path: Path, name: str = "Web") -> dict:
    folder = tmp_path / f"proj-{name}"
    folder.mkdir()
    response = client.post("/api/projects", json={"name": name, "path": str(folder)})
    assert response.status_code == 201
    return response.json()


def agent(client: TestClient, name: str = "Redactor") -> dict:
    response = client.post("/api/agents", json={"name": name, "role": "Redacta", "cli": "claude"})
    assert response.status_code == 201, response.text
    return response.json()


def process(client: TestClient, doc_id: str) -> None:
    """What block 2's pipeline will do: fingerprint the original and keep its Markdown."""
    with client.app.state.sessionmaker() as db:
        doc = db.get(KnowledgeDoc, doc_id)
        path = Path(doc.path)
        info = path.stat()
        doc.size, doc.source_mtime = info.st_size, info.st_mtime
        doc.sha256 = doc_ops.sha256_of(path)
        doc.status, doc.markdown, doc.md_tokens = "ready", "# Texto\n\nconvertido", 5
        db.commit()


# ------------------------------------------------------------------------------ adding
def test_add_files_creates_queued_documents(client: TestClient, tmp_path: Path):
    items = add(client, [make_file(tmp_path, "manual.md"), make_file(tmp_path, "datos.xlsx")])
    docs = [i["doc"] for i in items]
    assert [d["title"] for d in docs] == ["manual.md", "datos.xlsx"]
    first = docs[0]
    assert (first["scope"], first["status"], first["presence"]) == ("general", "queued", "ok")
    assert (first["source_kind"], first["viewer"], first["extension"]) == (
        "file",
        "markdown",
        ".md",
    )
    assert docs[1]["viewer"] == "system"  # Excel opens with the system's application
    assert first["path"] == str(tmp_path / "manual.md")
    assert first["has_markdown"] is False


def test_one_bad_path_does_not_stop_the_batch(client: TestClient, tmp_path: Path):
    folder = tmp_path / "carpeta"
    folder.mkdir()
    good = make_file(tmp_path, "bien.txt")
    items = add(client, [str(tmp_path / "no-existe.pdf"), str(folder), good, "relativa.md"])
    assert [i["error_code"] for i in items] == [
        "file_not_found",
        "not_a_file",
        None,
        "path_not_absolute",
    ]
    assert items[2]["doc"]["title"] == "bien.txt"
    assert len(client.get(DOCS).json()) == 1


def test_a_file_over_the_limit_is_refused(client: TestClient, tmp_path: Path):
    big = make_file(tmp_path, "grande.pdf", b"x" * (1024 * 1024 + 1))
    with client.app.state.sessionmaker() as db:
        knowledge_config.save(db, {"max_file_mb": 1})
        db.commit()
    item = add(client, [big])[0]
    assert item["doc"] is None
    assert item["error_code"] == "too_large"


def test_an_unsupported_format_is_created_as_a_failure(client: TestClient, tmp_path: Path):
    doc = add_one(client, make_file(tmp_path, "programa.exe"))
    assert (doc["status"], doc["error_code"]) == ("failed", "unsupported")


def test_the_same_file_cannot_be_added_twice_to_a_level(client: TestClient, tmp_path: Path):
    path = make_file(tmp_path, "uno.md")
    add_one(client, path)
    assert add(client, [path])[0]["error_code"] == "already_added"
    # Another spelling of the same path is the same file.
    assert add(client, [path.replace("\\", "/")])[0]["error_code"] == "already_added"
    # But another level may hold it.
    web = project(client, tmp_path)
    again = add_one(client, path, scope="project", project_id=web["id"])
    assert again["scope"] == "project"


def test_add_url(client: TestClient):
    response = client.post(
        f"{DOCS}/url", json={"scope": "general", "url": " https://docs.example.com/api/ "}
    )
    assert response.status_code == 201
    doc = response.json()
    assert (doc["source_kind"], doc["viewer"], doc["path"]) == ("url", "url", None)
    assert doc["url"] == "https://docs.example.com/api/"
    assert doc["title"] == "docs.example.com/api"
    again = client.post(
        f"{DOCS}/url", json={"scope": "general", "url": "https://docs.example.com/api/"}
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_added"
    for bad in ("ftp://x.com/a", "docs.example.com", "https://"):
        response = client.post(f"{DOCS}/url", json={"scope": "general", "url": bad})
        assert response.status_code == 422, bad


# ------------------------------------------------------------------------------ levels
def test_the_three_levels(client: TestClient, tmp_path: Path):
    web, blog = project(client, tmp_path, "Web"), project(client, tmp_path, "Blog")
    writer = agent(client)
    add_one(client, make_file(tmp_path, "general.md"))
    add_one(client, make_file(tmp_path, "web.md"), scope="project", project_id=web["id"])
    add_one(client, make_file(tmp_path, "blog.md"), scope="project", project_id=blog["id"])
    add_one(client, make_file(tmp_path, "marca.md"), scope="agent", agent_id=writer["id"])

    def titles(**query) -> list[str]:
        return [d["title"] for d in client.get(DOCS, params=query).json()]

    assert titles() == ["general.md", "web.md", "blog.md", "marca.md"]
    assert titles(scope="general") == ["general.md"]
    assert titles(scope="project", project_id=web["id"]) == ["web.md"]
    assert titles(scope="agent", agent_id=writer["id"]) == ["marca.md"]


def test_a_level_needs_its_owner(client: TestClient, tmp_path: Path):
    web = project(client, tmp_path)
    path = make_file(tmp_path, "a.md")
    body = {"paths": [path]}
    for level in (
        {"scope": "general", "project_id": web["id"]},
        {"scope": "project"},
        {"scope": "project", "project_id": web["id"], "agent_id": "x"},
        {"scope": "agent"},
    ):
        response = client.post(f"{DOCS}/files", json={**body, **level})
        assert response.status_code == 422, level
        assert response.json()["detail"]["code"] == "level_mismatch"
    missing = client.post(f"{DOCS}/files", json={**body, "scope": "project", "project_id": "nope"})
    assert missing.status_code == 404
    gone = client.post(f"{DOCS}/files", json={**body, "scope": "agent", "agent_id": "nope"})
    assert gone.status_code == 404


def test_documents_die_with_their_project_and_agent(client: TestClient, tmp_path: Path):
    web = project(client, tmp_path)
    writer = agent(client)
    add_one(client, make_file(tmp_path, "web.md"), scope="project", project_id=web["id"])
    add_one(client, make_file(tmp_path, "marca.md"), scope="agent", agent_id=writer["id"])
    assert client.delete(f"/api/projects/{web['id']}").status_code == 204
    assert client.delete(f"/api/agents/{writer['id']}").status_code == 204
    assert client.get(DOCS).json() == []


# ---------------------------------------------------------------------------- presence
def test_a_deleted_or_moved_original_is_reported(client: TestClient, tmp_path: Path):
    path = make_file(tmp_path, "informe.md")
    doc = add_one(client, path)
    process(client, doc["id"])
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "ok"

    moved = tmp_path / "otro.md"
    Path(path).rename(moved)
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "missing"
    assert client.get(DOCS).json()[0]["presence"] == "missing"
    assert client.get(f"{DOCS}/{doc['id']}/original").status_code == 410
    assert client.post(f"{DOCS}/{doc['id']}/open").status_code == 410
    assert client.post(f"{DOCS}/{doc['id']}/reveal").status_code == 410
    # The Markdown it was converted to is still there for the agents.
    assert client.get(f"{DOCS}/{doc['id']}/markdown").status_code == 200

    moved.rename(path)
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "ok"


def test_a_changed_original_is_reported_but_a_touched_one_is_not(
    client: TestClient, tmp_path: Path
):
    path = make_file(tmp_path, "informe.md", "versión uno")
    doc = add_one(client, path)
    process(client, doc["id"])

    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 60))  # same content, newer date
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "ok"

    Path(path).write_text("versión dos, distinta", encoding="utf-8")
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "changed"


def test_an_unprocessed_document_cannot_be_called_changed(client: TestClient, tmp_path: Path):
    path = make_file(tmp_path, "nuevo.md", "uno")
    doc = add_one(client, path)
    Path(path).write_text("dos, antes de procesarlo", encoding="utf-8")
    assert client.get(f"{DOCS}/{doc['id']}").json()["presence"] == "ok"


# ---------------------------------------------------------------------------- relocate
def test_relocating_to_the_same_content_keeps_the_index(client: TestClient, tmp_path: Path):
    path = make_file(tmp_path, "informe.md", "contenido")
    doc = add_one(client, path)
    process(client, doc["id"])
    new = tmp_path / "archivo"
    new.mkdir()
    Path(path).rename(new / "informe-v2.md")

    response = client.post(
        f"{DOCS}/{doc['id']}/relocate", json={"path": str(new / "informe-v2.md")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reprocess"] is False
    assert body["doc"]["presence"] == "ok"
    assert body["doc"]["path"] == str(new / "informe-v2.md")
    assert (body["doc"]["status"], body["doc"]["has_markdown"]) == ("ready", True)


def test_relocating_to_other_content_asks_for_confirmation(client: TestClient, tmp_path: Path):
    path = make_file(tmp_path, "informe.md", "original")
    doc = add_one(client, path)
    process(client, doc["id"])
    other = make_file(tmp_path, "distinto.md", "otro documento")
    url = f"{DOCS}/{doc['id']}/relocate"

    refused = client.post(url, json={"path": other})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "different_content"
    assert client.get(f"{DOCS}/{doc['id']}").json()["path"] == path

    accepted = client.post(url, json={"path": other, "confirm": True}).json()
    assert accepted["reprocess"] is True
    assert (accepted["doc"]["path"], accepted["doc"]["status"]) == (other, "queued")


def test_relocate_checks_the_new_path(client: TestClient, tmp_path: Path):
    doc = add_one(client, make_file(tmp_path, "a.md"))
    taken = make_file(tmp_path, "b.md")
    add_one(client, taken)
    url = f"{DOCS}/{doc['id']}/relocate"
    assert client.post(url, json={"path": str(tmp_path / "no.md")}).status_code == 404
    assert client.post(url, json={"path": str(tmp_path)}).status_code == 422
    assert client.post(url, json={"path": "relativa.md"}).status_code == 422
    assert client.post(url, json={"path": taken}).json()["detail"]["code"] == "already_added"
    web = client.post(f"{DOCS}/url", json={"scope": "general", "url": "https://a.com/x"}).json()
    assert client.post(f"{DOCS}/{web['id']}/relocate", json={"path": taken}).status_code == 422


# ------------------------------------------------------------------------------ changes
def test_edit_and_move_a_document(client: TestClient, tmp_path: Path):
    web = project(client, tmp_path)
    doc = add_one(client, make_file(tmp_path, "a.md"))
    url = f"{DOCS}/{doc['id']}"

    edited = client.patch(
        url, json={"title": "  Guía de estilo ", "description": "Tono", "mode": "context"}
    ).json()
    assert (edited["title"], edited["description"], edited["mode"]) == (
        "Guía de estilo",
        "Tono",
        "context",
    )

    forced = client.patch(url, json={"describe_images": True}).json()
    assert forced["describe_images"] is True
    assert client.patch(url, json={"describe_images": None}).json()["describe_images"] is None
    assert client.patch(url, json={"title": "Otro"}).json()["describe_images"] is None

    moved = client.patch(url, json={"scope": "project", "project_id": web["id"]}).json()
    assert (moved["scope"], moved["project_id"]) == ("project", web["id"])
    assert moved["title"] == "Otro"
    back = client.patch(url, json={"scope": "general"}).json()
    assert (back["scope"], back["project_id"]) == ("general", None)


def test_invalid_edits(client: TestClient, tmp_path: Path):
    web = project(client, tmp_path)
    doc = add_one(client, make_file(tmp_path, "a.md"))
    url = f"{DOCS}/{doc['id']}"
    assert client.patch(url, json={"title": "   "}).status_code == 422
    assert client.patch(url, json={"mode": "siempre"}).status_code == 422
    assert client.patch(url, json={"nada": 1}).status_code == 422
    assert client.patch(url, json={"project_id": web["id"]}).status_code == 422  # no scope
    assert client.patch(url, json={"scope": "project"}).status_code == 422  # no owner
    assert client.patch(f"{DOCS}/nope", json={"title": "x"}).status_code == 404


def test_moving_to_a_level_that_has_the_same_original_is_refused(
    client: TestClient, tmp_path: Path
):
    web = project(client, tmp_path)
    path = make_file(tmp_path, "a.md")
    general = add_one(client, path)
    add_one(client, path, scope="project", project_id=web["id"])
    response = client.patch(
        f"{DOCS}/{general['id']}", json={"scope": "project", "project_id": web["id"]}
    )
    assert response.status_code == 409


def test_delete_removes_the_index_and_unshared_images(client: TestClient, tmp_path: Path):
    first = add_one(client, make_file(tmp_path, "a.md"))
    second = add_one(client, make_file(tmp_path, "b.md"))
    images = Path(client.app.state.settings.data_dir) / "knowledge" / "images"
    images.mkdir(parents=True)
    (images / "solo.png").write_bytes(b"1")
    (images / "compartida.png").write_bytes(b"2")
    with client.app.state.sessionmaker() as db:
        for number, (doc, file) in enumerate(
            (
                (first, "solo.png"),
                (first, "compartida.png"),
                (second, "compartida.png"),
            )
        ):
            db.execute(
                text(
                    "INSERT INTO knowledge_images (id, doc_id, ord, sha256, file, location, width,"
                    " height, ocr_text, description, described_by) VALUES (:id, :doc, :ord, 'h',"
                    " :file, '', 1, 1, '', '', '')"
                ),
                {"id": f"{doc['id']}-{file}", "doc": doc["id"], "file": file, "ord": number},
            )
        db.execute(
            text(
                'INSERT INTO knowledge_chunks (id, doc_id, ord, heading, location, start, "end",'
                " tokens, vector_model) VALUES ('c1', :doc, 0, '', '', 0, 1, 1, '')"
            ),
            {"doc": first["id"]},
        )
        db.execute(
            text("INSERT INTO knowledge_fts (text, chunk_id, doc_id) VALUES ('hola', 'c1', :doc)"),
            {"doc": first["id"]},
        )
        db.commit()

    assert client.delete(f"{DOCS}/{first['id']}").status_code == 204
    assert not (images / "solo.png").exists()
    assert (images / "compartida.png").exists()  # the other document still uses it
    with client.app.state.sessionmaker() as db:
        assert db.execute(text("SELECT count(*) FROM knowledge_fts")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM knowledge_chunks")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM knowledge_images")).scalar() == 1

    assert client.delete(f"{DOCS}/{second['id']}").status_code == 204
    assert not (images / "compartida.png").exists()
    assert client.delete(f"{DOCS}/{second['id']}").status_code == 404


# -------------------------------------------------------------------------- the content
def test_markdown_only_after_processing(client: TestClient, tmp_path: Path):
    doc = add_one(client, make_file(tmp_path, "a.md"))
    url = f"{DOCS}/{doc['id']}/markdown"
    refused = client.get(url)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "not_processed")
    process(client, doc["id"])
    body = client.get(url).json()
    assert (body["title"], body["markdown"], body["tokens"]) == ("a.md", "# Texto\n\nconvertido", 5)


@pytest.mark.parametrize(
    ("name", "content", "media_type"),
    [
        ("manual.pdf", b"%PDF-1.4 fake", "application/pdf"),
        ("foto.png", b"\x89PNG fake", "image/png"),
        ("pagina.html", b"<script>alert(1)</script>", "text/plain"),  # shown as code, not run
        ("notas.md", b"# Hola", "text/plain"),
    ],
)
def test_the_viewer_gets_the_original_with_a_safe_type(
    client: TestClient, tmp_path: Path, name: str, content: bytes, media_type: str
):
    doc = add_one(client, make_file(tmp_path, name, content))
    response = client.get(f"{DOCS}/{doc['id']}/original")
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_only_registered_documents_are_served(client: TestClient, tmp_path: Path):
    secret = make_file(tmp_path, "secreto.txt", "no")
    assert client.get(f"{DOCS}/original", params={"path": secret}).status_code == 404
    assert client.get(f"{DOCS}/nope/original").status_code == 404
    web = client.post(f"{DOCS}/url", json={"scope": "general", "url": "https://a.com/x"}).json()
    assert client.get(f"{DOCS}/{web['id']}/original").status_code == 422


def test_open_and_reveal(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    opened, revealed, browsed = [], [], []
    monkeypatch.setattr(knowledge_api, "open_path", opened.append)
    monkeypatch.setattr(knowledge_api, "reveal_path", revealed.append)
    monkeypatch.setattr(knowledge_api.webbrowser, "open", browsed.append)
    path = make_file(tmp_path, "datos.xlsx")
    doc = add_one(client, path)
    web = client.post(f"{DOCS}/url", json={"scope": "general", "url": "https://a.com/x"}).json()

    assert client.post(f"{DOCS}/{doc['id']}/open").status_code == 204
    assert client.post(f"{DOCS}/{doc['id']}/reveal").status_code == 204
    assert client.post(f"{DOCS}/{web['id']}/open").status_code == 204
    assert (opened, revealed, browsed) == ([path], [path], ["https://a.com/x"])
    assert client.post(f"{DOCS}/{web['id']}/reveal").status_code == 422  # nothing on the disk
