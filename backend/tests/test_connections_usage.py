"""The calls to external servers a run makes (phase 18, block 7): the hook payloads of both CLIs
(shapes from spikes S1 and S2), what is recorded, the run's page data and the usage of a card
(CA11 and CA13)."""

import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from http_server import Running
from live_server import live_server
from test_scheduler_e2e import Api, settings_for

from agentic_os.models import Run, RunToolCall
from agentic_os.services.connections import usage

SERVER = str(Path(__file__).parent / "fixtures" / "mcp_servers" / "stdio_server.py")
KEY = "key-http-5527"


# -- the payloads -------------------------------------------------------------------------------
def claude(tool: str, **extra) -> dict:
    return {"hook_event_name": "x", "tool_name": tool, "tool_use_id": "toolu_1", **extra}


def test_claude_calls_are_read_from_the_tool_name():
    start = usage.parse("claude", "PreToolUse", claude("mcp__github__create_issue", tool_input={}))
    assert (start.phase, start.server, start.tool, start.key) == (
        "start",
        "github",
        "create_issue",
        "toolu_1",
    )
    end = usage.parse("claude", "PostToolUse", claude("mcp__github__create_issue", duration_ms=42))
    assert (end.phase, end.duration_ms) == ("end", 42)
    failed = usage.parse(
        "claude",
        "PostToolUseFailure",
        claude("mcp__github__create_issue", error="boom", duration_ms=7),
    )
    assert (failed.phase, failed.error, failed.duration_ms) == ("fail", "boom", 7)
    # a tool name with underscores in it keeps them
    assert usage.parse("claude", "PreToolUse", claude("mcp__db__run_read_query")).tool == (
        "run_read_query"
    )


@pytest.mark.parametrize(
    "tool", ["Bash", "Skill", "Agent", "mcp__agentic-os__report_status", "mcp__sinherramienta"]
)
def test_other_tools_and_our_own_server_are_not_external_calls(tool):
    assert usage.parse("claude", "PreToolUse", claude(tool)) is None


def agy(server: str, tool: str, **extra) -> dict:
    return {
        "conversationId": "c1",
        "stepIdx": 4,
        "toolCall": {
            "name": "call_mcp_tool",
            "args": {"ServerName": server, "ToolName": tool, "Arguments": {}},
        },
        **extra,
    }


def test_agy_calls_come_with_the_plugins_prefix():
    start = usage.parse("agy", "PreToolUse", agy("agentic-os_github", "create_issue"))
    assert (start.phase, start.server, start.tool, start.key) == (
        "start",
        "github",
        "create_issue",
        "c1:4",
    )
    assert usage.parse("agy", "PostToolUse", agy("agentic-os_github", "x", error="")).phase == "end"
    failed = usage.parse("agy", "PostToolUse", agy("agentic-os_github", "x", error="denied"))
    assert (failed.phase, failed.error) == ("fail", "denied")
    # our own server, and the other tools of agy
    assert usage.parse("agy", "PreToolUse", agy("agentic-os_agentic-os", "report_status")) is None
    other = {"toolCall": {"name": "run_command", "args": {"CommandLine": "dir"}}}
    assert usage.parse("agy", "PreToolUse", other) is None


# -- recording ----------------------------------------------------------------------------------
def _run_with(client: TestClient, tmp_path: Path) -> str:
    """A run row that was given a connection, without starting any CLI."""
    from agentic_os.models import RunConnection

    agent = client.post("/api/agents", json={"name": "Dev"}).json()["id"]
    folder = tmp_path / "web"
    folder.mkdir()
    project = client.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()["id"]
    with client.app.state.sessionmaker() as db:
        run = Run(
            workspace_id="default",
            agent_id=agent,
            project_id=project,
            agent_name="Dev",
            agent_color="#C9D4E8",
            project_name="Web",
            cli="claude",
            model="",
            prompt="x",
            cwd=str(folder),
        )
        db.add(run)
        db.flush()
        db.add(
            RunConnection(run_id=run.id, connection_name="github", status="sent", level="general")
        )
        db.commit()
        return run.id


def test_a_call_is_recorded_from_its_start_to_its_end(client: TestClient, tmp_path: Path):
    run_id = _run_with(client, tmp_path)
    with client.app.state.sessionmaker() as db:
        run = db.get(Run, run_id)
        usage.record(db, run, usage.Call("start", "github", "create_issue", "k1"))
        [row] = db.query(RunToolCall).all()
        assert row.ok is None  # still running
        usage.record(db, run, usage.Call("end", "github", "create_issue", "k1", duration_ms=30))
        db.commit()
        row = db.query(RunToolCall).one()
        assert (row.ok, row.duration_ms, row.error) == (True, 30, "")
    view = client.get(f"/api/runs/{run_id}/connections").json()
    assert view["connections"][0]["status"] == "connected"  # the first call that worked
    assert view["connections"][0]["calls"] == 1


