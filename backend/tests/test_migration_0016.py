"""Migration 0016 (phase 14): the knowledge library's tables and its full-text index."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-18 10:00:00.000000"


def _upgraded(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0016")
    return engine, config


def _doc(db, doc_id: str, scope: str = "general", project: str | None = None) -> None:
    db.execute(
        text(
            "INSERT INTO knowledge_docs (id, workspace_id, created_at, updated_at, scope,"
            " project_id, title, description, mode, source_kind, presence, status,"
            " progress_done, progress_total, markdown, md_tokens, embed_model)"
            f" VALUES ('{doc_id}', 'default', '{NOW}', '{NOW}', '{scope}', :project, 'T', '',"
            " 'auto', 'file', 'ok', 'queued', 0, 0, '', 0, '')"
        ),
        {"project": project},
    )


def test_tables_and_index_exist(settings: Settings):
    engine, _ = _upgraded(settings)
    tables = set(inspect(engine).get_table_names())
    assert {"knowledge_docs", "knowledge_chunks", "knowledge_images", "knowledge_fts"} <= tables


def test_the_words_index_ignores_accents(settings: Settings):
    engine, _ = _upgraded(settings)
    with engine.begin() as db:
        db.execute(
            text("INSERT INTO knowledge_fts (text, chunk_id, doc_id) VALUES (:t, 'c1', 'd1')"),
            {"t": "Para cancelar la suscripción pulse Dar de baja. Código ERR_4012."},
        )
        found = db.execute(
            text("SELECT chunk_id FROM knowledge_fts WHERE knowledge_fts MATCH :q"),
            {"q": '"suscripcion"'},
        ).all()
        exact = db.execute(
            text("SELECT chunk_id FROM knowledge_fts WHERE knowledge_fts MATCH :q"),
            {"q": '"ERR_4012"'},
        ).all()
    assert [row[0] for row in found] == ["c1"]
    assert [row[0] for row in exact] == ["c1"]


def test_a_document_belongs_to_exactly_one_level(settings: Settings):
    engine, _ = _upgraded(settings)
    with engine.begin() as db:
        _doc(db, "ok-general")
    for scope, project in (("project", None), ("general", "p1"), ("agent", None), ("nope", None)):
        with pytest.raises(IntegrityError), engine.begin() as db:
            _doc(db, "bad", scope, project)


def test_chunks_and_images_die_with_their_document(settings: Settings):
    engine, _ = _upgraded(settings)
    with engine.begin() as db:
        _doc(db, "d1")
        db.execute(
            text(
                'INSERT INTO knowledge_chunks (id, doc_id, ord, heading, location, start, "end",'
                " tokens, vector_model) VALUES ('c1', 'd1', 0, '', '', 0, 10, 3, '')"
            )
        )
        db.execute(
            text(
                "INSERT INTO knowledge_images (id, doc_id, sha256, location, width, height,"
                " ocr_text, description, described_by) VALUES ('i1', 'd1', 'abc', '', 1, 1,"
                " '', '', '')"
            )
        )
        db.execute(text("DELETE FROM knowledge_docs WHERE id = 'd1'"))
        assert db.execute(text("SELECT count(*) FROM knowledge_chunks")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM knowledge_images")).scalar() == 0


def test_downgrade_removes_everything_and_upgrade_comes_back(settings: Settings):
    engine, config = _upgraded(settings)
    command.downgrade(config, "0015")
    tables = set(inspect(engine).get_table_names())
    assert not {"knowledge_docs", "knowledge_chunks", "knowledge_images", "knowledge_fts"} & tables
    command.upgrade(config, "0016")
    assert "knowledge_fts" in set(inspect(engine).get_table_names())
