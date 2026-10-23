"""Dictation: the audio of a microphone in, the text out (phase 16, ADR 0023).

Everything happens on this machine: the WAV comes in the request, is checked in memory, goes to a
`whisper-server` on the loopback and is forgotten. One transcription at a time; the rest wait.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

import psutil
import structlog
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.services.dictation import audio, config, hints
from agentic_os.services.dictation.audio import DictationError
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.whisper import WhisperError, WhisperServer

log = structlog.get_logger()

ENGINE_ID = "whisper-cpp"
# What Whisper writes for sound it does not understand, or that it learned from subtitles.
TAG = re.compile(r"^\s*[\[\(\*♪][^\]\)]*[\]\)\*♪]?[\s.]*$")
PHANTOMS = ("amara.org", "gracias por ver el vídeo", "gracias por ver el video", "suscríbete")

# What a `WhisperError` means for the person.
STATUS = {
    "engine_missing": 409,
    "model_missing": 409,
    "not_enough_memory": 503,
    "start_failed": 503,
    "request_failed": 502,
    "transcription_failed": 502,
}


@dataclass(frozen=True)
class Transcript:
    text: str
    seconds: float
    model: str


@dataclass(frozen=True)
class Status:
    enabled: bool
    ready: bool  # a dictation can start now
    reason: str | None  # why not: disabled | no_model | engine_missing
    model: str | None  # the model that would be used (chosen or default)
    state: str  # stopped | ready | busy
    queued: int  # transcriptions waiting behind the current one


def clean(text: str) -> str:
    """One line of text: Whisper's segments are joined with a space."""
    return " ".join(text.split())


def is_phantom(text: str) -> bool:
    """Text Whisper invents for silence or noise: a tag like «[Música]» or a known subtitle."""
    lowered = text.lower()
    return (
        not text
        or (len(text) <= 40 and bool(TAG.match(text)))
        or any(p in lowered for p in PHANTOMS)
    )


class DictationService:
    def __init__(self, sessions: sessionmaker[Session], data_dir: Path) -> None:
        self.sessions = sessions
        self.data_dir = Path(data_dir)
        self._lock = threading.Lock()
        self._server: WhisperServer | None = None
        self._pending = 0  # transcriptions in progress or waiting

    # ------------------------------------------------------------------------ the engine
    def _threads(self) -> int:
        return max(1, psutil.cpu_count(logical=False) or 4)

    def _server_for(self, engine: CatalogEntry, model: CatalogEntry) -> WhisperServer:
        """The `whisper-server` for this model: one at a time, kept between dictations."""
        with self._lock:
            if self._server is None or self._server.model.id != model.id:
                if self._server is not None:
                    self._server.stop()
                self._server = WhisperServer(self.data_dir, engine, model, self._threads())
            return self._server

    def stop(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.stop()
                self._server = None

    def _engine(self) -> CatalogEntry:
        found = catalog.entry(ENGINE_ID)
        if found is None:  # the catalog always has it
            raise DictationError(
                500, "engine_missing", "the dictation engine is not in the catalog"
            )
        return found

    def _ready(self, db: Session) -> tuple[config.DictationSettings, CatalogEntry, CatalogEntry]:
        """The settings, engine and model, or the `DictationError` that says what is missing."""
        settings = config.load(db)
        if not settings.enabled:
            raise DictationError(409, "disabled", "dictation is turned off in the settings")
        engine = self._engine()
        if not store.is_installed(self.data_dir, engine):
            raise DictationError(409, "engine_missing", "the speech engine is not downloaded")
        model = selection.active(db, self.data_dir, catalog.SPEECH)
        if model is None:
            raise DictationError(409, "no_model", "there is no speech model downloaded")
        return settings, engine, model

    # --------------------------------------------------------------------------- status
    def status(self) -> Status:
        with self.sessions() as db:
            settings = config.load(db)
            chosen = catalog.entry(selection.chosen(db).get(catalog.SPEECH) or "")
            try:
                self._ready(db)
                reason = None
            except DictationError as error:
                reason = error.code
        with self._lock:
            server, pending = self._server, self._pending
        state = server.state if server is not None else "stopped"
        return Status(
            enabled=settings.enabled,
            ready=reason is None,
            reason=reason,
            model=chosen.id if chosen else None,
            state="busy" if pending else state,
            queued=max(0, pending - 1),
        )

    def warm_up(self) -> None:
        """Loads the model now (the person has just started to talk). Errors are not reported:
        the transcription will report them."""
        with self.sessions() as db:
            _, engine, model = self._ready(db)
        try:
            self._server_for(engine, model).warm_up()
        except WhisperError as error:
            log.warning("dictation_warmup_failed", code=error.code, model=model.id)

    # ----------------------------------------------------------------------- transcribing
    def transcribe(self, wav: bytes) -> Transcript:
        with self.sessions() as db:
            settings, engine, model = self._ready(db)
            info = audio.inspect(wav, settings.max_seconds)
            if audio.is_silent(info):
                raise DictationError(422, "no_speech", "no speech was heard")
            prompt = hints.build(db, settings)
        server = self._server_for(engine, model)
        with self._lock:
            self._pending += 1
        try:
            text = server.transcribe(wav, settings.language, prompt)
        except WhisperError as error:
            log.warning("dictation_failed", code=error.code, model=model.id)
            raise DictationError(STATUS.get(error.code, 502), error.code, error.message) from error
        finally:
            with self._lock:
                self._pending -= 1
        text = clean(text)
        if is_phantom(text):
            raise DictationError(422, "no_speech", "no speech was heard")
        # Only numbers: never the text or the audio (they are the person's).
        log.info("dictation_done", seconds=round(info.seconds, 1), model=model.id, chars=len(text))
        return Transcript(text=text, seconds=info.seconds, model=model.id)
