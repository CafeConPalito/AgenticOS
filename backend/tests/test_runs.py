"""Runs end to end: API + WebSocket + a real PTY running the fake CLI (tests/fake_cli.py)."""

import contextlib
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.services.runs import session as session_module

FAKE = str(Path(__file__).with_name("fake_cli.py"))


def make_settings(tmp_path: Path, *extra_args: str) -> Settings:
    command = [sys.executable, FAKE, *extra_args]
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        cli_command_overrides={"claude": command, "agy": command},
    )


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        yield client


def seed(client: TestClient, tmp_path: Path, cli: str = "claude") -> tuple[str, str]:
    folder = tmp_path / "proyecto"
    folder.mkdir(exist_ok=True)
    agent = client.post("/api/agents", json={"name": "Dev", "cli": cli}).json()
    project = client.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()
    return agent["id"], project["id"]


def launch(client: TestClient, tmp_path: Path, prompt: str = "hola", cli: str = "claude") -> dict:
    agent_id, project_id = seed(client, tmp_path, cli)
    response = client.post(
        "/api/runs", json={"agent_id": agent_id, "project_id": project_id, "prompt": prompt}
    )
    assert response.status_code == 201, response.text
    return response.json()


class Viewer:
    """Collects terminal output from a WebSocket in a background thread."""

    def __init__(self, client: TestClient, run_id: str, client_id: str) -> None:
        self.client_id = client_id
        self._cm = client.websocket_connect(f"/api/runs/{run_id}/terminal?client_id={client_id}")
        self.ws = self._cm.__enter__()
        self.text = ""
        self.messages: list[dict] = []
        self.closed = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        try:
            while True:
                message = self.ws.receive_json()
                self.messages.append(message)
                if message["type"] in ("snapshot", "output"):
                    self.text += message["data"]
                if message["type"] == "exit":
                    break
        except Exception:
            pass
        self.closed.set()

    def wait_for(self, predicate: Callable[[], bool] | str, timeout: float = 20) -> bool:
        check = (lambda: predicate in self.text) if isinstance(predicate, str) else predicate
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if check():
                return True
            time.sleep(0.05)
        return False

    def send(self, message: dict) -> None:
        self.ws.send_json(message)

    def close(self) -> None:
        """Closes the socket without ever blocking the test (daemon thread + deadline)."""

        def exit_cm() -> None:
            with contextlib.suppress(Exception):
                self._cm.__exit__(None, None, None)

        closer = threading.Thread(target=exit_cm, daemon=True)
        closer.start()
        closer.join(5)


def run_status(client: TestClient, run_id: str) -> dict:
    return client.get(f"/api/runs/{run_id}").json()


def wait_status(client: TestClient, run_id: str, *statuses: str, timeout: float = 25) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = run_status(client, run_id)
        if run["status"] in statuses:
            return run
        time.sleep(0.1)
    raise AssertionError(f"run never reached {statuses}: {run_status(client, run_id)}")


def test_launch_accepts_trust_and_streams_the_answer(app_client: TestClient, tmp_path: Path):
    run = launch(app_client, tmp_path, "hola")
    assert run["status"] == "running"
    assert run["cli"] == "claude" and run["agent_name"] == "Dev" and run["project_name"] == "Web"
    assert run["cli_session_id"]
    viewer = Viewer(app_client, run["id"], "a")
    try:
        assert viewer.wait_for("● RESPUESTA: hola"), viewer.text[-500:]  # trust auto-accepted
        assert "Trusted." in viewer.text
        log = Path(app_client.app.state.settings.data_dir) / "runs" / f"{run['id']}.log"
        assert "RESPUESTA: hola" in log.read_text("utf-8")
    finally:
        viewer.close()


