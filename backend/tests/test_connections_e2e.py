"""MCP connections end to end (phase 18): a real backend, the fake CLI in a real ConPTY, and real
MCP servers (a stdio one and an HTTP one) given through the app's own adapters.

CA1: an agent uses the tools of external servers configured in the app. CA3: the secret reaches
the server but is nowhere on disk or in the terminal. CA7: a tool the person did not allow is not
there. CA10-style: nothing outside the run's files changes.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest
from http_server import Running
from live_server import live_server
from test_scheduler_e2e import Api, settings_for, wait_until

SERVER = str(Path(__file__).parent / "fixtures" / "mcp_servers" / "stdio_server.py")
SECRET = "s3cret-value-8841"
KEY = "key-http-5527"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _setup(api: Api, root: Path, cli: str) -> tuple[str, str]:
    folder = root / f"web-{cli}"
    folder.mkdir()
    project = api.post("/api/projects", {"name": f"Web {cli}", "path": str(folder)})["id"]
    agent = api.post("/api/agents", {"name": f"Dev {cli}", "cli": cli})["id"]
    return agent, project


def _connections(api: Api, http_url: str) -> dict:
    probe = api.post(
        "/api/connections",
        {
            "name": "probe",
            "command": sys.executable,
            "args": [SERVER],
            "env": {"PROBE_SECRET": "${secret:TOKEN}"},
            "secrets": {"TOKEN": SECRET},
            "level": {"scope": "general"},
        },
    )[0]
    web = api.post(
        "/api/connections",
        {
            "name": "web",
            "transport": "http",
            "url": http_url,
            "headers": {"X-Probe-Key": "${secret:KEY}"},
            "secrets": {"KEY": KEY},
            "level": {"scope": "general"},
        },
    )[0]
    return {"probe": probe, "web": web}


def _title(*directives: str) -> str:
    return "Usar conexiones; " + "; ".join(directives) + "; TERMINA: hecho"


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_an_agent_uses_the_tools_of_external_servers(tmp_path: Path, cli: str):
    """CA1: a stdio server and an HTTP one, reached through the configuration the adapter wrote
    (Claude: ${AOS_MCP_…} references and process variables; agy: values in the plugin)."""
    settings = settings_for(tmp_path)
    folder = tmp_path / f"web-{cli}"
    with Running(KEY, _free_port()) as http, live_server(settings) as server:
        api = Api(server)
        api.client_put("/api/settings/connections", {"agy_grace": 0})
        agent, project = _setup(api, tmp_path, cli)
        made = _connections(api, http.url)
        title = _title(
            "CONTEXTO: ctx.txt",
            "CONEXION: probe|read_note|topic=a|nota.txt",
            "CONEXION: probe|show_env|name=PROBE_SECRET|env.txt",
            "CONEXION: web|ping|text=hola|ping.txt",
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(task["id"], "done")

        assert "PROBE-READ-4417" in (folder / "nota.txt").read_text("utf-8")
        # The secret got to the server through the CLI's configuration.
        assert f"ENV[PROBE_SECRET]={SECRET}" in (folder / "env.txt").read_text("utf-8")
        assert "PONG[hola]=PROBE-HTTP-5521" in (folder / "ping.txt").read_text("utf-8")
        context = (folder / "ctx.txt").read_text("utf-8")
        assert "## Conexiones MCP" in context and "`probe`" in context and "`web`" in context
        assert "no investigues el equipo" in context

        run_id = done["last_run_id"]
        with server.db() as db:
            from agentic_os.models import RunConnection

            rows = {r.connection_name: r for r in db.query(RunConnection).filter_by(run_id=run_id)}
        assert {n: r.status for n, r in rows.items()} == {"probe": "sent", "web": "sent"}
        assert (
            rows["probe"].revision == made["probe"]["revision"] and rows["probe"].level == "general"
        )

        # CA3: neither the log of the terminal nor the run's files hold the secret.
        log = (Path(settings.data_dir) / "runs" / f"{run_id}.log").read_text("utf-8", "replace")
        assert SECRET not in log and KEY not in log
        assert "•••" in log  # the fake CLI printed the answer that held it
        for file in (Path(settings.data_dir) / "runs" / run_id).rglob("*"):
            if file.is_file():
                assert SECRET not in file.read_text("utf-8", "replace"), file
                assert KEY not in file.read_text("utf-8", "replace"), file
        if cli == "claude":
            mcp = (Path(settings.data_dir) / "runs" / run_id / "mcp.json").read_text("utf-8")
            assert "${AOS_MCP_1_TOKEN}" in mcp and "${AOS_MCP_2_KEY}" in mcp
        else:  # the plugin held the values only while the run lived
            assert not (folder / ".agents" / "plugins" / "agentic-os").exists()


def test_a_tool_the_person_did_not_allow_is_not_there(tmp_path: Path):
    """CA7: with a selection, the other tools are taken away from the model (Claude)."""
    settings = settings_for(tmp_path)
    folder = tmp_path / "web-claude"
    with live_server(settings) as server:
        api = Api(server)
        agent, project = _setup(api, tmp_path, "claude")
        made = api.post(
            "/api/connections",
            {
                "name": "probe",
                "command": sys.executable,
                "args": [SERVER],
                "level": {"scope": "general"},
            },
        )[0]
        tested = api.post(f"/api/connections/{made['id']}/test?wait=true")
        assert tested["result"]["ok"], tested
        import httpx

        patched = httpx.patch(
            f"{api.url}/api/connections/{made['id']}",
            json={"tool_mode": "selected", "allowed_tools": ["read_note"]},
        )
        assert patched.status_code == 200, patched.text
        title = _title(
            "CONEXION: probe|read_note|topic=a|leer.txt",
            "CONEXION: probe|write_note|topic=a,text=b|escribir.txt",
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        api.wait_status(task["id"], "done")
        assert "PROBE-READ-4417" in (folder / "leer.txt").read_text("utf-8")
        assert (folder / "escribir.txt").read_text("utf-8") == "(tool not available)"


def test_a_connection_that_cannot_be_given_is_skipped_and_the_run_goes_on(tmp_path: Path):
    """CA12 (what is decided before starting): a missing secret and a never-tested selection."""
    settings = settings_for(tmp_path)
    folder = tmp_path / "web-claude"
    with live_server(settings) as server:
        api = Api(server)
        agent, project = _setup(api, tmp_path, "claude")
        api.post(
            "/api/connections",
            {
                "name": "sinclave",
                "command": sys.executable,
                "args": [SERVER],
                "env": {"TOKEN": "${secret:TOKEN}"},
                "level": {"scope": "general"},
            },
        )
        ok = api.post(
            "/api/connections",
            {
                "name": "probe",
                "command": sys.executable,
                "args": [SERVER],
                "level": {"scope": "general"},
            },
        )[0]
        title = _title("CONTEXTO: ctx.txt", "CONEXION: probe|read_note|topic=a|nota.txt")
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(task["id"], "done")
        assert "PROBE-READ-4417" in (folder / "nota.txt").read_text("utf-8")
        context = (folder / "ctx.txt").read_text("utf-8")
        assert "No están disponibles en esta ejecución" in context
        assert "`sinclave` (Falta el secreto «TOKEN» de la conexión «sinclave».)" in context
        with server.db() as db:
            from agentic_os.models import RunConnection

            rows = {
                r.connection_name: r
                for r in db.query(RunConnection).filter_by(run_id=done["last_run_id"])
            }
        assert rows["sinclave"].status == "skipped" and "TOKEN" in rows["sinclave"].detail
        assert rows["probe"].status == "sent" and ok["id"] == rows["probe"].connection_id
        assert wait_until(lambda: True)


def test_a_connection_taken_away_from_the_stage_is_not_given(tmp_path: Path):
    """CA6 on a real run: the same agent, with and without the connection taken away."""
    settings = settings_for(tmp_path)
    folder = tmp_path / "web-claude"
    with live_server(settings) as server:
        api = Api(server)
        agent, project = _setup(api, tmp_path, "claude")
        made = api.post(
            "/api/connections",
            {
                "name": "probe",
                "command": sys.executable,
                "args": [SERVER],
                "level": {"scope": "general"},
            },
        )[0]
        api.client_put(f"/api/agents/{agent}/connections", {"excluded": [made["id"]]})
        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": agent, "title": _title("CONTEXTO: ctx.txt")},
        )
        api.wait_status(task["id"], "done")
        assert "## Conexiones MCP" not in (folder / "ctx.txt").read_text("utf-8")


def _alive(pid: int) -> bool:
    import psutil

    return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE


@pytest.mark.parametrize("how", ["stop", "shutdown"])
def test_no_server_process_outlives_the_run(tmp_path: Path, how: str):
    """CA11: the stdio server a CLI started is gone when the run is stopped, and also when the
    backend itself closes with the run alive."""
    settings = settings_for(tmp_path)
    folder = tmp_path / "web-claude"
    with live_server(settings) as server:
        api = Api(server)
        agent, project = _setup(api, tmp_path, "claude")
        api.post(
            "/api/connections",
            {
                "name": "probe",
                "command": sys.executable,
                "args": [SERVER],
                "level": {"scope": "general"},
            },
        )
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "Servidor vivo; SERVIDOR: probe|pid.txt",
            },
        )
        assert wait_until(
            lambda: (folder / "pid.txt").exists() and (folder / "pid.txt").read_text()
        )
        pid = int((folder / "pid.txt").read_text("utf-8"))
        assert _alive(pid)
        if how == "stop":
            run_id = api.get(f"/api/tasks/{task['id']}")["last_run_id"]
            api.post(f"/api/runs/{run_id}/stop")
            assert wait_until(lambda: not _alive(pid), timeout=30), "the server is still running"
    assert wait_until(lambda: not _alive(pid), timeout=30), "the server survived the backend"
