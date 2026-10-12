"""A real backend (uvicorn in a thread) for tests that need a listening port: CLI processes
and MCP clients cannot talk to a TestClient.

Packaged mode (phase 08): with AGENTIC_OS_E2E_BINARY set to the PyInstaller sidecar, the
backend is that executable instead, configured through its environment like the desktop app
runs it. It catches modules or data files missing from the packaged build. The tests that
reach into the backend's objects (`server.manager`, `server.db()`) are skipped then.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
import uvicorn
from fastapi import FastAPI

from agentic_os.app import create_app
from agentic_os.config import Settings

BINARY = os.environ.get("AGENTIC_OS_E2E_BINARY")
READY_PREFIX = "AGENTIC_OS_READY"
# For tests that use the backend's objects, not just its API.
in_process_only = pytest.mark.skipif(
    bool(BINARY), reason="needs the backend in this process (not the packaged one)"
)


@dataclass
class LiveServer:
    app: FastAPI | None
    url: str

    @property
    def manager(self):
        assert self.app is not None, "not available with the packaged backend"
        return self.app.state.run_manager

    def db(self):
        assert self.app is not None, "not available with the packaged backend"
        return self.app.state.sessionmaker()


@contextmanager
def live_server(settings: Settings) -> Iterator[LiveServer]:
    if BINARY:
        with packaged_server(settings, BINARY) as server:
            yield server
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(settings.model_copy(update={"port": port}))
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "live server did not start"
    try:
        yield LiveServer(app, f"http://127.0.0.1:{port}")
    finally:
        server.should_exit = True
        thread.join(30)


def _environment(settings: Settings) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTIC_OS_")}
    env.update(
        AGENTIC_OS_DATA_DIR=str(settings.data_dir),
        AGENTIC_OS_CLI_COMMAND_OVERRIDES=json.dumps(settings.cli_command_overrides),
    )
    if settings.claude_config_file:
        env["AGENTIC_OS_CLAUDE_CONFIG_FILE"] = str(settings.claude_config_file)
    if settings.agy_settings_file:
        env["AGENTIC_OS_AGY_SETTINGS_FILE"] = str(settings.agy_settings_file)
    return env


@contextmanager
def packaged_server(settings: Settings, binary: str) -> Iterator[LiveServer]:
    """The sidecar as the desktop app runs it: free port, READY line, and a parent process it
    watches. Killing that parent is how the backend is closed gracefully (ADR 0002)."""
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"])
    backend = subprocess.Popen(
        [binary, "--port", "0", "--parent-pid", str(parent.pid)],
        env=_environment(settings),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        port = _wait_ready(backend)
        yield LiveServer(None, f"http://127.0.0.1:{port}")
    finally:
        parent.kill()
        try:
            backend.wait(30)
        except subprocess.TimeoutExpired:
            backend.kill()
            backend.wait(5)


def _wait_ready(backend: subprocess.Popen[str], timeout: float = 60) -> int:
    found: list[int] = []

    def read() -> None:
        assert backend.stdout is not None
        for line in backend.stdout:
            if line.startswith(READY_PREFIX) and not found:
                found.append(json.loads(line.removeprefix(READY_PREFIX))["port"])

    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + timeout
    while not found and time.monotonic() < deadline and backend.poll() is None:
        time.sleep(0.05)
    assert found, f"the packaged backend did not start (exit code {backend.poll()})"
    return found[0]
