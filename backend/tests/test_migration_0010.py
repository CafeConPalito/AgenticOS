"""Migration 0010 (phase 11): runs and tasks get the snapshot columns, empty on existing rows."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-15 12:00:00.000000"


def test_existing_rows_have_no_change_data(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0009")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, agent_name, agent_color, project_name, cli,"
                " model, prompt, cwd, status, activity, cols, rows, log_path, extra_transcripts,"
                " input_tokens, output_tokens, thinking_tokens, cache_read_tokens,"
                " cache_creation_tokens, usage_models, usage_status, log_purged, account_label,"
                " created_at, updated_at)"
                " VALUES ('r1', 'default', 'Dev', '#fff', 'Web', 'claude', '', 'p', 'c',"
                " 'exited', 'idle', 120, 32, '', '[]', 0, 0, 0, 0, 0, '{}', 'pending', 0, '',"
                " :now, :now)"
            ),
            {"now": NOW},
        )
    command.upgrade(config, "0010")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT snapshot_start, snapshot_end, snapshot_skipped, changes_files,"
                " changes_added, changes_deleted FROM runs WHERE id = 'r1'"
            )
        ).one()
        assert tuple(row) == (None, None, 0, None, None, None)
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(tasks)"))]
        assert "base_commit" in columns

    command.downgrade(config, "0009")
    with engine.begin() as conn:
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(runs)"))]
        assert "snapshot_start" not in columns and "changes_files" not in columns
        assert conn.execute(text("SELECT count(*) FROM runs")).scalar() == 1
    engine.dispose()
