"""How each CLI is given the run's external MCP servers (phase 18, block 5): the files and flags
of the adapters, what is skipped and why (CA12), and that nothing outside the run changes (CA10)."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_adapters import allowed, context, option

from agentic_os.models import Cli, McpOAuth, PermissionMode
from agentic_os.services.adapters import adapter_for
from agentic_os.services.adapters.agy import plugin_dir
from agentic_os.services.connections import oauth, runtime, secrets
from agentic_os.services.runs import launcher


@pytest.fixture(autouse=True)
def fake_which(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: f"C:/bin/{name}.exe")


def _make(client: TestClient, name: str, **extra) -> dict:
    payload = {"name": name, "command": "npx", "args": ["-y", name], **extra}
    payload.setdefault("level", {"scope": "general"})
    response = client.post("/api/connections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()[0]


def _prepare(client: TestClient, cli: Cli, agent=None, project=None, stage=None):
    with client.app.state.sessionmaker() as db:
        return runtime.prepare(db, cli.value, agent, project, stage)


def _with_tools(client: TestClient, connection_id: str, names: list[str]) -> None:
    from agentic_os.models import McpConnection

    with client.app.state.sessionmaker() as db:
        row = db.get(McpConnection, connection_id)
        row.tools = [{"name": n, "description": n, "input_schema": {}} for n in names]
        db.commit()


# -- Claude -------------------------------------------------------------------------------------
def test_claude_gets_the_servers_in_mcp_json_and_the_secrets_as_variables(
    client: TestClient, tmp_path: Path
):
    _make(
        client,
        "github",
        transport="http",
        command="",
        args=[],
        url="https://gh.example.test/mcp",
        headers={"Authorization": "Bearer ${secret:TOKEN}"},
        secrets={"TOKEN": "ghp_the_real_token"},
    )
    _make(
        client, "db", env={"PASSWORD": "${secret:PW}", "MODE": "ro"}, secrets={"PW": "pw-12345678"}
    )
    prepared = _prepare(client, Cli.CLAUDE)
    ctx = replace(context(tmp_path, Cli.CLAUDE), connections=prepared)
    spec = adapter_for(Cli.CLAUDE).prepare(ctx)

    mcp = json.loads((ctx.run_dir / "mcp.json").read_text("utf-8"))["mcpServers"]
    assert set(mcp) == {"agentic-os", "db", "github"}
    assert mcp["db"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "db"],
        "env": {"PASSWORD": "${AOS_MCP_1_PW}", "MODE": "ro"},
    }
    assert mcp["github"]["headers"] == {"Authorization": "Bearer ${AOS_MCP_2_TOKEN}"}
    assert mcp["github"]["type"] == "http"
    # the values are in the process environment and nowhere in the files
    assert spec.env["AOS_MCP_1_PW"] == "pw-12345678"
    assert spec.env["AOS_MCP_2_TOKEN"] == "ghp_the_real_token"
    assert spec.env["MCP_TIMEOUT"] == "60000"
    for file in ctx.run_dir.rglob("*"):
        if file.is_file():
            assert "pw-12345678" not in file.read_text("utf-8") and "ghp_the_real" not in (
                file.read_text("utf-8")
            )
    assert prepared.secret_values == {"pw-12345678", "ghp_the_real_token"}


def test_claude_takes_away_the_tools_that_are_not_allowed_in_every_mode(
    client: TestClient, tmp_path: Path
):
    made = _make(client, "db")
    _with_tools(client, made["id"], ["read", "write", "drop"])
    client.patch(
        f"/api/connections/{made['id']}",
        json={
            "tool_mode": "selected",
            "allowed_tools": ["read", "write"],
            "preapproved_tools": ["read"],
        },
    )
    prepared = _prepare(client, Cli.CLAUDE)
    assert prepared.deny == ["mcp__db__drop"] and prepared.allow == ["mcp__db__read"]
    for mode in PermissionMode:
        ctx = replace(context(tmp_path, Cli.CLAUDE, mode=mode), connections=prepared)
        argv = adapter_for(Cli.CLAUDE).prepare(ctx).argv
        assert option(argv, "--disallowedTools") == "mcp__db__drop", mode
        if mode == PermissionMode.AUTONOMOUS:
            assert "mcp__db__read" not in argv  # bypassPermissions: everything is allowed anyway
        else:
            assert "mcp__db__read" in allowed(argv) and "mcp__db__write" not in allowed(argv)


def test_without_connections_the_claude_flags_do_not_change(tmp_path: Path):
    plain = adapter_for(Cli.CLAUDE).prepare(context(tmp_path, Cli.CLAUDE)).argv
    empty = adapter_for(Cli.CLAUDE).prepare(
        replace(
            context(tmp_path, Cli.CLAUDE, run_id="r2"), connections=runtime.RunConnections("claude")
        )
    )
    assert "--disallowedTools" not in plain and "--disallowedTools" not in empty.argv
    assert "MCP_TIMEOUT" not in empty.env


# -- agy ----------------------------------------------------------------------------------------
def test_agy_gets_the_servers_in_its_plugin_with_the_values_in_clear(
    client: TestClient, tmp_path: Path
):
    _make(client, "db", env={"PASSWORD": "${secret:PW}"}, secrets={"PW": "pw-12345678"})
    made = _make(
        client, "web", transport="http", command="", args=[], url="https://w.example.test/mcp"
    )
    _with_tools(client, made["id"], ["a", "b"])
    client.patch(
        f"/api/connections/{made['id']}", json={"tool_mode": "selected", "allowed_tools": ["a"]}
    )
    prepared = _prepare(client, Cli.AGY)
    ctx = replace(context(tmp_path, Cli.AGY), connections=prepared)
    adapter_for(Cli.AGY).prepare(ctx)
    config = json.loads((plugin_dir(ctx.cwd) / "mcp_config.json").read_text("utf-8"))["mcpServers"]
    assert set(config) == {"agentic-os", "db", "web"}
    assert config["db"] == {
        "command": "npx",
        "args": ["-y", "db"],
        "env": {"PASSWORD": "pw-12345678"},
    }
    assert config["web"] == {"url": "https://w.example.test/mcp", "enabledTools": ["a"]}
    assert config["agentic-os"] == {"url": ctx.mcp_url}
    # and it goes away with the run
    adapter_for(Cli.AGY).cleanup(ctx)
    assert not plugin_dir(ctx.cwd).exists()


def test_agy_skips_sse_connections_and_claude_does_not(client: TestClient):
    _make(
        client, "legacy", transport="sse", command="", args=[], url="https://old.example.test/sse"
    )
    agy = _prepare(client, Cli.AGY)
    assert [(i.name, i.status) for i in agy.items] == [("legacy", "skipped")]
    assert "SSE" in agy.items[0].detail and not agy
    claude = _prepare(client, Cli.CLAUDE)
    assert claude.sent[0].entry["type"] == "sse"


# -- what is skipped ----------------------------------------------------------------------------
def test_a_missing_secret_or_an_untested_selection_skips_only_that_connection(client: TestClient):
    _make(client, "sinclave", env={"T": "${secret:TOKEN}"})
    chosen = _make(client, "elegida")
    client.patch(
        f"/api/connections/{chosen['id']}", json={"tool_mode": "selected", "allowed_tools": ["x"]}
    )
    _make(client, "buena")
    prepared = _prepare(client, Cli.CLAUDE)
    by_name = {i.name: i for i in prepared.items}
    assert by_name["buena"].sent
    assert (
        by_name["sinclave"].status == "skipped"
        and "Falta el secreto «TOKEN»" in by_name["sinclave"].detail
    )
    assert (
        by_name["elegida"].status == "skipped" and "Prueba la conexión" in by_name["elegida"].detail
    )
    assert list(prepared.servers) == ["buena"]


def test_oauth_connections_need_a_login(client: TestClient):
    made = _make(
        client,
        "linear",
        transport="http",
        command="",
        args=[],
        url="https://l.example.test/mcp",
        auth="oauth",
    )
    first = _prepare(client, Cli.CLAUDE).items[0]
    assert first.status == "skipped" and "Conecta la cuenta" in first.detail
    with client.app.state.sessionmaker() as db:
        db.add(McpOAuth(connection_id=made["id"], status="needs_reauth"))
        db.commit()
    assert "volver a conectar" in _prepare(client, Cli.CLAUDE).items[0].detail
    with client.app.state.sessionmaker() as db:
        db.get(McpOAuth, made["id"]).status = "connected"
        db.commit()
    secrets.put(
        made["id"],
        oauth.TOKENS_KEY,
        json.dumps({"access_token": "at-secret-token-1", "refresh_token": "rt-1"}),
    )
    sent = _prepare(client, Cli.CLAUDE)
    assert sent.items[0].sent
    assert sent.items[0].entry["headers"] == {"Authorization": "Bearer ${AOS_MCP_1_OAUTH_TOKEN}"}
    assert sent.env == {"AOS_MCP_1_OAUTH_TOKEN": "at-secret-token-1"}  # never the refresh token
    assert "at-secret-token-1" in sent.secret_values
    agy = _prepare(client, Cli.AGY)
    assert agy.items[0].entry["headers"] == {"Authorization": "Bearer at-secret-token-1"}


# -- the instructions ---------------------------------------------------------------------------
def test_the_instructions_name_the_connections_and_what_is_missing(client: TestClient):
    _make(client, "buena")
    _make(client, "sinclave", env={"T": "${secret:TOKEN}"})
    text = runtime.section(_prepare(client, Cli.CLAUDE))
    assert text.startswith("## Conexiones MCP") and "`buena`" in text
    assert "mcp__<servidor>__<herramienta>" in text and "no investigues el equipo" in text
    assert "`sinclave` (Falta el secreto «TOKEN»" in text
    assert "agentic-os_<servidor>" in runtime.section(_prepare(client, Cli.AGY))
    assert runtime.section(None) == "" and runtime.section(runtime.RunConnections("claude")) == ""


# -- CA10 ---------------------------------------------------------------------------------------
def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_nothing_outside_the_run_changes(client: TestClient, tmp_path: Path, monkeypatch):
    """The CLIs' own folders (a fake home) are the same before and after preparing and cleaning
    a run with connections, for both CLIs."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"model": "x"}', "utf-8")
    (home / ".claude.json").write_text('{"mcpServers": {"mio": {"command": "y"}}}', "utf-8")
    (home / ".gemini" / "config").mkdir(parents=True)
    (home / ".gemini" / "config" / "mcp_config.json").write_text('{"mcpServers": {}}', "utf-8")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    _make(client, "db", env={"T": "${secret:T}"}, secrets={"T": "value-12345678"})
    before = _tree(home)
    for cli in (Cli.CLAUDE, Cli.AGY):
        ctx = replace(
            context(tmp_path, cli, run_id=f"run-{cli.value}"), connections=_prepare(client, cli)
        )
        adapter_for(cli).prepare(ctx)
        adapter_for(cli).cleanup(ctx)
    assert _tree(home) == before
    assert not plugin_dir(tmp_path / "proyecto").exists()
    _ = sys  # the probes of the other tests use it
