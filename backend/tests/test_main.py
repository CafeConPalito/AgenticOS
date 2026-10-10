import json
import os
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from agentic_os.__main__ import READY_PREFIX, pid_exists


def start_backend(
    *extra: str, stderr: int = subprocess.DEVNULL
) -> tuple[subprocess.Popen[str], int]:
    # Never touch the real %APPDATA%\AgenticOS database from tests.
    data_dir = tempfile.mkdtemp(prefix="agentic-os-test-")
    proc = subprocess.Popen(
        [sys.executable, "-m", "agentic_os", "--port", "0", *extra],
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        env={**os.environ, "AGENTIC_OS_DATA_DIR": data_dir},
    )
    assert proc.stdout is not None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line.startswith(READY_PREFIX):
            return proc, json.loads(line.removeprefix(READY_PREFIX))["port"]
        if not line and proc.poll() is not None:
            break
    proc.kill()
    pytest.fail("backend never announced readiness")


def test_free_port_handshake_serves_health():
    proc, port = start_backend()
    try:
        assert port > 0
        response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=5)
        assert response.json()["status"] == "ok"
    finally:
        proc.kill()
        proc.wait(5)


def test_real_server_accepts_websockets():
    # TestClient bypasses uvicorn: without a WebSocket library uvicorn answers the upgrade
    # with a 404, so the terminal only works if the real server can speak WebSocket.
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect

    proc, port = start_backend()
    try:
        url = f"ws://127.0.0.1:{port}/api/runs/missing/terminal?client_id=test"
        with connect(url, open_timeout=5) as ws, pytest.raises(ConnectionClosed) as closed:
            ws.recv(timeout=5)
        assert closed.value.rcvd is not None
        assert closed.value.rcvd.code == 4404
    finally:
        proc.kill()
        proc.wait(5)


def test_exits_when_parent_dies():
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc, _ = start_backend("--parent-pid", str(parent.pid), "--watchdog-interval", "0.2")
    try:
        parent.kill()
        parent.wait(5)
        assert proc.wait(timeout=5) is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_exits_when_parent_dies_and_its_pipes_are_closed():
    # The desktop shell owns the sidecar's stdout/stderr pipes; when it dies they break and any
    # write fails. The watchdog must still shut the backend down.
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc, _ = start_backend(
        "--parent-pid", str(parent.pid), "--watchdog-interval", "0.2", stderr=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None and proc.stderr is not None
        proc.stdout.close()
        proc.stderr.close()
        parent.kill()
        parent.wait(5)
        assert proc.wait(timeout=10) is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_pid_exists():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    assert pid_exists(proc.pid)
    proc.kill()
    proc.wait(5)
    assert not pid_exists(proc.pid)
