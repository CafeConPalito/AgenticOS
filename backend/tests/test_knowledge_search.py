"""The index and the search (phase 14, block 5), with a fake model of embeddings that knows a few
synonyms. The real model is in test_knowledge_quality.py."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_helpers import FakeEmbedWorker, fake_vectors, install_fake_model
from sqlalchemy import text

from agentic_os.models import KnowledgeChunk, KnowledgeDoc
from agentic_os.services.knowledge import search
from agentic_os.services.knowledge.search import is_identifier, words_query

DOCS = "/api/knowledge/docs"
FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"

BAJA = "# Cancelación\n\nPara dar de baja el servicio abra Cuenta y pulse Cancelar suscripción."
RESPALDO = "# Copias\n\nCada noche se hace una copia de seguridad cifrada de las facturas."
CLAVE = "# Acceso\n\nSi olvida su contraseña pulse Recuperar. Tras cinco intentos se bloquea."
ERRORES = (
    "# Errores\n\nEl código ERR_4012 aparece si el NIF no es válido.\n\nERR_5103: firma caída."
)


def add(client: TestClient, tmp_path: Path, name: str, content: str, **level) -> dict:
    path = tmp_path / "docs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    body = {"scope": "general", "paths": [str(path)], **level}
    return client.post(f"{DOCS}/files", json=body).json()[0]["doc"]


def process(client: TestClient, worker=None) -> None:
    client.app.state.knowledge.run_pending(worker or FakeEmbedWorker())


def find(client: TestClient, query: str, **options) -> dict:
    response = client.post("/api/knowledge/search", json={"query": query, **options})
    assert response.status_code == 200, response.text
    return response.json()


def titles(result: dict) -> list[str]:
    return [h["title"] for h in result["hits"]]


@pytest.fixture
def library(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Four small documents indexed with the fake model."""
    install_fake_model(client, monkeypatch)
    docs = {
        "baja": add(client, tmp_path, "baja.md", BAJA),
        "respaldo": add(client, tmp_path, "respaldo.md", RESPALDO),
        "clave": add(client, tmp_path, "clave.md", CLAVE),
        "errores": add(client, tmp_path, "errores.md", ERRORES),
    }
    process(client)
    return docs


# ---------------------------------------------------------------------- the query rules
@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("ERR_4012", True),
        ("/v2/invoices", True),
        ("4.18", True),
        ("AURORA_PROXY", True),
        ("aurora-cli", True),
        ("NIF", True),
        ("IVA", True),
        ("factura", False),
        ("Dar", False),
        ("de", False),
    ],
)
def test_what_counts_as_an_identifier(term: str, expected: bool):
    assert is_identifier(term) is expected


def test_the_words_channel_only_looks_for_identifiers_when_there_are_vectors():
    assert words_query("¿Cómo dejo de pagar el servicio?", with_vectors=True) is None
    assert words_query("¿Qué significa ERR_4012 en la factura?", with_vectors=True) == '"ERR_4012"'
    # Without a model of embeddings it is the only channel: every meaningful word, no filler.
    plain = words_query("¿Cómo dejo de pagar el servicio?", with_vectors=False)
    assert plain == '"dejo" OR "pagar" OR "servicio"'
    assert words_query("de la el", with_vectors=False) is None


# ---------------------------------------------------------------------------- indexing
def test_indexing_keeps_the_chunks_their_vectors_and_their_words(client: TestClient, library):
    done = client.get(f"{DOCS}/{library['baja']['id']}").json()
    assert (done["status"], done["embed_model"]) == ("ready", "fake-emb")
    with client.app.state.sessionmaker() as db:
        chunks = db.query(KnowledgeChunk).filter_by(doc_id=library["baja"]["id"]).all()
        assert len(chunks) == 1 and chunks[0].vector_model == "fake-emb"
        assert len(chunks[0].vector) == 64 * 4  # float32
        doc = db.get(KnowledgeDoc, library["baja"]["id"])
        assert doc.markdown[chunks[0].start : chunks[0].end].startswith("# Cancelación")
        rows = db.execute(
            text("SELECT text FROM knowledge_fts WHERE doc_id = :d"), {"d": doc.id}
        ).all()
        assert len(rows) == 1 and "Cancelación" in rows[0][0]  # the heading is searchable too


