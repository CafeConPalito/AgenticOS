"""Migration 0017 (phase 14, block 4): pictures are numbered in their document, and a document
carries a notice and counts its pictures."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-19 10:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _document_and_picture(engine) -> None:
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO knowledge_docs (id, workspace_id, created_at, updated_at, scope,"
                " title, description, mode, source_kind, presence, status, progress_done,"
                " progress_total, markdown, md_tokens, embed_model) VALUES ('d1', 'default',"
                f" '{NOW}', '{NOW}', 'general', 'T', '', 'auto', 'file', 'ok', 'ready', 0, 0,"
                " '', 0, '')"
            )
        )
        db.execute(
            text(
                "INSERT INTO knowledge_images (id, doc_id, sha256, location, width, height,"
                " ocr_text, description, described_by) VALUES ('i1', 'd1', 'abc', '', 1, 1,"
                " '', '', '')"
            )
        )


def test_existing_rows_get_sensible_defaults(settings: Settings):
    engine, config = _engine(settings, "0016")
    _document_and_picture(engine)
    command.upgrade(config, "0017")
    with engine.connect() as db:
        doc = db.execute(text("SELECT notice, image_count FROM knowledge_docs")).one()
        image = db.execute(text("SELECT ord, kind FROM knowledge_images")).one()
    assert tuple(doc) == (None, 0)
    assert tuple(image) == (0, "embedded")


def test_a_picture_number_is_unique_inside_its_document(settings: Settings):
    engine, _ = _engine(settings, "0017")
    _document_and_picture(engine)
    insert = (
        "INSERT INTO knowledge_images (id, doc_id, ord, kind, sha256, location, width, height,"
        " ocr_text, description, described_by) VALUES ('{id}', 'd1', {ord}, 'embedded', 'h', '',"
        " 1, 1, '', '', '')"
    )
    with engine.begin() as db:
        db.execute(text(insert.format(id="i2", ord=1)))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(insert.format(id="i3", ord=1)))


def test_downgrade_and_upgrade_again(settings: Settings):
    engine, config = _engine(settings, "0017")
    command.downgrade(config, "0016")
    columns = {c["name"] for c in inspect(engine).get_columns("knowledge_images")}
    assert "ord" not in columns and "kind" not in columns
    assert "notice" not in {c["name"] for c in inspect(engine).get_columns("knowledge_docs")}
    command.upgrade(config, "0017")
    assert "image_count" in {c["name"] for c in inspect(engine).get_columns("knowledge_docs")}
