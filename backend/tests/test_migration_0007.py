"""Migration 0007: existing runs are not resumed and keep their logs; the downgrade removes the
new columns."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-12 12:00:00.000000"


def test_resume_columns(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0006")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, agent_name, agent_color, project_name, cli,"
                " model, prompt, cwd, status, activity, cols, rows, log_path, created_at,"
                " updated_at) VALUES ('r1', 'default', 'Dev', '#fff', 'p1', 'claude', '',"
                " 'hola', 'C:/p1', 'interrupted', 'idle', 120, 32, '', :now, :now)"
            ),
            {"now": NOW},
        )

    command.upgrade(config, "0007")
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT resumed_from_id, usage_baseline, log_purged FROM runs WHERE id = 'r1'")
        ).one()
        assert tuple(row) == (None, None, 0)
        conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, agent_name, agent_color, project_name, cli,"
                " model, prompt, cwd, status, activity, cols, rows, log_path, created_at,"
                " updated_at, resumed_from_id, usage_baseline) VALUES ('r2', 'default', 'Dev',"
                " '#fff', 'p1', 'claude', '', 'hola', 'C:/p1', 'running', 'idle', 120, 32, '',"
                " :now, :now, 'r1', '{\"offset\": 10}')"
            ),
            {"now": NOW},
        )
        # Deleting the resumed run leaves the resuming one without the link.
        conn.execute(text("DELETE FROM runs WHERE id = 'r1'"))
        assert conn.execute(text("SELECT resumed_from_id FROM runs")).scalar() is None

    command.downgrade(config, "0006")
    with engine.begin() as conn:
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(runs)"))]
        assert "resumed_from_id" not in columns and "log_purged" not in columns
    engine.dispose()
