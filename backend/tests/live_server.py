"""A real backend (uvicorn in a thread) for tests that need a listening port: CLI processes
and MCP clients cannot talk to a TestClient."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from agentic_os.app import create_app
from agentic_os.config import Settings


@dataclass
class LiveServer:
    app: FastAPI
    url: str

    @property
    def manager(self):
        return self.app.state.run_manager

    def db(self):
        return self.app.state.sessionmaker()


@contextmanager
def live_server(settings: Settings) -> Iterator[LiveServer]:
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