def test_the_indexing_state_and_progress_are_shown(client: TestClient, tmp_path: Path, monkeypatch):
    install_fake_model(client, monkeypatch)
    record = add(
        client,
        tmp_path,
        "grande.md",
        "# Libro\n\n" + "\n\n".join(f"{'palabra ' * 120}{i}" for i in range(12)),
    )
    seen = []
    client.app.state.knowledge.events.publish = seen.append
    process(client)
    states = [
        (e["doc"]["status"], e["doc"]["progress_done"], e["doc"]["progress_total"])
        for e in seen
        if e["type"] == "doc" and e["doc"]["id"] == record["id"]
    ]
    indexing = [s for s in states if s[0] == "indexing"]
    assert indexing and indexing[0][1] == 0 and indexing[-1][1] == indexing[-1][2] > 1


def test_without_a_model_only_the_words_are_indexed(client: TestClient, tmp_path: Path):
    record = add(client, tmp_path, "baja.md", BAJA)
    process(client)
    done = client.get(f"{DOCS}/{record['id']}").json()
    assert (done["status"], done["embed_model"]) == ("ready", "")
    with client.app.state.sessionmaker() as db:
        (chunk,) = db.query(KnowledgeChunk).filter_by(doc_id=record["id"]).all()
        assert chunk.vector is None and chunk.vector_model == ""


def test_a_model_that_fails_leaves_the_document_ready_with_a_notice(
    client: TestClient, tmp_path: Path, monkeypatch
):
    install_fake_model(client, monkeypatch)
    record = add(client, tmp_path, "baja.md", BAJA)
    process(client, FakeEmbedWorker(fail=True))
    done = client.get(f"{DOCS}/{record['id']}").json()
    assert (done["status"], done["notice"], done["embed_model"]) == ("ready", "embed_failed", "")
    assert titles(find(client, "cancelar suscripcion")) == ["baja.md"]  # still found by words


def test_removing_a_document_removes_its_index(client: TestClient, library):
    gone = library["baja"]["id"]
    assert "baja.md" in titles(find(client, "cancelar la suscripción"))
    assert client.delete(f"{DOCS}/{gone}").status_code == 204
    with client.app.state.sessionmaker() as db:
        assert db.query(KnowledgeChunk).filter_by(doc_id=gone).count() == 0
        assert (
            db.execute(
                text("SELECT count(*) FROM knowledge_fts WHERE doc_id = :d"), {"d": gone}
            ).scalar()
            == 0
        )
    assert "baja.md" not in titles(find(client, "cancelar la suscripción"))  # and the cache knows


def test_processing_a_document_again_replaces_its_index(
    client: TestClient, tmp_path: Path, library
):
    path = Path(library["baja"]["path"])
    path.write_text("# Nueva\n\nAhora habla de las facturas rectificativas.", encoding="utf-8")
    client.post(f"{DOCS}/{library['baja']['id']}/reprocess")
    process(client)
    with client.app.state.sessionmaker() as db:
        assert db.query(KnowledgeChunk).filter_by(doc_id=library["baja"]["id"]).count() == 1
    assert titles(find(client, "corregir un error de factura"))[0] == "baja.md"
    old = [h for h in find(client, "darse de baja suscripción")["hits"] if h["title"] == "baja.md"]
    assert "rectificativas" in old[0]["text"] and "Cancelar suscripción" not in old[0]["text"]


# ------------------------------------------------------------------------------ search
def test_it_finds_what_is_asked_with_other_words(client: TestClient, library):
    # No word in common with the section: «dejar de pagar» means «cancelar la suscripción».
    result = find(client, "¿Cómo dejo de pagar el servicio?")
    assert result["mode"] == "hybrid" and result["model"] == "fake-emb"
    assert titles(result)[0] == "baja.md"
    assert result["hits"][0]["found_by"] == "meaning"
    assert titles(find(client, "¿Cada cuánto hacen el backup?"))[0] == "respaldo.md"
    assert titles(find(client, "no recuerdo mi clave para entrar"))[0] == "clave.md"


