"""Migration 0004: the project memory text becomes a list of notes (and back on downgrade)."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

# What phase 04 left in a project: user text plus blocks appended by write_project_memory.
OLD_MEMORY = (
    "# Convenciones\nUsa pnpm.\n\n"
    "### 2026-10-10 18:05 · Dev\nEl login usa PKCE.\n\n"
    "### 2026-10-10 19:40 · Gema\nLos tests e2e van en /e2e.\nDos líneas."
)
NOW = "2026-10-10 12:00:00.000000"


def test_memory_becomes_notes_and_back(settings: Settings, tmp_path: Path):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0003")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agents (id, workspace_id, name, role, description, color, cli,"
                " model, instructions, permission_mode, allowed_tools, max_concurrency,"
                " can_spawn_subagents, can_create_tasks, status, created_at, updated_at)"
                " VALUES ('a1', 'default', 'Dev', '', '', '#fff', 'claude', '', '', 'ask', '[]',"
                " 1, 0, 0, 'active', :now, :now)"
            ),
            {"now": NOW},
        )
        for pid, memory in (("p1", OLD_MEMORY), ("p2", "")):
            conn.execute(
                text(
                    "INSERT INTO projects (id, workspace_id, name, color, description, path,"
                    " path_key, workspace_mode, memory, created_at, updated_at)"
                    " VALUES (:id, 'default', :id, '#fff', '', :id, :id, 'direct', :memory,"
                    " :now, :now)"
                ),
                {"id": pid, "memory": memory, "now": NOW},
            )
        conn.execute(
            text(
                "INSERT INTO runs (id, workspace_id, agent_id, project_id, agent_name,"
                " agent_color, project_name, cli, model, prompt, cwd, status, activity, cols,"
                " rows, log_path, created_at, updated_at) VALUES ('r1', 'default', 'a1', 'p1',"
                " 'Dev', '#fff', 'p1', 'claude', '', 'hola', 'p1', 'completed', 'idle', 120, 32,"
                " '', :now, :now)"
            ),
            {"now": NOW},
        )
        conn.execute(
            text(
                "INSERT INTO run_events (id, run_id, at, kind, name, detail)"
                " VALUES ('e1', 'r1', :now, 'mcp', 'complete_task', 'hecho')"
            ),
            {"now": NOW},
        )

    command.upgrade(config, "0004")
    with engine.connect() as conn:
        # Rebuilding projects and runs (SQLite batch mode) must not fire their ON DELETE actions.
        assert conn.execute(text("SELECT project_id FROM runs")).scalar() == "p1"
        assert conn.execute(text("SELECT count(*) FROM run_events")).scalar() == 1
    with engine.connect() as conn:
        notes = conn.execute(
            text(
                "SELECT project_id, author_kind, author_name, agent_id, text FROM memory_notes"
                " ORDER BY created_at"
            )
        ).all()
    # The user's text has no date: it keeps its place, before the oldest agent note.
    assert notes == [
        ("p1", "user", "", None, "# Convenciones\nUsa pnpm."),
        ("p1", "agent", "Dev", "a1", "El login usa PKCE."),
        ("p1", "agent", "Gema", None, "Los tests e2e van en /e2e.\nDos líneas."),
    ]

    command.downgrade(config, "0003")
    with engine.connect() as conn:
        memories = dict(conn.execute(text("SELECT id, memory FROM projects")).all())
    assert memories["p2"] == ""
    restored = memories["p1"]
    assert "### 2026-10-10 18:05 · Dev\nEl login usa PKCE." in restored
    assert "### 2026-10-10 19:40 · Gema\nLos tests e2e van en /e2e.\nDos líneas." in restored
    assert "# Convenciones\nUsa pnpm." in restored
    engine.dispose()
