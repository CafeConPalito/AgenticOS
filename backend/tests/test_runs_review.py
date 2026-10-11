"""Phase 04 code review: control vs. completion, final status, event errors, agy folders."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from test_runs_mcp import FAKE, Viewer, launch, run, seed, wait_ended, wait_until

from agentic_os.config import Settings
from agentic_os.errors import ApiError
from agentic_os.services.adapters.agy import EXCLUDE_LINE, exclude_from_git
from agentic_os.services.memory import list_notes


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


def control(server: LiveServer, run_id: str, action: str) -> httpx.Response:
    return httpx.post(
        f"{server.url}/api/runs/{run_id}/control", json={"action": action, "client_id": "v"}
    )


def started_idle(server: LiveServer, tmp_path: Path, prompt: str = "hola") -> tuple[dict, Viewer]:
    agent_id, project_id = seed(server, tmp_path / "web", "claude")
    started = launch(server, agent_id, project_id, prompt).json()
    viewer = Viewer(server, started["id"])  # client_id "v": the viewer that takes control
    assert wait_until(lambda: "RESPUESTA" in viewer.text)
    assert wait_until(lambda: run(server, started["id"])["activity"] == "idle")
    return started, viewer


def test_taking_control_ends_an_interrupted_turn(server: LiveServer, tmp_path: Path):
    started, viewer = started_idle(server, tmp_path)
    try:
        # The human starts a turn that never ends by itself, and hands the terminal back.
        assert control(server, started["id"], "take").status_code == 200
        viewer.ws.send(json.dumps({"type": "input", "data": "LARGO\r"}))
        assert wait_until(lambda: run(server, started["id"])["activity"] == "busy", 10)
        assert control(server, started["id"], "release").status_code == 200
        # Taking it again sends Esc: the turn is interrupted and Claude fires no Stop hook.
        assert control(server, started["id"], "take").status_code == 200
        assert wait_until(lambda: run(server, started["id"])["activity"] == "idle", 10)
    finally:
        viewer.close()
        httpx.post(f"{server.url}/api/runs/{started['id']}/stop")


def test_a_completed_run_is_not_closed_under_a_human(server: LiveServer, tmp_path: Path):
    started, viewer = started_idle(server, tmp_path)
    try:
        assert control(server, started["id"], "take").status_code == 200
        server.manager.complete_task(started["id"], "hecho")  # as the MCP tool would
        for _ in range(8):  # the human keeps the terminal: it is not closed under them
            time.sleep(1)
            assert run(server, started["id"])["status"] == "intervening"
        assert control(server, started["id"], "release").status_code == 200
        ended = wait_ended(server, started["id"])
        assert ended["status"] == "completed" and ended["summary"] == "hecho"
        assert "Continúa con la tarea" not in viewer.text  # no nudge: the task was done
    finally:
        viewer.close()


def test_a_user_stop_after_complete_task_is_not_completed(server: LiveServer, tmp_path: Path):
    started, viewer = started_idle(server, tmp_path)
    try:
        assert control(server, started["id"], "take").status_code == 200
        server.manager.complete_task(started["id"], "hecho")
        httpx.post(f"{server.url}/api/runs/{started['id']}/stop")
        assert wait_ended(server, started["id"])["status"] == "stopped"
    finally:
        viewer.close()


def test_event_errors_never_reach_the_session_threads(server: LiveServer, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(server.manager, "_store_event", broken)
    server.manager.add_event("whatever", "system", "closing")  # logged, not raised


def test_each_memory_write_is_its_own_note(server: LiveServer, tmp_path: Path):
    started, viewer = started_idle(server, tmp_path)
    try:
        server.manager.write_project_memory(started["id"], "primera nota")
        server.manager.write_project_memory(started["id"], "segunda nota")
        with server.db() as db:
            notes = list_notes(db, started["project_id"])
        assert [(n.author_name, n.text) for n in notes] == [
            ("Dev", "primera nota"),
            ("Dev", "segunda nota"),
        ]
    finally:
        viewer.close()
        httpx.post(f"{server.url}/api/runs/{started['id']}/stop")


def test_agy_folder_reservation_is_atomic(server: LiveServer, tmp_path: Path):
    manager = server.manager
    key = manager._reserve_agy_folder(str(tmp_path))
    with pytest.raises(ApiError) as busy:
        manager._reserve_agy_folder(str(tmp_path / "."))
    assert busy.value.code == "agy_folder_busy"
    manager._release_agy_folder(key)
    manager._release_agy_folder(manager._reserve_agy_folder(str(tmp_path)))


def test_plugin_excluded_in_a_git_worktree(tmp_path: Path):
    main = tmp_path / "repo" / ".git"
    worktree_git = main / "worktrees" / "tarea"
    worktree_git.mkdir(parents=True)
    (worktree_git / "commondir").write_text("../..", "utf-8")
    worktree = tmp_path / "tarea"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {worktree_git}", "utf-8")
    exclude_from_git(worktree)
    assert (main / "info" / "exclude").read_text("utf-8") == f"{EXCLUDE_LINE}\n"
