"""Runs end to end with the agentic-os MCP server and the CLI hooks (phase 04).

A real backend (the fake CLI must reach it over HTTP) and the fake CLI in a real ConPTY: the
fake uses the run files / workspace plugin exactly like Claude Code / agy, runs the hook
scripts (hook.cmd + curl) and talks to the MCP server with the official client.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from websockets.sync.client import connect

from agentic_os.config import Settings

FAKE = str(Path(__file__).with_name("fake_cli.py"))
ACTIVE = ("starting", "running", "intervening")


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    command = [sys.executable, FAKE]
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        cli_command_overrides={"claude": command, "agy": command},
    )
    with live_server(settings) as live:
        yield live


class Viewer:
    def __init__(self, server: LiveServer, run_id: str) -> None:
        url = server.url.replace("http", "ws") + f"/api/runs/{run_id}/terminal?client_id=v"
        self.ws = connect(url, open_timeout=10)
        self.messages: list[dict] = []
        self.text = ""
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        try:
            while True:
                message = json.loads(self.ws.recv())
                self.messages.append(message)
                if message["type"] in ("snapshot", "output"):
                    self.text += message["data"]
        except Exception:
            return

    def events(self) -> list[str]:
        return [m["name"] for m in self.messages if m["type"] == "event"]

    def close(self) -> None:
        self.ws.close()


def seed(server: LiveServer, folder: Path, cli: str, mode: str = "ask") -> tuple[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    agent = httpx.post(
        f"{server.url}/api/agents",
        json={"name": "Dev", "role": "Desarrollador", "cli": cli, "permission_mode": mode},
    ).json()
    project = httpx.post(
        f"{server.url}/api/projects", json={"name": "Web", "path": str(folder)}
    ).json()
    return agent["id"], project["id"]


def launch(server: LiveServer, agent_id: str, project_id: str, prompt: str) -> httpx.Response:
    return httpx.post(
        f"{server.url}/api/runs",
        json={"agent_id": agent_id, "project_id": project_id, "prompt": prompt},
        timeout=30,
    )


def run(server: LiveServer, run_id: str) -> dict:
    return httpx.get(f"{server.url}/api/runs/{run_id}").json()


def wait_until(check: Callable[[], bool], timeout: float = 40) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.2)
    return False


def wait_ended(server: LiveServer, run_id: str, timeout: float = 60) -> dict:
    assert wait_until(lambda: run(server, run_id)["status"] not in ACTIVE, timeout), run(
        server, run_id
    )
    return run(server, run_id)


TASK = "hola; ESTADO: leyendo el login; MEMORIA: el login usa PKCE; TERMINA: login arreglado"


def test_claude_reports_completes_and_closes_by_itself(server: LiveServer, tmp_path: Path):
    agent_id, project_id = seed(server, tmp_path / "web", "claude")
    started = launch(server, agent_id, project_id, TASK).json()
    viewer = Viewer(server, started["id"])
    try:
        ended = wait_ended(server, started["id"])
        assert ended["status"] == "completed"
        assert ended["exit_code"] == 0  # closed with /exit after the turn, not killed
        assert ended["summary"] == "login arreglado"
        assert ended["last_status"] == "leyendo el login"
        assert ended["mcp_connected_at"]

        names = [
            e["name"] for e in httpx.get(f"{server.url}/api/runs/{started['id']}/events").json()
        ]
        for expected in (
            "SessionStart",
            "UserPromptSubmit",
            "mcp_connected",
            "report_status",
            "write_project_memory",
            "complete_task",
            "Stop",
            "closing",
        ):
            assert expected in names, names
        assert names.index("complete_task") < names.index("closing")
        assert "complete_task" in viewer.events()  # pushed live to the viewers

        memory = httpx.get(f"{server.url}/api/projects/{project_id}").json()["memory"]
        assert memory.endswith("· Dev\nel login usa PKCE")
    finally:
        viewer.close()
    # The token died with the run.
    token_url = json.loads(
        (server.manager.runs_dir / started["id"] / "mcp.json").read_text("utf-8")
    )["mcpServers"]["agentic-os"]
    bearer = token_url["headers"]
    assert httpx.post(f"{server.url}/r/mcp", json={}, headers=bearer).status_code == 401


def test_agy_gets_its_prompt_after_mcp_and_our_dialogs_are_approved(
    server: LiveServer, tmp_path: Path
):
    folder = tmp_path / "web"
    (folder / ".git" / "info").mkdir(parents=True)
    agent_id, project_id = seed(server, folder, "agy")
    started = launch(server, agent_id, project_id, TASK).json()
    assert started["cli_session_id"] is None
    plugin = folder / ".agents" / "plugins" / "agentic-os"
    assert plugin.is_dir()
    viewer = Viewer(server, started["id"])
    try:
        ended = wait_ended(server, started["id"], timeout=90)
        assert ended["status"] == "completed", viewer.text[-2000:]
        assert ended["summary"] == "login arreglado"
        assert ended["cli_session_id"]  # agy's conversationId, from the hooks
        names = [
            e["name"] for e in httpx.get(f"{server.url}/api/runs/{started['id']}/events").json()
        ]
        assert names.index("mcp_connected") < names.index("prompt_sent")
        assert "mcp_timeout" not in names
        assert names.count("PreInvocation") == 1  # turn boundaries only
        # Each of our tools asked once and was approved "for the conversation".
        # (each dialog is drawn twice: when it opens and after moving to option 2)
        assert viewer.text.count("Allow calling this tool?") == 2 * 3
        assert "(denied" not in viewer.text
    finally:
        viewer.close()
    assert not (folder / ".agents").exists()  # the plugin is gone
    exclude = (folder / ".git" / "info" / "exclude").read_text("utf-8")
    assert ".agents/plugins/agentic-os/" in exclude


def test_one_agy_run_per_folder(server: LiveServer, tmp_path: Path):
    agent_id, project_id = seed(server, tmp_path / "web", "agy")
    first = launch(server, agent_id, project_id, "hola").json()
    try:
        second = launch(server, agent_id, project_id, "otra")
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "agy_folder_busy"
    finally:
        httpx.post(f"{server.url}/api/runs/{first['id']}/stop")
        wait_ended(server, first["id"])
    assert launch(server, agent_id, project_id, "ahora sí").status_code == 201


def test_recover_removes_a_plugin_left_by_a_crash(tmp_path: Path):
    folder = tmp_path / "web"
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        cli_command_overrides={"agy": [sys.executable, FAKE]},
    )
    with live_server(settings) as live:
        agent_id, project_id = seed(live, folder, "agy")
        started = launch(live, agent_id, project_id, "hola").json()
        assert (folder / ".agents" / "plugins" / "agentic-os").is_dir()
        live.manager.on_end_disabled = True
        # Simulate a crash: the process dies but nobody cleans up.
        session = live.manager.get(started["id"])
        session.on_end = None
        session.kill()
        assert wait_until(lambda: not session.alive)
        assert (folder / ".agents" / "plugins" / "agentic-os").is_dir()
        with live.db() as db:  # as if the backend had died with the run active
            from agentic_os.models import Run

            db.get(Run, started["id"]).status = "running"
            db.commit()
    with live_server(settings) as again:
        assert run(again, started["id"])["status"] == "interrupted"
    assert not (folder / ".agents").exists()
