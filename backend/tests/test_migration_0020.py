"""Migration 0020 (phase 18, block 1): the catalog of MCP connections, where each is given and
taken away, the OAuth login, the registry origin, what each run received and the calls it made,
and the Inbox kind «connection»."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-24 21:00:00.000000"


def _engine(settings: Settings, revision: str):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, revision)
    return engine, config


def _connection(connection_id: str, name: str = "github", **extra) -> str:
    values = {"transport": "stdio", "auth": "none", "tool_mode": "all", "origin": "user", **extra}
    return (
        "INSERT INTO mcp_connections (id, workspace_id, created_at, updated_at, name, description,"
        " icon, transport, command, args, cwd, url, env, headers, secret_keys, auth, enabled,"
        " tools, resources, prompts, tools_changed, tool_mode, allowed_tools, preapproved_tools,"
        " origin, revision) VALUES"
        f" ('{connection_id}', 'default', '{NOW}', '{NOW}', '{name}', '', '',"
        f" '{values['transport']}', 'npx', '[]', '', '', '{{}}', '{{}}', '[]', '{values['auth']}',"
        f" 1, '[]', '[]', '[]', 0, '{values['tool_mode']}', '[]', '[]', '{values['origin']}', 1)"
    )


def _agent(agent_id: str) -> str:
    return (
        "INSERT INTO agents (id, workspace_id, created_at, updated_at, name, role, description,"
        " color, cli, model, instructions, permission_mode, allowed_tools, max_concurrency,"
        " can_spawn_subagents, can_create_tasks, status, fallback_model) VALUES"
        f" ('{agent_id}', 'default', '{NOW}', '{NOW}', 'Dev', '', '', '#fff', 'claude', '', '',"
        " 'ask', '[]', 1, 0, 0, 'active', '')"
    )


def _assignment(assignment_id: str, connection_id: str, scope: str, project="NULL", agent="NULL"):
    return (
        "INSERT INTO mcp_assignments (id, connection_id, scope, project_id, agent_id, created_at)"
        f" VALUES ('{assignment_id}', '{connection_id}', '{scope}', {project}, {agent}, '{NOW}')"
    )


def test_tables_exist_after_the_upgrade(settings: Settings):
    engine, _ = _engine(settings, "0020")
    tables = set(inspect(engine).get_table_names())
    assert {
        "mcp_connections",
        "mcp_assignments",
        "mcp_exclusions",
        "mcp_oauth",
        "mcp_origins",
        "run_connections",
        "run_tool_calls",
    } <= tables
    assert "connection_id" in {c["name"] for c in inspect(engine).get_columns("inbox_items")}


def test_a_connection_name_is_unique(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_connection("c1")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_connection("c2")))


def test_transport_and_auth_are_closed_lists(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_connection("c1", transport="websocket")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_connection("c2", name="b", auth="password")))


def test_an_assignment_is_unique_per_level_even_for_general(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_connection("c1")))
        db.execute(text(_assignment("x1", "c1", "general")))
        db.execute(text(_assignment("x2", "c1", "agent", agent="'a1'")))  # another level
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_assignment("x3", "c1", "general")))  # NULLs must still clash


def test_the_level_of_an_assignment_must_match_its_ids(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_connection("c1")))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(_assignment("x1", "c1", "project", agent="'a1'")))


def test_an_exclusion_targets_an_agent_or_a_stage_not_both(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_agent("a1")))
        db.execute(text(_connection("c1")))
        db.execute(text("INSERT INTO mcp_exclusions VALUES ('e1', 'c1', 'a1', NULL)"))
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("INSERT INTO mcp_exclusions VALUES ('e2', 'c1', NULL, NULL)"))


def test_deleting_a_connection_removes_what_hangs_from_it(settings: Settings):
    engine, _ = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text(_connection("c1")))
        db.execute(text(_assignment("x1", "c1", "general")))
        db.execute(
            text(
                "INSERT INTO mcp_oauth (connection_id, issuer, client_id, client_pasted,"
                " redirect_uri, scopes, account_label, status, updated_at) VALUES"
                f" ('c1', '', '', 0, '', '', '', 'disconnected', '{NOW}')"
            )
        )
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.execute(text("DELETE FROM mcp_connections WHERE id = 'c1'"))
        assert db.execute(text("SELECT count(*) FROM mcp_assignments")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM mcp_oauth")).scalar() == 0


def test_the_inbox_accepts_the_connection_kind_only_after_the_migration(settings: Settings):
    insert = (
        "INSERT INTO inbox_items (id, workspace_id, created_at, updated_at, kind, status,"
        " agent_name, agent_color, project_name, project_color, title, detail, options)"
        f" VALUES ('i1', 'default', '{NOW}', '{NOW}', 'connection', 'pending', '', '#fff', '',"
        " '#fff', 'Vuelve a conectar', '', '[]')"
    )
    engine, config = _engine(settings, "0019")
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text(insert))
    command.upgrade(config, "0020")
    with engine.begin() as db:
        db.execute(text(insert))


def test_downgrade_removes_everything_new(settings: Settings):
    engine, config = _engine(settings, "0020")
    with engine.begin() as db:
        db.execute(text(_connection("c1")))
    command.downgrade(config, "0019")
    inspector = inspect(engine)
    assert "mcp_connections" not in inspector.get_table_names()
    assert "run_tool_calls" not in inspector.get_table_names()
    assert "connection_id" not in {c["name"] for c in inspector.get_columns("inbox_items")}