def test_a_failed_call_keeps_its_error_without_secrets_and_does_not_connect(
    client: TestClient, tmp_path: Path
):
    run_id = _run_with(client, tmp_path)
    with client.app.state.sessionmaker() as db:
        run = db.get(Run, run_id)
        usage.record(db, run, usage.Call("start", "github", "x", "k1"))
        usage.record(
            db,
            run,
            usage.Call("fail", "github", "x", "k1", error="401 for token ghp_abcdef123456"),
            frozenset({"ghp_abcdef123456"}),
        )
        db.commit()
    view = client.get(f"/api/runs/{run_id}/connections").json()
    assert view["calls"][0]["ok"] is False and "ghp_abcdef123456" not in view["calls"][0]["error"]
    assert "•••" in view["calls"][0]["error"]
    assert (
        view["connections"][0]["status"] == "sent" and view["connections"][0]["failed_calls"] == 1
    )


def test_an_end_without_its_start_and_a_server_the_run_never_got(
    client: TestClient, tmp_path: Path
):
    run_id = _run_with(client, tmp_path)
    with client.app.state.sessionmaker() as db:
        run = db.get(Run, run_id)
        assert usage.record(db, run, usage.Call("end", "github", "x", "k9")) is True
        assert usage.record(db, run, usage.Call("start", "intruso", "x", "k8")) is False
        db.commit()
        assert [c.connection_name for c in db.query(RunToolCall)] == ["github"]
    assert client.get("/api/runs/nope/connections").status_code == 404


# -- end to end ---------------------------------------------------------------------------------
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_a_real_run_records_its_calls_and_the_card_shows_the_usage(tmp_path: Path, cli: str):
    settings = settings_for(tmp_path)
    folder = tmp_path / f"web-{cli}"
    folder.mkdir()
    with Running(KEY, _free_port()) as http, live_server(settings) as server:
        api = Api(server)
        api.client_put("/api/settings/connections", {"agy_grace": 0})
        project = api.post("/api/projects", {"name": f"Web {cli}", "path": str(folder)})["id"]
        agent = api.post("/api/agents", {"name": f"Dev {cli}", "cli": cli})["id"]
        probe = api.post(
            "/api/connections",
            {
                "name": "probe",
                "command": sys.executable,
                "args": [SERVER],
                "level": {"scope": "general"},
            },
        )[0]
        api.post(
            "/api/connections",
            {
                "name": "web",
                "transport": "http",
                "url": http.url,
                "headers": {"X-Probe-Key": "${secret:KEY}"},
                "secrets": {"KEY": KEY},
                "level": {"scope": "general"},
            },
        )
        title = (
            "Usar conexiones; CONEXION: probe|read_note|topic=a|a.txt; "
            "CONEXION: web|ping|text=hola|b.txt; CONEXION: probe|write_note|topic=a|c.txt; "
            "TERMINA: hecho"  # write_note without its `text`: the server answers with an error
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        run_id = api.wait_status(task["id"], "done")["last_run_id"]

        view = api.get(f"/api/runs/{run_id}/connections")
        calls = [(c["connection"], c["tool"], c["ok"]) for c in view["calls"]]
        assert calls == [
            ("probe", "read_note", True),
            ("web", "ping", True),
            ("probe", "write_note", False),
        ]
        assert all(c["duration_ms"] is not None for c in view["calls"])
        assert "validation error" in view["calls"][2]["error"] or view["calls"][2]["error"]
        by_name = {c["name"]: c for c in view["connections"]}
        assert by_name["probe"]["status"] == "connected" and by_name["probe"]["calls"] == 2
        assert by_name["probe"]["failed_calls"] == 1 and by_name["web"]["failed_calls"] == 0

        # the usage on the card
        card = next(c for c in api.get("/api/connections") if c["name"] == "probe")
        assert card["usage"]["used_runs"] == 1 and card["usage"]["calls"] == 2
        assert card["usage"]["failed_calls"] == 1 and card["usage"]["last_used"]

        # and it survives the connection (the name is copied)
        import httpx

        assert httpx.delete(f"{api.url}/api/connections/{probe['id']}").status_code == 204
        again = api.get(f"/api/runs/{run_id}/connections")
        assert [c["connection"] for c in again["calls"]].count("probe") == 2
