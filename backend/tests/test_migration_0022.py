"""Migration 0022 (phase 20, block 5): the avatar of agents and of saved templates."""

from pathlib import Path

from alembic import command
from sqlalchemy import inspect, text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-28 09:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _columns(engine, table: str) -> dict:
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


def test_existing_agents_keep_their_initials_and_downgrade_drops_the_column(settings: Settings):
    engine, config = _engine(settings, "0021")
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO agents (id, workspace_id, created_at, updated_at, name, role,"
                " description, color, cli, model, instructions, permission_mode, allowed_tools,"
                " max_concurrency, can_spawn_subagents, can_create_tasks, status, fallback_model,"
                " can_propose_agents) VALUES ('a1', 'default', :now, :now, 'Dev', '', '', '#fff',"
                " 'claude', '', '', 'ask', '[]', 1, 0, 0, 'active', '', 0)"
            ),
            {"now": NOW},
        )
    command.upgrade(config, "0022")
    for table in ("agents", "agent_templates"):
        column = _columns(engine, table)["avatar"]
        assert column["nullable"]
    with engine.connect() as db:
        assert db.execute(text("SELECT avatar FROM agents WHERE id = 'a1'")).scalar() is None

    command.downgrade(config, "0021")
    for table in ("agents", "agent_templates"):
        assert "avatar" not in _columns(engine, table)
    with engine.connect() as db:
        assert db.execute(text("SELECT name FROM agents WHERE id = 'a1'")).scalar() == "Dev"
