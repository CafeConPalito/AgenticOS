"""A downloaded engine run as a local server: what `llama-server` and `whisper-server` share.

The program is started when there is work, talks HTTP on the loopback only, answers one request
at a time and is stopped after a while without work, so the memory of its model is free when
nobody needs it (phase 14 for pictures, phase 16 for dictation).
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import psutil
import structlog

log = structlog.get_logger()

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
CREATE_NO_WINDOW = 0x08000000
MEMORY_MARGIN = 1_000_000_000  # leave this much for the rest of the machine

Launcher = Callable[[list[str], Path], "subprocess.Popen[bytes]"]


class ServerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def launch(argv: list[str], log_file: Path, low_priority: bool = True) -> subprocess.Popen[bytes]:
    """The real launcher: no window, its output kept for diagnosis, and low priority unless the
    user is waiting for the answer."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = CREATE_NO_WINDOW | (
            BELOW_NORMAL_PRIORITY_CLASS if low_priority else 0
        )
    with log_file.open("ab") as output:
        return subprocess.Popen(  # our own downloaded program
            argv, stdout=output, stderr=output, stdin=subprocess.DEVNULL, **options
        )


class ManagedServer:
    """Lifecycle of one server process. Subclasses say how to start it (`_argv`, `_check`) and
    what to ask it; everything they ask goes through `_request`, which holds the lock."""

    error_class: type[ServerError] = ServerError
    name = "server"
    health_path = "/health"
    start_timeout = 180.0  # loading a 4 GB model from disk

    def __init__(
        self,
        log_file: Path,
        idle_seconds: float,
        launcher: Launcher,
        client: Callable[[], httpx.Client] | None = None,
        reap_every: float = 5.0,
    ) -> None:
        self._log_file = Path(log_file)
        self._reap_every = reap_every
        self._idle = idle_seconds
        self._launcher = launcher
        self._client = client or (lambda: httpx.Client(timeout=300.0))
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._port = 0
        self._last_used = time.monotonic()
        self._busy = False
        self._retired = False
        self._stop = threading.Event()
        threading.Thread(target=self._reap, name=f"{self.name}-reaper", daemon=True).start()

    # ---------------------------------------------------------------- what subclasses give
    def _argv(self, port: int) -> list[str]:
        raise NotImplementedError

    def _check(self) -> None:
        """Raises `error_class` when the files or the memory are not there."""

    def _fail(self, code: str, message: str = "") -> ServerError:
        return self.error_class(code, message)

    # ----------------------------------------------------------------------------- life
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def log_file(self) -> Path:
        return self._log_file

    @property
    def busy(self) -> bool:
        return self._busy

    def _ensure(self) -> int:
        if self.running:
            return self._port
        self._kill()
        self._check()
        port = free_port()
        try:
            self._proc = self._launcher(self._argv(port), self.log_file)
        except OSError as error:
            raise self._fail("start_failed", f"{self.name} could not start: {error}") from error
        self._port = port
        self._wait_ready()
        log.info(f"{self.name}_started", port=port)
        return port

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.start_timeout
        with self._client() as client:
            while time.monotonic() < deadline:
                if self._proc is None or self._proc.poll() is not None:
                    code = None if self._proc is None else self._proc.returncode
                    self._proc = None
                    raise self._fail(
                        "start_failed", f"{self.name} stopped while loading (code {code})"
                    )
                try:
                    url = f"http://127.0.0.1:{self._port}{self.health_path}"
                    if client.get(url, timeout=2).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
        self._kill()
        raise self._fail("start_failed", f"{self.name} did not get ready in time")

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        with contextlib.suppress(Exception):
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        with contextlib.suppress(Exception):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    def stop(self) -> None:
        self._stop.set()
        # A request holds the lock while the model loads or answers (minutes): end the server
        # first so that the request fails now, then take the lock to clean up.
        proc = self._proc
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
        with self._lock:
            self._kill()

    def retire(self) -> None:
        """No longer wanted (another model was chosen), but a request may be running or waiting:
        let it finish, and stop the process the moment nobody uses it. Unlike `stop`, a request
        that still arrives later can start it again and it will be stopped again."""
        self._retired = True

    def _reap(self) -> None:
        while not self._stop.wait(self._reap_every):
            with self._lock:
                idle = time.monotonic() - self._last_used
                limit = 0.0 if self._retired else self._idle
                if self.running and not self._busy and idle >= limit:
                    log.info(f"{self.name}_idle")
                    self._kill()
                if self._retired and not self._busy and not self.running:
                    return

    # -------------------------------------------------------------------------- requests
    def _request(self, send: Callable[[httpx.Client, int], httpx.Response]) -> httpx.Response:
        """Starts the server if needed and runs `send(client, port)`. One at a time."""
        with self._lock:
            self._busy = True
            try:
                port = self._ensure()
                try:
                    with self._client() as client:
                        response = send(client, port)
                except httpx.HTTPError as error:
                    self._kill()
                    raise self._fail(
                        "request_failed", f"{type(error).__name__}: {error}"
                    ) from error
                if response.status_code >= 400:
                    raise self._fail("request_failed", f"HTTP {response.status_code}")
                return response
            finally:
                self._busy = False
                self._last_used = time.monotonic()

    def warm_up(self) -> None:
        """Starts the server now, so the first real request does not wait for the model."""
        with self._lock:
            self._busy = True
            try:
                self._ensure()
            finally:
                self._busy = False
                self._last_used = time.monotonic()


def memory_available() -> int:
    return psutil.virtual_memory().available
