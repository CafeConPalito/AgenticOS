"""Phase 15, block 1: an agent's proposal is a document nobody reads yet, with its provenance and
the documents it was built on."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_helpers import FakeEmbedWorker, install_fake_model

from agentic_os.db.base import utcnow
from agentic_os.models import (
    DocStatus,
    KnowledgeDoc,
    KnowledgeProvenance,
    KnowledgeSource,
    Origin,
    Review,
    SourceKind,
)
from agentic_os.services.knowledge import search

DOCS = "/api/knowledge/docs"


def add_file(client: TestClient, tmp_path: Path, name: str, content: str) -> dict:
    path = tmp_path / "docs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    body = {"scope": "general", "paths": [str(path)]}
    return client.post(f"{DOCS}/files", json=body).json()[0]["doc"]


def add_proposal(
    client: TestClient, title: str, *, based_on: list[dict], review: str = Review.PROPOSED
) -> str:
    with client.app.state.sessionmaker() as db:
        doc = KnowledgeDoc(
            scope="general",
            title=title,
            source_kind=SourceKind.MARKDOWN,
            origin=Origin.AGENT,
            review=review,
            status=DocStatus.READY,
            markdown=f"# {title}\n\nTexto de la propuesta.",
            md_tokens=12,
        )
        db.add(doc)
        db.flush()
        db.add(
            KnowledgeProvenance(
                doc_id=doc.id,
                agent_name="Redactor",
                task_title="Documentar Celery",
                proposed_at=utcnow(),
                suggested_scope="general",
            )
        )
        for source in based_on:
            db.add(
                KnowledgeSource(doc_id=doc.id, source_id=source["id"], source_title=source["title"])
            )
        db.commit()
        return doc.id


def test_a_proposal_is_not_visible_to_the_agents_until_it_is_accepted(
    client: TestClient, tmp_path: Path
):
    manual = add_file(client, tmp_path, "celery.md", "Celery es una cola de tareas.")
    client.app.state.knowledge.run_pending(FakeEmbedWorker())
    proposal = add_proposal(client, "Guía de reintentos", based_on=[manual])
    with client.app.state.sessionmaker() as db:
        visible = {d.id for d in search.visible_docs(db, None, [])}
        assert manual["id"] in visible and proposal not in visible
        db.get(KnowledgeDoc, proposal).review = Review.NONE
        db.commit()
        assert proposal in {d.id for d in search.visible_docs(db, None, [])}


def test_the_list_can_be_filtered_by_review_and_origin(client: TestClient, tmp_path: Path):
    manual = add_file(client, tmp_path, "celery.md", "Celery es una cola de tareas.")
    proposal = add_proposal(client, "Guía de reintentos", based_on=[manual])
    proposed = client.get(DOCS, params={"review": "proposed"}).json()
    assert [d["id"] for d in proposed] == [proposal]
    assert [d["id"] for d in client.get(DOCS, params={"origin": "user"}).json()] == [manual["id"]]
    assert len(client.get(DOCS).json()) == 2


def test_a_proposal_reads_with_its_provenance_and_sources(client: TestClient, tmp_path: Path):
    manual = add_file(client, tmp_path, "celery.md", "Celery es una cola de tareas.")
    proposal = add_proposal(client, "Guía de reintentos", based_on=[manual])
    read = client.get(f"{DOCS}/{proposal}").json()
    assert (read["origin"], read["review"], read["source_kind"]) == (
        "agent",
        "proposed",
        "markdown",
    )
    assert read["viewer"] == "none" and read["file_name"] is None
    assert read["sources"] == [{"id": manual["id"], "title": manual["title"], "removed": False}]
    provenance = read["provenance"]
    assert provenance["agent_name"] == "Redactor"
    assert provenance["task_title"] == "Documentar Celery"
    assert provenance["suggested_scope"] == "general"
    # An ordinary document has neither.
    plain = client.get(f"{DOCS}/{manual['id']}").json()
    assert (plain["origin"], plain["review"], plain["provenance"], plain["sources"]) == (
        "user",
        "none",
        None,
        [],
    )


def test_deleting_the_source_keeps_the_derived_document_marked_as_removed(
    client: TestClient, tmp_path: Path
):
    manual = add_file(client, tmp_path, "celery.md", "Celery es una cola de tareas.")
    proposal = add_proposal(client, "Guía de reintentos", based_on=[manual])
    assert client.delete(f"{DOCS}/{manual['id']}").status_code == 204
    read = client.get(f"{DOCS}/{proposal}").json()
    assert read["sources"] == [{"id": None, "title": manual["title"], "removed": True}]


def test_renaming_a_source_renames_the_copy_the_derived_documents_keep(
    client: TestClient, tmp_path: Path
):
    manual = add_file(client, tmp_path, "celery.md", "Celery es una cola de tareas.")
    proposal = add_proposal(client, "Guía de reintentos", based_on=[manual])
    client.patch(f"{DOCS}/{manual['id']}", json={"title": "Manual de Celery"})
    assert client.get(f"{DOCS}/{proposal}").json()["sources"][0]["title"] == "Manual de Celery"


def test_deleting_a_proposal_deletes_its_provenance_and_sources(client: TestClient):
    proposal = add_proposal(client, "Guía", based_on=[])
    with client.app.state.sessionmaker() as db:
        db.add(KnowledgeSource(doc_id=proposal, source_id=None, source_title="Otro"))
        db.commit()
    assert client.delete(f"{DOCS}/{proposal}").status_code == 204
    with client.app.state.sessionmaker() as db:
        assert db.query(KnowledgeProvenance).count() == 0
        assert db.query(KnowledgeSource).count() == 0


def test_a_proposal_is_not_reindexed_when_the_model_changes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    install_fake_model(client, monkeypatch)
    add_proposal(client, "Guía", based_on=[])
    assert client.app.state.knowledge.stale_docs() == []


def test_a_proposal_waiting_in_the_inbox_outlives_its_task(client: TestClient):
    from agentic_os.models import InboxItem, InboxKind, InboxStatus, Resolution
    from agentic_os.services import inbox

    proposal = add_proposal(client, "Guía", based_on=[])
    with client.app.state.sessionmaker() as db:
        item = inbox.create(db, InboxKind.KNOWLEDGE, "Conocimiento propuesto: Guía", "")
        item.knowledge_doc_id = proposal
        other = inbox.create(db, InboxKind.STALLED, "Sin terminar", "")
        db.commit()
        # What closing a task does to everything that waited for it:
        inbox.resolve_pending(db, Resolution.DISMISSED)
        db.commit()
        assert db.get(InboxItem, item.id).status == InboxStatus.PENDING
        assert db.get(InboxItem, other.id).status == InboxStatus.RESOLVED