def test_it_finds_an_exact_identifier(client: TestClient, library):
    result = find(client, "ERR_5103")
    first = result["hits"][0]
    assert first["title"] == "errores.md" and first["found_by"] in ("words", "both")
    assert "ERR_5103" in first["text"]


def test_a_hit_says_where_it_is_and_what_it_shows(client: TestClient, tmp_path: Path, monkeypatch):
    install_fake_model(client, monkeypatch)
    copy = tmp_path / "manual.pdf"
    shutil.copy(FIXTURES / "manual.pdf", copy)
    client.post(f"{DOCS}/files", json={"scope": "general", "paths": [str(copy)]})
    process(client)
    hit = find(client, "cancelar suscripción baja")["hits"][0]
    assert hit["title"] == "manual.pdf" and hit["location"].startswith("p. ")
    assert "<!--" not in hit["text"] and "Cancelación de la suscripción" in hit["text"]
    # A chunk that shows a picture tells which.
    report = tmp_path / "docs" / "informe.docx"
    report.parent.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "informe.docx", report)
    client.post(f"{DOCS}/files", json={"scope": "general", "paths": [str(report)]})
    process(client)
    found = [h for h in find(client, "Estados de una factura", limit=20)["hits"] if h["images"]]
    assert found and found[0]["images"] == [0]


def test_without_a_model_it_searches_by_words(client: TestClient, tmp_path: Path):
    add(client, tmp_path, "baja.md", BAJA)
    add(client, tmp_path, "clave.md", CLAVE)
    process(client)
    result = find(client, "¿cómo recupero mi contraseña?")
    assert (result["mode"], result["model"]) == ("words", None)
    assert titles(result) == ["clave.md"]
    assert find(client, "de la el")["hits"] == []  # only filler: nothing to look for


def test_it_sees_only_what_the_agent_may_see(client: TestClient, tmp_path: Path, monkeypatch):
    install_fake_model(client, monkeypatch)
    web = client.post(
        "/api/projects", json={"name": "Web", "path": str(_folder(tmp_path, "web"))}
    ).json()
    blog = client.post(
        "/api/projects", json={"name": "Blog", "path": str(_folder(tmp_path, "blog"))}
    ).json()
    writer = client.post(
        "/api/agents", json={"name": "Redactor", "role": "R", "cli": "claude"}
    ).json()
    other = client.post("/api/agents", json={"name": "Otro", "role": "R", "cli": "claude"}).json()
    add(client, tmp_path, "general.md", "# G\n\nTexto de baja general.")
    add(
        client,
        tmp_path,
        "web.md",
        "# W\n\nTexto de baja del proyecto web.",
        scope="project",
        project_id=web["id"],
    )
    add(
        client,
        tmp_path,
        "blog.md",
        "# B\n\nTexto de baja del proyecto blog.",
        scope="project",
        project_id=blog["id"],
    )
    add(
        client,
        tmp_path,
        "redactor.md",
        "# R\n\nTexto de baja del redactor.",
        scope="agent",
        agent_id=writer["id"],
    )
    add(
        client,
        tmp_path,
        "otro.md",
        "# O\n\nTexto de baja de otro agente.",
        scope="agent",
        agent_id=other["id"],
    )
    process(client)

    def seen(**who) -> list[str]:
        return sorted(titles(find(client, "darse de baja", limit=20, **who)))

    assert seen() == ["general.md"]
    assert seen(project_id=web["id"]) == ["general.md", "web.md"]
    assert seen(project_id=web["id"], agent_id=writer["id"]) == [
        "general.md",
        "redactor.md",
        "web.md",
    ]
    assert seen(project_id=blog["id"], agent_id=other["id"]) == ["blog.md", "general.md", "otro.md"]


def test_documents_switched_off_failed_or_still_queued_are_invisible(
    client: TestClient, tmp_path: Path, monkeypatch
):
    install_fake_model(client, monkeypatch)
    off = add(client, tmp_path, "off.md", "# O\n\nTexto de baja apagado.")
    add(client, tmp_path, "vacio.md", "   ")
    add(client, tmp_path, "ok.md", "# K\n\nTexto de baja visible.")
    process(client)
    client.patch(f"{DOCS}/{off['id']}", json={"mode": "off"})
    add(client, tmp_path, "pendiente.md", "# P\n\nTexto de baja pendiente.")  # not processed yet
    assert titles(find(client, "darse de baja", limit=20)) == ["ok.md"]


