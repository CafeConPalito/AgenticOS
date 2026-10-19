"""Downloading models and engines: resumable, checked and cancellable (phase 14, block 3).

Each file goes to `<name>.part`; if the download is interrupted (or cancelled) the next attempt
asks the server for the rest with a `Range` request. When a file is complete its SHA-256 must be
the catalog's: a different file is deleted, never used. Only when every file is checked does the
`manifest.json` appear and the model count as installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import structlog

from agentic_os import __version__
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.localmodels import store
from agentic_os.services.localmodels.catalog import CatalogEntry, RemoteFile

log = structlog.get_logger()

CHUNK = 1024 * 1024
PROGRESS_INTERVAL = 0.25
FREE_MARGIN = 200 * 1024 * 1024  # leave this much free on the disk after the download
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60.0

ABSENT, PARTIAL, DOWNLOADING, READY, ERROR = "absent", "partial", "downloading", "ready", "error"


class DownloadError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class Cancelled(Exception):
    pass


@dataclass
class ModelState:
    id: str
    state: str
    done: int = 0
    total: int = 0
    error_code: str | None = None
    error_message: str | None = None
    bundled: bool = False  # it came inside the app: nothing to download, nothing to delete

    def as_dict(self) -> dict:
        return asdict(self)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


class DownloadManager:
    def __init__(
        self,
        data_dir: Path,
        events: KnowledgeEvents,
        http: Callable[[], httpx.Client] | None = None,
        token: Callable[[], str | None] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.events = events
        self._http = http or self._default_client
        self._token = token or (lambda: None)
        self._lock = threading.Lock()
        self._running: dict[str, threading.Thread] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._live: dict[str, ModelState] = {}  # downloading, or failed in this run

    @staticmethod
    def _default_client() -> httpx.Client:
        return httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            headers={"User-Agent": f"AgenticOS/{__version__}"},
        )

    # ------------------------------------------------------------------------ state
    def state(self, entry: CatalogEntry) -> ModelState:
        with self._lock:
            live = self._live.get(entry.id)
            if live is not None:
                return ModelState(**live.as_dict())
        if store.is_installed(self.data_dir, entry):
            return ModelState(
                entry.id, READY, entry.size, entry.size, bundled=store.is_bundled(entry)
            )
        have = store.partial_bytes(self.data_dir, entry)
        return ModelState(entry.id, PARTIAL if have else ABSENT, have, entry.size)

    def busy(self) -> bool:
        with self._lock:
            return any(t.is_alive() for t in self._running.values())

    def _publish(self, state: ModelState) -> None:
        self.events.model(state.as_dict())

    # ---------------------------------------------------------------------- control
    def start(self, entry: CatalogEntry) -> ModelState:
        """Starts (or continues) the download in a thread. Raises ApiError-like DownloadError."""
        with self._lock:
            running = self._running.get(entry.id)
            if running is not None and running.is_alive():
                raise DownloadError("already_downloading", "that download is already running")
            state = ModelState(
                entry.id, DOWNLOADING, store.partial_bytes(self.data_dir, entry), entry.size
            )
            self._live[entry.id] = state
            self._cancel[entry.id] = threading.Event()
            thread = threading.Thread(
                target=self._run, args=(entry,), name=f"download-{entry.id}", daemon=True
            )
            self._running[entry.id] = thread
        self._publish(state)
        thread.start()
        return state

    def cancel(self, entry: CatalogEntry) -> None:
        with self._lock:
            event = self._cancel.get(entry.id)
        if event is not None:
            event.set()

    def remove(self, entry: CatalogEntry) -> None:
        if self.state(entry).state == DOWNLOADING:
            raise DownloadError("downloading", "cancel the download first")
        if store.is_bundled(entry):
            raise DownloadError("bundled", "it is part of the app: it cannot be removed")
        store.remove(self.data_dir, entry)
        with self._lock:
            self._live.pop(entry.id, None)
        self._publish(self.state(entry))

    def join(self, entry: CatalogEntry, timeout: float = 30) -> None:
        """Waits for a download to end (tests)."""
        with self._lock:
            thread = self._running.get(entry.id)
        if thread is not None:
            thread.join(timeout)

    def stop(self) -> None:
        with self._lock:
            events, threads = list(self._cancel.values()), list(self._running.values())
        for event in events:
            event.set()
        for thread in threads:
            thread.join(timeout=5)

    # ------------------------------------------------------------------- the thread
    def _run(self, entry: CatalogEntry) -> None:
        cancel = self._cancel[entry.id]
        state = self._live[entry.id]
        last = [0.0]

        def report(done: int, force: bool = False) -> None:
            state.done = done
            now = time.monotonic()
            if force or now - last[0] >= PROGRESS_INTERVAL:
                last[0] = now
                self._publish(state)

        try:
            self._download(entry, cancel, report)
            store.write_manifest(self.data_dir, entry)
            log.info("local_model_ready", id=entry.id)
            with self._lock:
                self._live.pop(entry.id, None)
        except Cancelled:
            log.info("local_model_cancelled", id=entry.id)
            with self._lock:
                self._live.pop(entry.id, None)
        except DownloadError as error:
            log.warning("local_model_failed", id=entry.id, code=error.code, message=error.message)
            with self._lock:
                self._live[entry.id] = ModelState(
                    entry.id, ERROR, state.done, entry.size, error.code, error.message
                )
        except Exception as error:
            log.exception("local_model_crashed", id=entry.id)
            with self._lock:
                self._live[entry.id] = ModelState(
                    entry.id,
                    ERROR,
                    state.done,
                    entry.size,
                    "network",
                    f"{type(error).__name__}: {error}",
                )
        finally:
            with self._lock:
                self._running.pop(entry.id, None)
                self._cancel.pop(entry.id, None)
            self._publish(self.state(entry))

    def _download(
        self, entry: CatalogEntry, cancel: threading.Event, report: Callable[..., None]
    ) -> None:
        folder = store.downloaded_folder(self.data_dir, entry)
        folder.mkdir(parents=True, exist_ok=True)
        missing = entry.size - store.partial_bytes(self.data_dir, entry)
        free = shutil.disk_usage(folder).free
        if free < missing + FREE_MARGIN:
            raise DownloadError(
                "no_space", f"{missing // 2**20} MB needed, {free // 2**20} MB free"
            )
        done = 0
        with self._http() as client:
            for remote in entry.files:
                target = folder / remote.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not (target.is_file() and self._valid(target, remote, cancel)):
                    self._fetch(client, entry, remote, target, cancel, done, report)
                done += remote.size
                report(done, force=True)
        if entry.unpack:
            self._unpack(folder, entry.unpack)

    @staticmethod
    def _valid(path: Path, remote: RemoteFile, cancel: threading.Event) -> bool:
        """A file left complete by an earlier attempt that did not reach the manifest."""
        if path.stat().st_size != remote.size:
            return False
        if cancel.is_set():
            raise Cancelled
        return sha256_of(path) == remote.sha256

    def _headers(self, url: str, entry: CatalogEntry, have: int) -> dict[str, str]:
        headers: dict[str, str] = {}
        if have:
            headers["Range"] = f"bytes={have}-"
        # The token goes only to Hugging Face, and only when the model asks for an account.
        if entry.needs_account and url.startswith("https://huggingface.co/"):
            token = self._token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _fetch(
        self,
        client: httpx.Client,
        entry: CatalogEntry,
        remote: RemoteFile,
        target: Path,
        cancel: threading.Event,
        before: int,
        report: Callable[..., None],
    ) -> None:
        part = target.with_name(target.name + store.PART)
        failure = DownloadError("network", "no address worked")
        for url in remote.urls:
            have = part.stat().st_size if part.is_file() else 0
            if have > remote.size:
                part.unlink()
                have = 0
            try:
                if have < remote.size:
                    self._stream(client, entry, url, part, have, remote, cancel, before, report)
                break
            except DownloadError as error:
                failure = error
                if error.code in ("http_401", "http_403"):
                    break  # another mirror would not accept us either
        else:
            raise failure
        if part.stat().st_size != remote.size or sha256_of(part) != remote.sha256:
            part.unlink(missing_ok=True)
            raise DownloadError("checksum", f"{remote.name} is not the expected file")
        part.replace(target)

    def _stream(
        self,
        client: httpx.Client,
        entry: CatalogEntry,
        url: str,
        part: Path,
        have: int,
        remote: RemoteFile,
        cancel: threading.Event,
        before: int,
        report: Callable[..., None],
    ) -> None:
        try:
            with client.stream("GET", url, headers=self._headers(url, entry, have)) as response:
                if response.status_code == 416:  # nothing left to ask for
                    return
                if response.status_code >= 400:
                    raise DownloadError(
                        f"http_{response.status_code}", f"HTTP {response.status_code}"
                    )
                if response.status_code == 200 and have:  # the server ignored Range: from the top
                    have = 0
                mode = "ab" if have else "wb"
                with part.open(mode) as out:
                    written = have
                    for block in response.iter_bytes(CHUNK):
                        if cancel.is_set():
                            raise Cancelled
                        out.write(block)
                        written += len(block)
                        report(before + written)
        except httpx.HTTPError as error:
            raise DownloadError("network", f"{type(error).__name__}: {error}"[:300]) from error

    @staticmethod
    def _unpack(folder: Path, archive: str) -> None:
        """Unpacks an engine's zip into `<folder>/bin` (refusing paths that escape it) and removes
        the zip."""
        base = (folder / "bin").resolve()
        try:
            with zipfile.ZipFile(folder / archive) as bundle:
                for member in bundle.infolist():
                    destination = (base / member.filename).resolve()
                    if base != destination and base not in destination.parents:
                        raise DownloadError(
                            "unpack", f"unsafe path in the archive: {member.filename}"
                        )
                bundle.extractall(base)
        except zipfile.BadZipFile as error:
            raise DownloadError("unpack", f"damaged archive: {error}") from error
        with contextlib.suppress(OSError):
            (folder / archive).unlink()
