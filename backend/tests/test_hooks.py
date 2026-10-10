"""CLI hooks: the per-run hook script (real curl.exe) and how events are interpreted."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server

from agentic_os.config import Settings
from agentic_os.models import Activity, Cli, Run, RunEvent
from agentic_os.services.hooks import interpret, write_hook_script

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="hook.cmd is Windows-only")


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def seed_run(server: LiveServer, cli: str) -> tuple[str, str]:
    with server.db() as db:
        run = Run(
            agent_name="Dev",
            agent_color="#4FD1C5",
            project_name="Web",
            cli=cli,
            prompt="x",
            cwd=".",
            cli_session_id=None,
        )
        db.add(run)
        db.commit()
        run_id = run.id
    return run_id, server.manager.tokens.issue(run_id)


def run_hook(command: str, event: str, payload: object) -> subprocess.CompletedProcess:
    """Runs the hook the way agy does: through cmd.exe, unquoted, JSON on stdin."""
    return subprocess.run(
        ["cmd.exe", "/c", f"{command} {event}"],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=20,
    )


def hook_events(server: LiveServer, run_id: str) -> list[str]:
    with server.db() as db:
        return [e.name for e in db.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.at)]


def test_hook_script_reaches_the_backend_from_a_folder_with_spaces(
    server: LiveServer, tmp_path: Path
):
    run_id, token = seed_run(server, "agy")
    command = write_hook_script(tmp_path / "datos con espacio" / run_id, server.url, token)
    assert " " not in command and '"' not in command  # agy breaks quoted paths

    payload = {"conversationId": "3cc6af35-cc8f-4ca0-ae13-66f4b88ea9ee"}
    assert run_hook(command, "Stop", payload).returncode == 0
    with server.db() as db:
        assert db.get(Run, run_id).cli_session_id == payload["conversationId"]
    assert hook_events(server, run_id) == ["Stop"]


def test_hook_never_fails_even_with_the_backend_down(tmp_path: Path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # nothing listens there
    command = write_hook_script(tmp_path / "run", f"http://127.0.0.1:{port}", "t" * 40)
    started = time.monotonic()
    result = run_hook(command, "Stop", {"x": 1})
    assert result.returncode == 0  # a failing hook would block the tool call in agy
    assert time.monotonic() - started < 6


def test_hook_endpoint_rejects_unknown_tokens_and_tolerates_bad_bodies(server: LiveServer):
    run_id, token = seed_run(server, "claude")
    assert httpx.post(f"{server.url}/r/{'z' * 40}/hook/Stop", content=b"{}").status_code == 401
    assert httpx.post(f"{server.url}/r/{token}/hook/Stop", content=b"no json").status_code == 204
    odd = httpx.post(f"{server.url}/r/{token}/hook/../x", content=b"{}")
    assert 400 <= odd.status_code < 500  # never reaches a handler
    assert hook_events(server, run_id) == ["Stop"]


def test_interpretation_per_cli():
    assert interpret(Cli.CLAUDE, "UserPromptSubmit", {}).activity == Activity.BUSY
    stop = interpret(Cli.CLAUDE, "Stop", {"session_id": "abc"})
    assert (stop.activity, stop.turn_ended, stop.session_id) == (Activity.IDLE, True, None)
    pre = interpret(Cli.AGY, "PreInvocation", {"conversationId": "c1"})
    assert (pre.activity, pre.turn_started, pre.session_id) == (Activity.BUSY, True, "c1")
    other = interpret(Cli.CLAUDE, "SessionStart", None)
    assert other.activity is None and not other.turn_started and not other.turn_ended
