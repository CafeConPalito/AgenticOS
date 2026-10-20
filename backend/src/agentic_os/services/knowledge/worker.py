"""The knowledge worker: the heavy work (conversion now; OCR and embeddings later) runs in a
process of its own, at low priority, so the API and the agents stay responsive (spike S8).

Protocol: JSON lines in UTF-8. The backend writes a request per line,
`{"id": "r1", "op": "convert", ...}`; the worker answers with any number of
`{"id": "r1", "event": "progress", "done": 3, "total": 12}` lines and then one
`{"id": "r1", "ok": true, ...}` or `{"id": "r1", "ok": false, "code": "...", "message": "..."}`.

The same file is the worker's `main` (`python -m agentic_os.services.knowledge.worker`, or the
packaged executable with `--knowledge-worker`) and the backend's side of the conversation
(`ProcessWorker`). `InlineWorker` runs the requests in the caller's process: the tests, and
the fallback when a second process is not wanted.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import structlog

from agentic_os.services.knowledge.errors import KnowledgeError

log = structlog.get_logger()

Emit = Callable[[dict], None]
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
CREATE_NO_WINDOW = 0x08000000
IDLE_SECONDS = 60.0  # a worker nobody asked anything for leaves, and takes its memory with it
REQUEST_TIMEOUT = 20 * 60.0  # one document, however big, is not worth more than this


# ------------------------------------------------------------------------ the work itself
def handle(request: dict, emit: Emit) -> dict:
    """Runs one request. Never raises: a failure is the `{"ok": false, ...}` answer."""
    rid = request.get("id")
    try:
        op = request.get("op")
        if op == "ping":
            return {"ok": True, "pid": os.getpid()}
        if op == "convert":
            from agentic_os.services.knowledge.convert import convert_file

            def progress(done: int, total: int) -> None:
                emit({"id": rid, "event": "progress", "done": done, "total": total})

            converted = convert_file(
                Path(request["path"]),
                ext=request["ext"],
                workdir=Path(request["workdir"]),
                name=request.get("name", ""),
                url=request.get("url"),
                progress=progress,
            )
            return {
                "ok": True,
                "markdown": converted.markdown,
                "title": converted.title,
                "images": [image.as_dict() for image in converted.images],
                "dropped_images": converted.dropped_images,
            }
        if op == "ocr":
            from agentic_os.services.knowledge import ocr

            def reading(done: int, total: int) -> None:
                emit({"id": rid, "event": "progress", "done": done, "total": total})

            texts, failed = ocr.read_all(
                Path(request["folder"]),
                {int(n): name for n, name in request["files"].items()},
                request["models"],
                int(request.get("threads", 0)),
                reading,
            )
            return {"ok": True, "texts": {str(n): t for n, t in texts.items()}, "failed": failed}
        if op == "embed":
            from agentic_os.services.knowledge import embeddings

            vectors = embeddings.embedder(request["model"], int(request.get("threads", 0))).encode(
                request["texts"], request["kind"]
            )
            return {"ok": True, "vectors": embeddings.pack(vectors), "count": len(vectors)}
        return KnowledgeError("convert_error", f"unknown operation {op!r}").as_dict()
    except KnowledgeError as error:
        return error.as_dict()
    except Exception as error:
        log.exception("knowledge_worker_failed", op=request.get("op"))
        code = "embed_error" if request.get("op") == "embed" else "convert_error"
        return KnowledgeError(code, f"{type(error).__name__}: {error}"[:300]).as_dict()


def serve() -> None:
    """The worker process: reads requests from stdin until `quit` or the end of the input."""
    protocol = sys.stdout
    sys.stdin.reconfigure(encoding="utf-8")
    protocol.reconfigure(encoding="utf-8")
    sys.stdout = sys.stderr  # a library that prints must not corrupt the protocol

    def write(message: dict) -> None:
        protocol.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        if request.get("op") == "quit":
            return
        answer = handle(request, write)
        answer["id"] = request.get("id")
        write(answer)


# ------------------------------------------------------------------- the backend's side
class Worker(Protocol):
    def request(self, request: dict, on_event: Emit | None = None) -> dict: ...

    def close(self) -> None: ...


class InlineWorker:
    """Runs the requests here, in the caller's thread (tests; and no second process)."""

    def request(self, request: dict, on_event: Emit | None = None) -> dict:
        answer = handle(request, on_event or (lambda _: None))
        answer["id"] = request.get("id")
        return answer

    def close(self) -> None:
        pass


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--knowledge-worker"]
    return [sys.executable, "-m", "agentic_os.services.knowledge.worker"]


class ProcessWorker:
    """A worker process that starts when the first request comes and leaves when it has been idle
    for a while. One request at a time (a lock)."""

    def __init__(
        self,
        command: Callable[[], list[str]] = worker_command,
        idle_seconds: float = IDLE_SECONDS,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._command = command
        self._idle = idle_seconds
        self._timeout = timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._last_used = time.monotonic()
        self._busy = False
        self._stop = threading.Event()
        self._reaper = threading.Thread(target=self._reap, name="knowledge-reaper", daemon=True)
        self._reaper.start()

    # --- process
    def _start(self) -> subprocess.Popen[str]:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        options: dict = {}
        if sys.platform == "win32":
            options["creationflags"] = BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
        else:
            options["preexec_fn"] = lambda: os.nice(10)
        proc = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
            **options,
        )
        log.info("knowledge_worker_started", pid=proc.pid)
        return proc

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        with contextlib.suppress(Exception):
            if proc.poll() is None:
                proc.stdin.write(json.dumps({"op": "quit"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=3)
        with contextlib.suppress(Exception):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)

    def _reap(self) -> None:
        while not self._stop.wait(5.0):
            with self._lock:
                if (
                    self._proc
                    and not self._busy
                    and time.monotonic() - self._last_used > self._idle
                ):
                    log.info("knowledge_worker_idle")
                    self._kill()

    def close(self) -> None:
        self._stop.set()
        # A request in flight holds the lock until it ends (up to the timeout): stop its process
        # first so that it fails now, and only then take the lock to clean up.
        proc = self._proc
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
        with self._lock:
            self._kill()

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc and self._proc.poll() is None else None

    # --- requests
    def request(self, request: dict, on_event: Emit | None = None) -> dict:
        rid = f"r{next(self._ids)}"
        message = {**request, "id": rid}
        with self._lock:
            self._busy = True
            watchdog: threading.Timer | None = None
            try:
                if self._proc is None or self._proc.poll() is not None:
                    self._proc = self._start()
                proc = self._proc
                watchdog = threading.Timer(self._timeout, proc.kill)
                watchdog.start()
                proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                for line in proc.stdout:
                    try:
                        answer = json.loads(line)
                    except ValueError:
                        continue  # a stray line is not ours
                    if answer.get("id") != rid:
                        continue
                    if answer.get("event"):
                        if on_event:
                            on_event(answer)
                        continue
                    return answer
                raise OSError("the worker closed its output")
            except (OSError, ValueError) as error:
                self._kill()
                raise KnowledgeError(
                    "convert_error", f"the worker stopped ({error}); try again"
                ) from error
            finally:
                if watchdog:
                    watchdog.cancel()
                self._busy = False
                self._last_used = time.monotonic()


if __name__ == "__main__":
    serve()