def test_two_viewers_and_control(app_client: TestClient, tmp_path: Path):
    run = launch(app_client, tmp_path)
    a, b = Viewer(app_client, run["id"], "a"), Viewer(app_client, run["id"], "b")
    try:
        assert a.wait_for("RESPUESTA: hola") and b.wait_for("RESPUESTA: hola")

        b.send({"type": "input", "data": "intruso\r"})  # nobody gave b the control
        time.sleep(1)
        assert "intruso" not in a.text

        taken = app_client.post(
            f"/api/runs/{run['id']}/control", json={"action": "take", "client_id": "a"}
        ).json()
        assert taken["status"] == "intervening" and taken["controller"] == "a"
        conflict = app_client.post(
            f"/api/runs/{run['id']}/control", json={"action": "take", "client_id": "b"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "control_taken"

        a.send({"type": "input", "data": "otra\r"})
        assert a.wait_for("RESPUESTA: otra") and b.wait_for("RESPUESTA: otra")

        released = app_client.post(
            f"/api/runs/{run['id']}/control", json={"action": "release", "client_id": "a"}
        ).json()
        assert released["status"] == "running" and released["controller"] is None
        time.sleep(1)
        assert "Continúa con la tarea" not in a.text  # a typed: no nudge
    finally:
        a.close()
        b.close()


def test_resize_is_broadcast_and_only_the_controller_resizes(app_client: TestClient, tmp_path):
    run = launch(app_client, tmp_path)
    a, b = Viewer(app_client, run["id"], "a"), Viewer(app_client, run["id"], "b")

    def size_seen(viewer: Viewer, cols: int, rows: int) -> bool:
        return any(
            m["type"] == "state" and (m["cols"], m["rows"]) == (cols, rows) for m in viewer.messages
        )

    try:
        assert a.wait_for("RESPUESTA: hola")
        a.send({"type": "resize", "cols": 150, "rows": 40})
        assert b.wait_for(lambda: size_seen(b, 150, 40))  # passive viewers learn the size
        assert run_status(app_client, run["id"])["cols"] == 150

        app_client.post(f"/api/runs/{run['id']}/control", json={"action": "take", "client_id": "a"})
        b.send({"type": "resize", "cols": 60, "rows": 10})  # b does not hold the control
        time.sleep(1)
        assert not size_seen(a, 60, 10)
        assert run_status(app_client, run["id"])["cols"] == 150
    finally:
        a.close()
        b.close()


def test_take_interrupts_and_release_without_typing_nudges(app_client: TestClient, tmp_path):
    run = launch(app_client, tmp_path)
    viewer = Viewer(app_client, run["id"], "a")
    try:
        assert viewer.wait_for("RESPUESTA: hola")
        control = f"/api/runs/{run['id']}/control"
        app_client.post(control, json={"action": "take", "client_id": "a"})
        viewer.send({"type": "input", "data": "LARGO\r"})
        assert viewer.wait_for("esc to interrupt")
        app_client.post(control, json={"action": "release", "client_id": "a"})
        assert viewer.wait_for(lambda: run_status(app_client, run["id"])["activity"] == "busy")

        app_client.post(control, json={"action": "take", "client_id": "a"})  # sends Esc
        assert viewer.wait_for("Interrupted")
        app_client.post(control, json={"action": "release", "client_id": "a"})  # nothing typed
        assert viewer.wait_for("RESPUESTA: Continúa con la tarea.")
    finally:
        viewer.close()


def test_reconnecting_viewer_gets_the_scrollback(app_client: TestClient, tmp_path: Path):
    run = launch(app_client, tmp_path, "primera")
    first = Viewer(app_client, run["id"], "a")
    assert first.wait_for("RESPUESTA: primera")
    first.close()
    second = Viewer(app_client, run["id"], "a2")
    try:
        assert second.wait_for(
            lambda: (
                bool(second.messages)
                and second.messages[0]["type"] == "snapshot"
                and "RESPUESTA: primera" in second.messages[0]["data"]
            )
        )
    finally:
        second.close()


def test_graceful_stop_and_finished_run_replays_its_log(app_client: TestClient, tmp_path):
    run = launch(app_client, tmp_path, "adios")
    viewer = Viewer(app_client, run["id"], "a")
    assert viewer.wait_for("RESPUESTA: adios")
    assert app_client.post(f"/api/runs/{run['id']}/stop").status_code == 202
    finished = wait_status(app_client, run["id"], "stopped")
    assert finished["exit_code"] == 0 and finished["ended_at"]
    assert viewer.closed.wait(10)
    assert viewer.messages[-1]["type"] == "exit"
    viewer.close()

    replay = Viewer(app_client, run["id"], "later")
    assert replay.closed.wait(10)
    assert "RESPUESTA: adios" in replay.text
    assert replay.messages[-1] == {"type": "exit", "code": 0, "status": "stopped"}
    replay.close()
    assert app_client.post(f"/api/runs/{run['id']}/stop").json()["detail"]["code"] == (
        "run_not_active"
    )


def test_agy_graceful_stop_waits_for_the_exit_notice(app_client: TestClient, tmp_path):
    run = launch(app_client, tmp_path, "adios", cli="agy")
    viewer = Viewer(app_client, run["id"], "a")
    try:
        assert viewer.wait_for("RESPUESTA: adios")
        started = time.monotonic()
        app_client.post(f"/api/runs/{run['id']}/stop")
        finished = wait_status(app_client, run["id"], "stopped")
        assert "press ctrl+c again to exit" in viewer.text
        assert finished["exit_code"] == 130  # left by itself, not terminated
        assert time.monotonic() - started < 8
    finally:
        viewer.close()


def test_stop_retries_when_the_cli_was_not_listening(tmp_path: Path):
    # Real Claude Code drops keys while it finishes background work after a turn.
    with TestClient(create_app(make_settings(tmp_path, "--deaf"))) as client:
        run = launch(client, tmp_path, "adios")
        viewer = Viewer(client, run["id"], "a")
        try:
            assert viewer.wait_for("RESPUESTA: adios")
            started = time.monotonic()
            client.post(f"/api/runs/{run['id']}/stop")
            finished = wait_status(client, run["id"], "stopped")
            assert "Resume this session" in viewer.text
            assert finished["exit_code"] == 0  # left by itself, not terminated
            assert time.monotonic() - started < 10
        finally:
            viewer.close()


def test_forced_stop_when_the_cli_ignores_exit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(session_module, "STOP_TIMEOUT", 1.5)
    with TestClient(create_app(make_settings(tmp_path, "--ignore-exit"))) as client:
        run = launch(client, tmp_path)
        viewer = Viewer(client, run["id"], "a")
        assert viewer.wait_for("RESPUESTA: hola")
        client.post(f"/api/runs/{run['id']}/stop")
        assert viewer.wait_for("(ignoring /exit)")
        assert wait_status(client, run["id"], "stopped", timeout=15)["status"] == "stopped"
        viewer.close()


def test_agy_style_launch(app_client: TestClient, tmp_path: Path):
    run = launch(app_client, tmp_path, "revisa", cli="agy")
    assert run["cli"] == "agy" and run["cli_session_id"] is None
    viewer = Viewer(app_client, run["id"], "a")
    try:
        assert viewer.wait_for("RESPUESTA: revisa")
    finally:
        viewer.close()


def test_shutdown_stops_live_runs_and_recover_marks_leftovers(tmp_path: Path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        run = launch(client, tmp_path)
        viewer = Viewer(client, run["id"], "a")
        assert viewer.wait_for("RESPUESTA: hola")
        viewer.close()
    # Leaving the TestClient ran the lifespan shutdown: the run was stopped, not left alive.
    with TestClient(create_app(settings)) as client:
        assert run_status(client, run["id"])["status"] == "stopped"

        # A run left "running" by a crashed backend is marked interrupted on start.
        with client.app.state.sessionmaker() as db:
            from agentic_os.models import Run

            db.get(Run, run["id"]).status = "running"
            db.commit()
    with TestClient(create_app(settings)) as client:
        assert run_status(client, run["id"])["status"] == "interrupted"


def test_launch_validation(app_client: TestClient, tmp_path: Path, monkeypatch):
    agent_id, project_id = seed(app_client, tmp_path)
    assert (
        app_client.post(
            "/api/runs", json={"agent_id": "nope", "project_id": project_id, "prompt": "x"}
        ).json()["detail"]["code"]
        == "agent_not_found"
    )
    assert (
        app_client.post(
            "/api/runs", json={"agent_id": agent_id, "project_id": project_id, "prompt": "  "}
        ).json()["detail"]["field"]
        == "prompt"
    )
    app_client.app.state.settings.cli_command_overrides = {}
    from agentic_os.services.runs import launcher

    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    response = app_client.post(
        "/api/runs", json={"agent_id": agent_id, "project_id": project_id, "prompt": "x"}
    )
    assert response.json()["detail"]["code"] == "cli_not_installed"


def test_list_filters(app_client: TestClient, tmp_path: Path):
    run = launch(app_client, tmp_path)
    assert [r["id"] for r in app_client.get("/api/runs").json()] == [run["id"]]
    assert app_client.get("/api/runs", params={"active": True}).json()[0]["id"] == run["id"]
    assert app_client.get("/api/runs", params={"active": False}).json() == []
    assert app_client.get("/api/runs", params={"agent_id": "otro"}).json() == []