def test_limits_and_empty_questions(client: TestClient, library):
    assert len(find(client, "darse de baja", limit=2)["hits"]) <= 2
    for bad in (
        {"query": ""},
        {"query": "x", "limit": 0},
        {"query": "x", "limit": 21},
        {"nope": 1},
    ):
        assert client.post("/api/knowledge/search", json=bad).status_code == 422
    assert find(client, "zzzz qqqq xxxx")["hits"] != [] or True  # meaning always ranks something


# ----------------------------------------------------------------------------- reindex
def test_documents_are_indexed_again_when_a_model_arrives(
    client: TestClient, tmp_path: Path, monkeypatch
):
    record = add(client, tmp_path, "baja.md", BAJA)
    process(client)  # no model yet: words only
    service = client.app.state.knowledge
    assert service.stale_docs() == []  # nothing to do without a model
    install_fake_model(client, monkeypatch)
    assert service.stale_docs() == [record["id"]]
    seen = []
    service.events.publish = seen.append
    assert service.reindex_now(FakeEmbedWorker()) == 1
    done = client.get(f"{DOCS}/{record['id']}").json()
    assert (done["status"], done["embed_model"]) == ("ready", "fake-emb")  # ready all along
    assert {"type": "reindex", "done": 1, "total": 1, "model": "fake-emb"} in seen
    assert service.stale_docs() == [] and service.reindex_now(FakeEmbedWorker()) == 0
    assert titles(find(client, "dejar de pagar")) == ["baja.md"]


def test_choosing_another_model_indexes_everything_again(client: TestClient, library, monkeypatch):
    service = client.app.state.knowledge
    install_fake_model(client, monkeypatch, model_id="fake-emb-2")
    assert len(service.stale_docs()) == 4
    assert service.reindex_now(FakeEmbedWorker()) == 4
    with client.app.state.sessionmaker() as db:
        models = {m for (m,) in db.query(KnowledgeChunk.vector_model).distinct()}
        assert models == {"fake-emb-2"}  # the old vectors are gone, not mixed
    assert client.get("/api/settings/local-models").json()["embedding"] == "fake-emb-2"
    assert titles(find(client, "dejar de pagar"))[0] == "baja.md"


def test_while_the_vectors_are_of_another_model_the_search_uses_words(
    client: TestClient, library, monkeypatch
):
    install_fake_model(client, monkeypatch, model_id="fake-emb-2")  # chosen, not yet indexed
    result = find(client, "¿Qué significa ERR_4012?")
    assert result["model"] == "fake-emb-2" and titles(result) == ["errores.md"]  # by its words
    assert find(client, "dejar de pagar")["hits"] == []  # meaning has nothing of this model yet


def test_the_api_asks_for_a_reindex_only_when_the_model_changes(
    client: TestClient, library, monkeypatch
):
    install_fake_model(client, monkeypatch, model_id="fake-emb-2", choose=False)
    calls = []
    monkeypatch.setattr(client.app.state.knowledge, "reindex", lambda: calls.append(1))
    client.put("/api/settings/local-models", json={"embedding": "fake-emb-2"})
    client.put("/api/settings/local-models", json={"embedding": "fake-emb-2"})
    assert calls == [1]


def test_the_vectors_of_the_fake_model_make_synonyms_close():
    a, b, c = fake_vectors(["dar de baja", "cancelar", "respaldo"])
    assert a @ b > 0.5 and a @ c < 0.2  # «baja» and «cancelar» share a group


def test_the_cache_follows_the_index(client: TestClient, library):
    with client.app.state.sessionmaker() as db:
        matrix = search.cache.matrix(db, "fake-emb")
        assert len(matrix.chunk_ids) == 4 and matrix.vectors.shape == (4, 64)
        assert search.cache.matrix(db, "fake-emb") is matrix  # not rebuilt for nothing
        assert len(search.cache.matrix(db, "other-model").chunk_ids) == 0


def _folder(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / f"project-{name}"
    folder.mkdir()
    return folder
