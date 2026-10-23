"""The local vision model, served by `llama-server` (phase 14, block 7).

`llama.cpp` is not in the installer: the app downloads it (the `llama-cpp` engine) together with
a vision model and its projector. `LlamaServer` starts it when there are pictures to describe,
talks to it over HTTP on the loopback (the OpenAI chat API) and stops it after a while without
work, so its gigabytes of memory are free when nobody needs them. The lifecycle is shared with
the dictation engine (`server.ManagedServer`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from agentic_os.services.localmodels import store
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.server import (
    MEMORY_MARGIN,
    Launcher,
    ManagedServer,
    ServerError,
    free_port,  # noqa: F401  (kept importable from here)
    launch,
    memory_available,
)

IDLE_SECONDS = 60.0
START_TIMEOUT = 180.0  # loading a 4 GB model from disk
CONTEXT = 4096


class LlamaError(ServerError):
    pass


class LlamaServer(ManagedServer):
    error_class = LlamaError
    name = "llama-server"
    start_timeout = START_TIMEOUT

    def __init__(
        self,
        data_dir: Path,
        engine: CatalogEntry,
        vision: CatalogEntry,
        threads: int,
        idle_seconds: float = IDLE_SECONDS,
        launcher: Launcher = launch,
        memory: Callable[[], int] = memory_available,
        client: Callable[[], httpx.Client] | None = None,
        reap_every: float = 5.0,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.engine, self.vision = engine, vision
        self.threads = threads
        self._memory = memory
        super().__init__(
            self.data_dir / "logs" / "llama-server.log",
            idle_seconds,
            launcher,
            client,
            reap_every,
        )

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

    def _check(self) -> None:
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

    # --------------------------------------------------------------------------- chat
    def chat(self, messages: list[dict], max_tokens: int = 300) -> dict:
        """One chat completion (OpenAI format). Raises `LlamaError`."""
        body = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        response = self._request(
            lambda client, port: client.post(
                f"http://127.0.0.1:{port}/v1/chat/completions", json=body
            )
        )
        return response.json()
