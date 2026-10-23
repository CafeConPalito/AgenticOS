"""The dictation engine: `whisper-server`, from whisper.cpp (phase 16, ADR 0023).

whisper.cpp is not in the installer: the app downloads it (the `whisper-cpp` engine) with a
Whisper model and the small voice-activity model that comes with it. `WhisperServer` starts it
when someone dictates, sends the WAV from memory over HTTP on the loopback and stops it after a
few minutes without work. Unlike the picture describer it runs at normal priority: the user is
waiting for the answer.
"""

from __future__ import annotations

import functools
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
    launch,
    memory_available,
)

IDLE_SECONDS = 300.0
START_TIMEOUT = 60.0
REQUEST_TIMEOUT = 600.0  # a slow machine, a long dictation and the large model


class WhisperError(ServerError):
    pass


class WhisperServer(ManagedServer):
    error_class = WhisperError
    name = "whisper-server"
    start_timeout = START_TIMEOUT

    def __init__(
        self,
        data_dir: Path,
        engine: CatalogEntry,
        model: CatalogEntry,
        threads: int,
        idle_seconds: float = IDLE_SECONDS,
        launcher: Launcher | None = None,
        memory: Callable[[], int] = memory_available,
        client: Callable[[], httpx.Client] | None = None,
        reap_every: float = 5.0,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.engine, self.model = engine, model
        self.threads = threads
        self._memory = memory
        super().__init__(
            self.data_dir / "logs" / "whisper-server.log",
            idle_seconds,
            launcher or functools.partial(launch, low_priority=False),
            client or (lambda: httpx.Client(timeout=REQUEST_TIMEOUT)),
            reap_every,
        )

    def _argv(self, port: int) -> list[str]:
        program = store.executable(self.data_dir, self.engine)
        model = store.file_path(self.data_dir, self.model, self.model.usage["model"])
        vad = store.file_path(self.data_dir, self.model, self.model.usage["vad"])
        return [
            str(program), "-m", str(model), "-t", str(self.threads),
            "--host", "127.0.0.1", "--port", str(port),
            "--vad", "-vm", str(vad),
        ]  # fmt: skip

    def _check(self) -> None:
        if not store.is_installed(self.data_dir, self.engine):
            raise WhisperError("engine_missing", "whisper.cpp is not downloaded")
        if not store.is_installed(self.data_dir, self.model):
            raise WhisperError("model_missing", f"{self.model.title} is not downloaded")
        needed = self.model.size + MEMORY_MARGIN
        available = self._memory()
        if available < needed:
            raise WhisperError(
                "not_enough_memory",
                f"{self.model.title} needs about {needed // 2**20} MB free and "
                f"{available // 2**20} MB are available",
            )

    @property
    def state(self) -> str:
        """`stopped`, `ready` (loaded, waiting) or `busy` (transcribing or loading)."""
        if self.busy:
            return "busy"
        return "ready" if self.running else "stopped"

    # ------------------------------------------------------------------- transcription
    def transcribe(self, wav: bytes, language: str = "es", prompt: str = "") -> str:
        """The text of a 16 kHz mono WAV, or "" when there is no speech. Raises `WhisperError`."""
        data = {"temperature": "0.0", "response_format": "json", "language": language}
        if prompt:
            data["prompt"] = prompt
        response = self._request(
            lambda client, port: client.post(
                f"http://127.0.0.1:{port}/inference",
                files={"file": ("dictation.wav", wav, "audio/wav")},
                data=data,
            )
        )
        try:
            return str(response.json().get("text", "")).strip()
        except ValueError as error:
            raise WhisperError("transcription_failed", "unreadable answer") from error
