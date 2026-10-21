"""Migration 0018 (phase 15, block 1): proposals, provenance, the links between documents and the
new Inbox kind."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-21 10:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _doc(doc_id: str, source_kind: str = "file") -> str:
    return (
        "INSERT INTO knowledge_docs (id, workspace_id, created_at, updated_at, scope, title,"
        " description, mode, source_kind, presence, status, progress_done, progress_total,"
        f" markdown, md_tokens, embed_model) VALUES ('{doc_id}', 'default', '{NOW}', '{NOW}',"
        f" 'general', 'T', '', 'auto', '{source_kind}', 'ok', 'ready', 0, 0, '', 0, '')"
    )


def test_existing_documents_are_the_users_and_need_no_review(settings: Settings):
    engine, config = _engine(settings, "0017")
    with engine.begin() as db:
        db.execute(text(_doc("d1")))
    command.upgrade(config, "0018")
    with engine.connect() as db:
        row = db.execute(
            text("SELECT origin, review, summary, centroid, centroid_model FROM knowledge_docs")
        ).one()
    assert tuple(row) == ("user", "none", "", None, "")


def test_a_markdown_document_is_allowed_only_after_the_migration(settings: Settings):
    engine, config = _engine(settings, "0017")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_doc("d1", "markdown")))
    command.upgrade(config, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("d1", "markdown")))


def test_origin_and_review_are_closed_sets(settings: Settings):
    engine, _ = _engine(settings, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("d1")))
    for column, value in (("origin", "robot"), ("review", "rejected")):
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(text(f"UPDATE knowledge_docs SET {column} = '{value}'"))


def test_a_related_pair_is_stored_once_and_in_order(settings: Settings):
    engine, _ = _engine(settings, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("a")))
        db.execute(text(_doc("b")))
        db.execute(text("INSERT INTO knowledge_related VALUES ('a', 'b', 0.5, 'm')"))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("INSERT INTO knowledge_related VALUES ('b', 'a', 0.5, 'm')"))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("INSERT INTO knowledge_related VALUES ('a', 'b', 0.6, 'm')"))


def test_deleting_the_source_keeps_the_derived_document(settings: Settings):
    engine, _ = _engine(settings, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("pdf")))
        db.execute(text(_doc("guide", "markdown")))
        db.execute(
            text(
                "INSERT INTO knowledge_sources (id, doc_id, source_id, source_title)"
                " VALUES ('s1', 'guide', 'pdf', 'Manual de Celery')"
            )
        )
        db.execute(text("DELETE FROM knowledge_docs WHERE id = 'pdf'"))
        left = db.execute(text("SELECT doc_id, source_id, source_title FROM knowledge_sources"))
        assert tuple(left.one()) == ("guide", None, "Manual de Celery")
        assert db.execute(text("SELECT count(*) FROM knowledge_docs")).scalar() == 1


def test_deleting_a_document_deletes_its_links(settings: Settings):
    engine, _ = _engine(settings, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("a")))
        db.execute(text(_doc("b")))
        db.execute(text("INSERT INTO knowledge_related VALUES ('a', 'b', 0.5, 'm')"))
        db.execute(text("DELETE FROM knowledge_docs WHERE id = 'b'"))
        assert db.execute(text("SELECT count(*) FROM knowledge_related")).scalar() == 0


def test_the_inbox_accepts_the_knowledge_kind(settings: Settings):
    engine, _ = _engine(settings, "0018")
    insert = (
        "INSERT INTO inbox_items (id, workspace_id, created_at, updated_at, kind, status,"
        " agent_name, agent_color, project_name, project_color, title, detail, options)"
        f" VALUES ('i1', 'default', '{NOW}', '{NOW}', '{{kind}}', 'pending', '', '#fff', '',"
        " '#fff', 'T', '', '[]')"
    )
    with engine.begin() as db:
        db.execute(text(insert.format(kind="knowledge")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(insert.format(kind="nonsense").replace("'i1'", "'i2'")))


def test_downgrade_and_upgrade_again(settings: Settings):
    engine, config = _engine(settings, "0018")
    with engine.begin() as db:
        db.execute(text(_doc("a")))
        db.execute(text(_doc("guide", "markdown")))
    command.downgrade(config, "0017")
    names = set(inspect(engine).get_table_names())
    assert not names & {
        "knowledge_provenance",
        "knowledge_sources",
        "knowledge_related",
        "knowledge_rejections",
    }
    columns = {c["name"] for c in inspect(engine).get_columns("knowledge_docs")}
    assert not columns & {"origin", "review", "summary", "centroid", "centroid_model"}
    with engine.connect() as db:  # the markdown document has no place in the old schema
        assert db.execute(text("SELECT count(*) FROM knowledge_docs")).scalar() == 1
    command.upgrade(config, "0018")
    assert "knowledge_related" in inspect(engine).get_table_names()
