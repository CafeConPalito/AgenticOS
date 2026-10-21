"""Agents propose knowledge, the person reviews it (phase 15, block 2). Driven by the official MCP
client against a real backend; there is no model of embeddings here, so the duplicate check
counts the exact text and the title (the meaning is tested with a fake model in the graph tests)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from test_mcp_server import call, events, mcp_url, seed_run
from test_scheduler_e2e import wait_until

from agentic_os.config import Settings
from agentic_os.models import InboxItem, KnowledgeDoc, KnowledgeRejection, Run

MANUAL = (
    "# Manual de Celery\n\nCelery es una cola de tareas distribuida para Python. Un productor "
    "publica un mensaje en un broker y los workers lo consumen. Las tareas se declaran con "
    "el decorador app.task y se lanzan con delay."
)
GUIDE = (
    "# Reintentos\n\nUna tarea que falla por un error transitorio debe reintentarse. Con "
    "autoretry_for se indican las excepciones y con retry_backoff se espacian los intentos. "
    "La tarea debe ser idempotente: ejecutada dos veces no puede duplicar el efecto."
)
OTHER = GUIDE.replace("Reintentos", "Colas").replace("transitorio", "de red")


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def api(server: LiveServer, method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{server.url}/api{path}", timeout=30, **kwargs)


def add_manual(server: LiveServer, tmp_path: Path, **level) -> dict:
    path = tmp_path / "library" / "celery.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(MANUAL, encoding="utf-8")
    body = {"scope": "general", "paths": [str(path)], **level}
    doc = api(server, "POST", "/knowledge/docs/files", json=body).json()[0]["doc"]
    assert wait_until(
        lambda: api(server, "GET", f"/knowledge/docs/{doc['id']}").json()["status"] == "ready",
        timeout=60,
    )
    return api(server, "GET", f"/knowledge/docs/{doc['id']}").json()


@pytest.fixture
def agent(server: LiveServer, tmp_path: Path) -> dict:
    run_id, token = seed_run(server, tmp_path)
    return {"run": run_id, "url": mcp_url(server, token), "manual": add_manual(server, tmp_path)}


def propose(agent: dict, **args) -> str:
    body = {
        "title": "Guía de reintentos",
        "markdown": GUIDE,
        "based_on": [agent["manual"]["title"]],
    }
    return call(agent["url"], "propose_knowledge", {**body, **args})


def proposals(server: LiveServer) -> list[dict]:
    return api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json()


# ------------------------------------------------------------------------------ proposing
def test_a_proposal_waits_for_review_and_is_linked_to_its_source(server: LiveServer, agent: dict):
    answer = propose(agent)
    assert answer.startswith("Propuesta registrada") and "no aparece en las búsquedas" in answer
    [found] = proposals(server)
    assert (found["title"], found["origin"], found["source_kind"]) == (
        "Guía de reintentos",
        "agent",
        "markdown",
    )
    assert found["sources"] == [
        {"id": agent["manual"]["id"], "title": agent["manual"]["title"], "removed": False}
    ]
    assert found["provenance"]["agent_name"] == "Dev"
    assert found["provenance"]["run_id"] == agent["run"]
    # It starts at the level of the document it is based on.
    assert (found["scope"], found["project_id"]) == ("general", None)
    with server.db() as db:
        [item] = db.query(InboxItem).filter(InboxItem.kind == "knowledge").all()
        assert item.knowledge_doc_id == found["id"] and item.status == "pending"
        assert item.agent_name == "Dev" and "Guía de reintentos" in item.title
    assert any(n == "propose_knowledge" for n, _ in events(server, agent["run"]))


def test_nobody_reads_a_proposal_before_it_is_accepted(server: LiveServer, agent: dict):
    propose(agent)
    found = call(agent["url"], "search_knowledge", {"query": "autoretry_for retry_backoff"})
    assert "No encontré nada" in found and "### " not in found  # no passage at all
    read = call(agent["url"], "read_knowledge", {"document": "Guía de reintentos"})
    assert "No encuentro un documento" in read and "idempotente" not in read
    assert "Guía de reintentos" not in call(agent["url"], "get_context")


def test_the_original_never_changes(server: LiveServer, agent: dict):
    before = api(server, "GET", f"/knowledge/docs/{agent['manual']['id']}/markdown").json()
    sha = agent["manual"]["size"]
    propose(agent)
    [found] = proposals(server)
    api(server, "POST", f"/knowledge/docs/{found['id']}/accept", json={})
    propose(agent, title="Otra", markdown=OTHER)
    [other] = proposals(server)
    api(server, "POST", f"/knowledge/docs/{other['id']}/reject", json={})
    after = api(server, "GET", f"/knowledge/docs/{agent['manual']['id']}/markdown").json()
    assert after == before
    assert api(server, "GET", f"/knowledge/docs/{agent['manual']['id']}").json()["size"] == sha


# ------------------------------------------------------------------------------ the decision
def test_accepting_with_edits_indexes_it_without_conversion(
    server: LiveServer, agent: dict, tmp_path: Path
):
    propose(agent)
    [found] = proposals(server)
    edited = GUIDE + "\n\nUsa también retry_jitter para no coincidir."
    accepted = api(
        server,
        "POST",
        f"/knowledge/docs/{found['id']}/accept",
        json={"title": "Reintentos en Celery", "markdown": edited, "scope": "general"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["review"] == "none"

    def ready() -> bool:
        return api(server, "GET", f"/knowledge/docs/{found['id']}").json()["status"] == "ready"

    assert wait_until(ready, timeout=60)
    doc = api(server, "GET", f"/knowledge/docs/{found['id']}").json()
    assert (doc["title"], doc["origin"], doc["provenance"]["edited"]) == (
        "Reintentos en Celery",
        "agent",
        True,
    )
    assert doc["provenance"]["decided_at"] is not None
    # Now it is searchable, and it says where it comes from.
    answer = call(agent["url"], "search_knowledge", {"query": "retry_jitter"})
    assert "Reintentos en Celery" in answer
    assert proposals(server) == []
    with server.db() as db:
        item = db.query(InboxItem).filter(InboxItem.knowledge_doc_id == found["id"]).one()
        assert (item.status, item.resolution) == ("resolved", "approved")


def test_accepting_can_move_it_to_another_level(server: LiveServer, agent: dict):
    propose(agent)
    [found] = proposals(server)
    with server.db() as db:
        project_id = db.get(Run, agent["run"]).project_id
    moved = api(
        server,
        "POST",
        f"/knowledge/docs/{found['id']}/accept",
        json={"scope": "project", "project_id": project_id},
    ).json()
    assert (moved["scope"], moved["project_id"]) == ("project", project_id)
    assert moved["provenance"]["edited"] is False  # the level is a decision, not an edit


def test_rejecting_deletes_it_and_remembers_it(server: LiveServer, agent: dict):
    propose(agent)
    [found] = proposals(server)
    rejected = api(
        server, "POST", f"/knowledge/docs/{found['id']}/reject", json={"reason": "ya lo sabemos"}
    )
    assert rejected.status_code == 204
    assert api(server, "GET", f"/knowledge/docs/{found['id']}").status_code == 404
    with server.db() as db:
        [memory] = db.query(KnowledgeRejection).all()
        assert (memory.title, memory.reason) == ("Guía de reintentos", "ya lo sabemos")
        item = db.query(InboxItem).filter(InboxItem.kind == "knowledge").one()
        assert (item.status, item.resolution) == ("resolved", "rejected")
        assert item.knowledge_doc_id is None  # the document is gone
    again = propose(agent)
    assert "ya rechazó" in again and "ya lo sabemos" in again
    assert proposals(server) == []


def test_a_decision_can_be_taken_only_once(server: LiveServer, agent: dict):
    propose(agent)
    [found] = proposals(server)
    assert api(server, "POST", f"/knowledge/docs/{found['id']}/accept", json={}).status_code == 200
    again = api(server, "POST", f"/knowledge/docs/{found['id']}/accept", json={})
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "not_proposed")
    assert (
        api(server, "POST", f"/knowledge/docs/{agent['manual']['id']}/reject", json={}).status_code
        == 409
    )


def test_deleting_a_proposal_dismisses_its_inbox_item(server: LiveServer, agent: dict):
    propose(agent)
    [found] = proposals(server)
    assert api(server, "DELETE", f"/knowledge/docs/{found['id']}").status_code == 204
    with server.db() as db:
        item = db.query(InboxItem).filter(InboxItem.kind == "knowledge").one()
        assert (item.status, item.resolution) == ("resolved", "dismissed")


# ----------------------------------------------------------------------------- the limits
def test_the_number_of_proposals_per_run_is_limited_and_the_agent_is_told(
    server: LiveServer, agent: dict
):
    api(server, "PUT", "/settings/knowledge", json={"proposals_per_run": 1})
    assert propose(agent).startswith("Propuesta registrada")
    refused = propose(agent, title="Otra", markdown=OTHER)
    assert "máximo es 1" in refused and len(proposals(server)) == 1


def test_proposals_can_be_switched_off(server: LiveServer, agent: dict):
    api(server, "PUT", "/settings/knowledge", json={"proposals_enabled": False})
    assert "desactivadas" in propose(agent) and proposals(server) == []


@pytest.mark.parametrize(
    ("args", "says"),
    [
        ({"markdown": "Muy corto."}, "demasiado corto"),
        ({"title": "  "}, "Falta el título"),
        ({"markdown": "palabra " * 30_000}, "demasiado largo"),
        ({"based_on": ["No existe ese documento"]}, "No encuentro un documento"),
        ({"level": "galaxia"}, "`level` debe ser"),
        ({"replaces": "celery.md"}, "Solo puedes proponer una versión nueva"),
    ],
)
def test_a_bad_proposal_is_refused_in_words(server: LiveServer, agent: dict, args: dict, says: str):
    assert says in propose(agent, **args)
    assert proposals(server) == []


def test_the_same_text_or_title_is_not_proposed_twice(server: LiveServer, agent: dict):
    propose(agent)
    same_text = propose(agent, title="Otro título")
    assert "Ya existe algo muy parecido" in same_text and "tiene exactamente ese texto" in same_text
    same_title = propose(agent, markdown=OTHER)
    assert "Ya existe algo muy parecido" in same_title and "mismo título" in same_title
    existing = propose(agent, title="celery.md", markdown=OTHER)
    assert "el conocimiento" in existing
    assert len(proposals(server)) == 1


def test_a_new_version_of_what_the_agent_proposed_lives_beside_it(server: LiveServer, agent: dict):
    propose(agent)
    [first] = proposals(server)
    api(server, "POST", f"/knowledge/docs/{first['id']}/accept", json={})
    assert wait_until(
        lambda: api(server, "GET", f"/knowledge/docs/{first['id']}").json()["status"] == "ready",
        timeout=60,
    )
    answer = propose(
        agent, title="Reintentos v2", markdown=OTHER, based_on=[], replaces="Guía de reintentos"
    )
    assert answer.startswith("Propuesta registrada")
    [second] = proposals(server)
    assert second["provenance"]["replaces_id"] == first["id"]
    assert [s["id"] for s in second["sources"]] == [first["id"]]
    # Both exist until the person picks «Reemplazar».
    assert api(server, "GET", f"/knowledge/docs/{first['id']}").status_code == 200
    api(
        server,
        "POST",
        f"/knowledge/docs/{second['id']}/accept",
        json={"replace": True},
    )

    def old_gone() -> bool:
        return api(server, "GET", f"/knowledge/docs/{first['id']}").status_code == 404

    assert wait_until(old_gone, timeout=60)
    new = api(server, "GET", f"/knowledge/docs/{second['id']}").json()
    assert new["status"] == "ready" and new["title"] == "Reintentos v2"
    with server.db() as db:
        assert db.query(KnowledgeDoc).filter(KnowledgeDoc.origin == "agent").count() == 1


# --------------------------------------------------------------------------- the marks
def accept_and_wait(server: LiveServer, doc_id: str, **body) -> None:
    assert api(server, "POST", f"/knowledge/docs/{doc_id}/accept", json=body).status_code == 200
    assert wait_until(
        lambda: api(server, "GET", f"/knowledge/docs/{doc_id}").json()["status"] == "ready",
        timeout=60,
    )


def test_an_accepted_document_says_it_was_generated_by_an_agent(server: LiveServer, agent: dict):
    propose(agent)
    [found] = proposals(server)
    accept_and_wait(server, found["id"])
    found_by_search = call(agent["url"], "search_knowledge", {"query": "autoretry_for"})
    assert "Guía de reintentos" in found_by_search and "generado por agente" in found_by_search
    read = call(agent["url"], "read_knowledge", {"document": "Guía de reintentos"})
    assert "generado por agente" in read and "idempotente" in read
    context = call(agent["url"], "get_context")
    index = next(line for line in context.splitlines() if "**Guía de reintentos**" in line)
    assert "generado por agente" in index
    assert "fíate más de las fuentes originales" in context
    assert "propose_knowledge" in context  # the agent is told it can propose


def test_the_context_does_not_invite_to_propose_when_proposals_are_off(
    server: LiveServer, agent: dict
):
    api(server, "PUT", "/settings/knowledge", json={"proposals_enabled": False})
    assert "propose_knowledge" not in call(agent["url"], "get_context")


# ----------------------------------------------------- the meaning (with a fake model)
BAJA = (
    "# Baja\n\nPara cancelar la suscripción abra Cuenta y pulse dar de baja. "
    "No se devuelve el cobro del mes en curso. "
) * 4


@pytest.fixture
def library(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """A run, and a document about cancelling the subscription indexed with the fake model."""
    from knowledge_helpers import FakeEmbedWorker, install_fake_model

    from agentic_os.models import Agent, Project

    install_fake_model(client, monkeypatch)
    with client.app.state.sessionmaker() as db:
        agent = Agent(name="Dev", role="R")
        project = Project(name="Web", path=str(tmp_path), path_key=str(tmp_path))
        db.add_all([agent, project])
        db.flush()
        run = Run(
            agent_id=agent.id,
            project_id=project.id,
            agent_name="Dev",
            agent_color="#4FD1C5",
            project_name="Web",
            cli="claude",
            prompt="x",
            cwd=str(tmp_path),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    path = tmp_path / "docs" / "baja.md"
    path.parent.mkdir()
    path.write_text(
        "# Baja\n\nPara cancelar la suscripción abra Cuenta y pulse dar de baja. "
        "No se devuelve el cobro del mes en curso. " * 4,
        encoding="utf-8",
    )
    body = {"scope": "general", "paths": [str(path)]}
    client.post("/api/knowledge/docs/files", json=body)
    client.app.state.knowledge.run_pending(FakeEmbedWorker())
    return {"client": client, "run": run_id}


def propose_direct(library: dict, **args):
    from agentic_os.services.knowledge import proposals

    client = library["client"]
    with client.app.state.sessionmaker() as db:
        run = db.get(Run, library["run"])
        return proposals.propose(db, client.app.state.knowledge, run, **args)[0]


# The same words but two of the group «cancelar, suscripción, baja…», which the fake model puts in
# the same place: the same idea in other words.
SAME_IDEA = BAJA.replace("cancelar", "dejar").replace("suscripción", "desuscribir")
ANOTHER = (
    "# Contraseña\n\nSi olvida la clave de acceso, pulse recuperar password en la pantalla de "
    "entrada y recibirá un enlace. Tras varios intentos fallidos la cuenta se bloquea. " * 3
)


def test_the_same_idea_in_other_words_is_a_duplicate(library: dict):
    answer = propose_direct(library, title="Cómo dejar de pagar", markdown=SAME_IDEA)
    assert "Ya existe algo muy parecido" in answer and "baja.md" in answer
    assert "prácticamente lo mismo" in answer


def test_something_different_is_accepted_and_keeps_its_centroid(library: dict):
    answer = propose_direct(library, title="Recuperar la clave", markdown=ANOTHER)
    assert answer.startswith("Propuesta registrada")
    client = library["client"]
    [found] = client.get("/api/knowledge/docs", params={"review": "proposed"}).json()
    with client.app.state.sessionmaker() as db:
        doc = db.get(KnowledgeDoc, found["id"])
        assert doc.centroid is not None and doc.centroid_model == "fake-emb"


def test_a_rejected_idea_is_remembered_by_meaning(library: dict):
    propose_direct(library, title="Recuperar la clave", markdown=ANOTHER)
    client = library["client"]
    [found] = client.get("/api/knowledge/docs", params={"review": "proposed"}).json()
    client.post(f"/api/knowledge/docs/{found['id']}/reject", json={"reason": "no hace falta"})
    paraphrase = ANOTHER.replace("Contraseña", "Acceso").replace("olvida", "olvide")
    answer = propose_direct(library, title="Otra vez la clave", markdown=paraphrase)
    assert "ya rechazó" in answer and "no hace falta" in answer


def test_an_indexed_document_has_a_centroid(library: dict):
    client = library["client"]
    [doc] = client.get("/api/knowledge/docs").json()
    with client.app.state.sessionmaker() as db:
        row = db.get(KnowledgeDoc, doc["id"])
        assert row.centroid is not None and row.centroid_model == "fake-emb"
