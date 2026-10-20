"""The local vision model, served by `llama-server` (phase 14, block 7).

`llama.cpp` is not in the installer: the app downloads it (the `llama-cpp` engine) together with
a vision model and its projector. `LlamaServer` starts it when there are pictures to describe,
talks to it over HTTP on the loopback (the OpenAI chat API) and stops it after a while without
work, so its gigabytes of memory are free when nobody needs them.
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

from agentic_os.services.localmodels import store
from agentic_os.services.localmodels.catalog import CatalogEntry

log = structlog.get_logger()

IDLE_SECONDS = 60.0
START_TIMEOUT = 180.0  # loading a 4 GB model from disk
CONTEXT = 4096
MEMORY_MARGIN = 1_000_000_000  # leave this much for the rest of the machine
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
CREATE_NO_WINDOW = 0x08000000

Launcher = Callable[[list[str], Path], "subprocess.Popen[bytes]"]


class LlamaError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def launch(argv: list[str], log_file: Path) -> subprocess.Popen[bytes]:
    """The real launcher: low priority, no window, its output kept for diagnosis."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    with log_file.open("ab") as output:
        return subprocess.Popen(  # our own downloaded program
            argv, stdout=output, stderr=output, stdin=subprocess.DEVNULL, **options
        )


class LlamaServer:
    def __init__(
        self,
        data_dir: Path,
        engine: CatalogEntry,
        vision: CatalogEntry,
        threads: int,
        idle_seconds: float = IDLE_SECONDS,
        launcher: Launcher = launch,
        memory: Callable[[], int] = lambda: psutil.virtual_memory().available,
        client: Callable[[], httpx.Client] | None = None,
        reap_every: float = 5.0,
    ) -> None:
        self._reap_every = reap_every
        self.data_dir = Path(data_dir)
        self.engine, self.vision = engine, vision
        self.threads = threads
        self._idle = idle_seconds
        self._launcher = launcher
        self._memory = memory
        self._client = client or (lambda: httpx.Client(timeout=300.0))
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._port = 0
        self._last_used = time.monotonic()
        self._busy = False
        self._stop = threading.Event()
        threading.Thread(target=self._reap, name="llama-reaper", daemon=True).start()

    # ------------------------------------------------------------------------- life
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "llama-server.log"

    def _argv(self, port: int) -> list[str]:
        program = store.executable(self.data_dir, self.engine)
        model = store.file_path(self.data_dir, self.vision, self.vision.usage["model"])
        projector = store.file_path(self.data_dir, self.vision, self.vision.usage["projector"])
        return [
            str(program), "-m", str(model), "--mmproj", str(projector),
            "-c", str(CONTEXT), "-t", str(self.threads),
            "--host", "127.0.0.1", "--port", str(port),
            "--no-webui", "-ngl", "0", "--jinja",
        ]  # fmt: skip

    def _ensure(self) -> int:
        if self.running:
            return self._port
        self._kill()
        if not store.is_installed(self.data_dir, self.engine):
            raise LlamaError("engine_missing", "llama.cpp is not downloaded")
        if not store.is_installed(self.data_dir, self.vision):
            raise LlamaError("model_missing", f"{self.vision.title} is not downloaded")
        needed = self.vision.size + MEMORY_MARGIN
        available = self._memory()
        if available < needed:
            raise LlamaError(
                "not_enough_memory",
                f"{self.vision.title} needs about {needed // 2**20} MB free and "
                f"{available // 2**20} MB are available",
            )
        port = free_port()
        try:
            self._proc = self._launcher(self._argv(port), self.log_file)
        except OSError as error:
            raise LlamaError("start_failed", f"llama-server could not start: {error}") from error
        self._port = port
        self._wait_ready()
        log.info("llama_server_started", model=self.vision.id, port=port)
        return port

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT
        with self._client() as client:
            while time.monotonic() < deadline:
                if self._proc is None or self._proc.poll() is not None:
                    code = None if self._proc is None else self._proc.returncode
                    self._proc = None
                    raise LlamaError(
                        "start_failed", f"llama-server stopped while loading (code {code})"
                    )
                try:
                    if (
                        client.get(f"http://127.0.0.1:{self._port}/health", timeout=2).status_code
                        == 200
                    ):
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
        self._kill()
        raise LlamaError("start_failed", "llama-server did not get ready in time")

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
        # `chat` holds the lock while the model loads or answers (minutes): end the server first
        # so that the request fails now, then take the lock to clean up.
        proc = self._proc
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
        with self._lock:
            self._kill()

    def _reap(self) -> None:
        while not self._stop.wait(self._reap_every):
            with self._lock:
                idle = time.monotonic() - self._last_used
                if self.running and not self._busy and idle > self._idle:
                    log.info("llama_server_idle")
                    self._kill()

    # --------------------------------------------------------------------------- chat
    def chat(self, messages: list[dict], max_tokens: int = 300) -> dict:
        """One chat completion (OpenAI format). Raises `LlamaError`."""
        with self._lock:
            self._busy = True
            try:
                port = self._ensure()
                body = {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                try:
                    with self._client() as client:
                        response = client.post(
                            f"http://127.0.0.1:{port}/v1/chat/completions", json=body
                        )
                except httpx.HTTPError as error:
                    self._kill()
                    raise LlamaError(
                        "request_failed", f"{type(error).__name__}: {error}"
                    ) from error
                if response.status_code >= 400:
                    raise LlamaError("request_failed", f"HTTP {response.status_code}")
                return response.json()
            finally:
                self._busy = False
                self._last_used = time.monotonic()
