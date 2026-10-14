"""Migration 0009 (phase 10 amendment): agents get a secondary CLI (none by default) and the Inbox
accepts the «switch» kind; the downgrade removes both."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-14 12:00:00.000000"


def test_agents_have_no_secondary_and_the_inbox_takes_switch(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0008")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agents (id, workspace_id, name, role, description, color, cli, model,"
                " instructions, permission_mode, allowed_tools, max_concurrency,"
                " can_spawn_subagents, can_create_tasks, status, created_at, updated_at)"
                " VALUES ('a1', 'default', 'Dev', '', '', '#fff', 'claude', '', '', 'ask', '[]', 1,"
                " 0, 0, 'active', :now, :now)"
            ),
            {"now": NOW},
        )
    command.upgrade(config, "0009")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT fallback_account_id, fallback_model, using_fallback_until,"
                " switch_decided_until FROM agents WHERE id = 'a1'"
            )
        ).one()
        assert tuple(row) == (None, "", None, None)
        conn.execute(
            text(
                "INSERT INTO inbox_items (id, workspace_id, kind, status, agent_name, agent_color,"
                " project_name, project_color, title, detail, options, created_at, updated_at)"
                " VALUES ('i1', 'default', 'switch', 'pending', '', '#fff', '', '#fff', 't', '',"
                " '[]', :now, :now)"
            ),
            {"now": NOW},
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE agents SET fallback_account_id = 'nope' WHERE id = 'a1'"))

    command.downgrade(config, "0008")
    with engine.begin() as conn:
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(agents)"))]
        assert "fallback_account_id" not in columns and "using_fallback_until" not in columns
        assert conn.execute(text("SELECT count(*) FROM inbox_items")).scalar() == 0
    engine.dispose()
