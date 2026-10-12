"""Migration 0006: runs from phase 06 get empty usage («pending») and the Inbox accepts the
new kinds; the downgrade removes them."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-11 12:00:00.000000"


def test_usage_columns_and_inbox_kinds(settings: Settings, tmp_path: Path):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0005")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, agent_name, agent_color, project_name, cli,"
                " model, prompt, cwd, status, activity, cols, rows, log_path, created_at,"
                " updated_at) VALUES ('r1', 'default', 'Dev', '#fff', 'p1', 'claude', '',"
                " 'hola', 'C:/p1', 'completed', 'idle', 120, 32, '', :now, :now)"
            ),
            {"now": NOW},
        )

    command.upgrade(config, "0006")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT usage_status, input_tokens, cost_usd, extra_transcripts, usage_models"
                " FROM runs WHERE id = 'r1'"
            )
        ).one()
        assert tuple(row) == ("pending", 0, None, "[]", "{}")
        conn.execute(
            text(
                "INSERT INTO inbox_items (id, workspace_id, kind, status, agent_name,"
                " agent_color, project_name, project_color, title, detail, options, created_at,"
                " updated_at) VALUES ('i1', 'default', 'quota', 'pending', '', '#fff', '',"
                " '#fff', 'Cuota agotada', '', '[]', :now, :now)"
            ),
            {"now": NOW},
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE runs SET usage_status = 'weird' WHERE id = 'r1'"))

    command.downgrade(config, "0005")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM inbox_items")).scalar() == 0
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(runs)"))]
        assert "usage_status" not in columns
    engine.dispose()
