"""Migration 0008 (phase 10): a database from v1.1 gets one system account per CLI as its default,
the daily limits move to them, the runs and the limit items point to them, and the downgrade
puts everything back."""

import json
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-14 12:00:00.000000"


def _run(conn, run_id: str, cli: str) -> None:
    conn.execute(
        text(
            "INSERT INTO runs (id, workspace_id, agent_name, agent_color, project_name, cli,"
            " model, prompt, cwd, status, activity, cols, rows, log_path, created_at,"
            " updated_at) VALUES (:id, 'default', 'Dev', '#fff', 'p1', :cli, '', 'hola',"
            " 'C:/p1', 'completed', 'idle', 120, 32, '', :now, :now)"
        ),
        {"id": run_id, "cli": cli, "now": NOW},
    )


def _item(conn, item_id: str, kind: str, command_value: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO inbox_items (id, workspace_id, kind, status, agent_name, agent_color,"
            " project_name, project_color, title, detail, command, options, created_at,"
            " updated_at) VALUES (:id, 'default', :kind, 'pending', '', '#fff', '', '#fff', 't',"
            " '', :command, '[]', :now, :now)"
        ),
        {"id": item_id, "kind": kind, "command": command_value, "now": NOW},
    )


def test_system_accounts_limits_runs_and_items(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0007")
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_state (key, value) VALUES ('usage_limits', :value)"),
            {"value": json.dumps({"claude_usd": 25.0, "agy_tokens": 2000000})},
        )
        _run(conn, "r-claude", "claude")
        _run(conn, "r-agy", "agy")
        _item(conn, "i-limit", "limit", "claude")
        _item(conn, "i-quota", "quota", "agy")
        _item(conn, "i-delivery", "delivery", None)

    command.upgrade(config, "0008")
    with engine.begin() as conn:
        accounts = {
            row.cli: row
            for row in conn.execute(
                text(
                    "SELECT id, cli, config_dir, is_default, daily_limit, session_state"
                    " FROM cli_accounts"
                )
            ).fetchall()
        }
        assert set(accounts) == {"claude", "agy"}
        for account in accounts.values():
            assert account.config_dir is None and account.is_default == 1
            assert account.session_state == "unknown"
        assert accounts["claude"].daily_limit == 25.0
        assert accounts["agy"].daily_limit == 2000000

        # The limits left app_state; the runs and the limit items point to the accounts.
        assert conn.execute(text("SELECT count(*) FROM app_state")).scalar() == 0
        runs = dict(conn.execute(text("SELECT id, account_id FROM runs")).fetchall())
        assert runs == {"r-claude": accounts["claude"].id, "r-agy": accounts["agy"].id}
        assert (
            conn.execute(text("SELECT account_label FROM runs WHERE id = 'r-claude'")).scalar()
            == ""
        )
        items = dict(conn.execute(text("SELECT id, command FROM inbox_items")).fetchall())
        assert items == {
            "i-limit": accounts["claude"].id,
            "i-quota": accounts["agy"].id,
            "i-delivery": None,
        }
        # The Inbox takes the new kind; the database keeps one default account per CLI.
        _item(conn, "i-account", "account", accounts["claude"].id)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cli_accounts (id, workspace_id, cli, label, email, plan, is_default,"
                " session_state, quota, created_at, updated_at) VALUES ('x', 'default', 'claude',"
                " 'Otra', '', '', 1, 'ok', '{}', :now, :now)"
            ),
            {"now": NOW},
        )

    command.downgrade(config, "0007")
    with engine.begin() as conn:
        limits = json.loads(conn.execute(text("SELECT value FROM app_state")).scalar())
        assert limits == {"claude_usd": 25.0, "agy_tokens": 2000000}
        items = dict(conn.execute(text("SELECT id, command FROM inbox_items")).fetchall())
        assert items == {"i-limit": "claude", "i-quota": "agy", "i-delivery": None}
        assert "account_id" not in [r[1] for r in conn.execute(text("PRAGMA table_info(runs)"))]
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master"))}
        assert "cli_accounts" not in tables and "teams" not in tables
    engine.dispose()


def test_a_fresh_database_without_limits_has_unlimited_system_accounts(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0007")
    command.upgrade(config, "0008")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT cli, daily_limit FROM cli_accounts")).fetchall()
        assert {r.cli: r.daily_limit for r in rows} == {"claude": None, "agy": None}
    command.downgrade(config, "0007")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM app_state")).scalar() == 0
    engine.dispose()
