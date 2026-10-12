"""Keeps each run's usage up to date (phase 07, ADR 0011).

A single worker thread reads the transcripts, so neither a hook request nor the end of a run
waits on the disk. Reads are requested:
- at the end of every turn (`Stop`): live, partial figures;
- when the run ends: final figures (Claude writes its exact `cost-state` on close);
- at startup, for finished runs that were never read (runs from before phase 07).
Claude's status line sends the session's cost after every turn; it is stored as it arrives.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import utcnow
from agentic_os.models import ACTIVE_STATUSES, Cli, Run, UsageStatus
from agentic_os.services.usage.parsers import (
    COST_STATE,
    AgyReader,
    ClaudeReader,
    Usage,
)
from agentic_os.services.usage.paths import agy_transcript, claude_transcript

log = structlog.get_logger()

STATUS_LINE = "statusline"
# Claude writes `cost-state` while it closes: a final read that misses it is retried once.
FINAL_RETRY_DELAY = 2.0


def usage_payload(run: Run) -> dict:
    """The usage block of a run, as the API and the run's WebSocket send it."""
    return {
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "thinking_tokens": run.thinking_tokens,
        "cache_read_tokens": run.cache_read_tokens,
        "cache_creation_tokens": run.cache_creation_tokens,
        "cost_usd": run.cost_usd,
        "source": run.usage_source,
        "status": run.usage_status,
        "cli_version": run.cli_version,
        "models": run.usage_models or {},
        "read_at": run.usage_read_at.isoformat().replace("+00:00", "Z")
        if run.usage_read_at
        else None,
    }


@dataclass
class _Readers:
    cli: Cli
    main_path: Path | None = None
    main: ClaudeReader | AgyReader | None = None
    extras: dict[str, AgyReader] = field(default_factory=dict)

    def read(self, path: Path | None, extra_paths: list[str]) -> Usage | None:
        if path is not None and path != self.main_path:
            self.main_path = path
            self.main = ClaudeReader(path) if self.cli == Cli.CLAUDE else AgyReader(path)
        total = self.main.read() if self.main is not None else None
        for extra in extra_paths:  # agy native subagents
            reader = self.extras.setdefault(extra, AgyReader(Path(extra)))
            part = reader.read()
            if part is not None:
                total = part if total is None else total.add(part)
        return total


class UsageService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        publish: Callable[[str, dict], None] | None = None,
        claude_config_dir: Path | None = None,
        home: Path | None = None,
    ) -> None:
        self._db = sessions
        # Pushes {"type": "usage", ...} to the run's viewers (any thread).
        self.publish = publish or (lambda run_id, message: None)
        # Called after a run's usage changed (the daily limits are checked there).
        self.on_updated: Callable[[str], None] | None = None
        self._claude_config_dir = claude_config_dir
        self._home = home
        self._queue: queue.Queue[tuple[str, bool, bool] | None] = queue.Queue()
        self._readers: dict[str, _Readers] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ worker
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="usage", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout)
        self._thread = None

    def request(self, run_id: str, final: bool = False, retry: bool = True) -> None:
        """Asks for a read; any thread. Without a worker (tests), reads right away.
        `retry`: a final Claude read without `cost-state` is tried once more."""
        if self._thread is None:
            if self.refresh(run_id, final, last_try=not retry):
                self.refresh(run_id, final, last_try=True)
        else:
            self._queue.put((run_id, final, retry))

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Tests: until the queued reads are done."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return False

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                run_id, final, retry = item
                try:
                    if self.refresh(run_id, final, last_try=not retry):
                        time.sleep(FINAL_RETRY_DELAY)  # Claude may still be closing
                        self.refresh(run_id, final, last_try=True)
                except Exception:
                    log.exception("could not read the run's usage", run_id=run_id)
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------ hooks
    def note_transcript(self, run_id: str, path: str, own: bool) -> None:
        """A hook reported a transcript: the run's own, or (agy) a native subagent's."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            if own:
                if run.transcript_path != path:
                    run.transcript_path = path
                    db.commit()
            elif path not in (run.extra_transcripts or []) and path != run.transcript_path:
                run.extra_transcripts = [*(run.extra_transcripts or []), path]
                db.commit()

    def status_line(self, run_id: str, cost_usd: float | None, version: str | None) -> None:
        """Claude's status line: the session's cost so far (exact, from the CLI itself)."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None or run.usage_source == COST_STATE:
                return  # the final figures are already in
            changed = False
            if version and run.cli_version != version:
                run.cli_version, changed = version, True
            if cost_usd is not None and run.cost_usd != cost_usd:
                run.cost_usd, changed = cost_usd, True
                if run.usage_status == UsageStatus.PENDING:
                    run.usage_status = UsageStatus.PARTIAL
                run.usage_read_at = utcnow()
            if not changed:
                return
            db.commit()
            message = {"type": "usage", "run_id": run_id, "usage": usage_payload(run)}
        self.publish(run_id, message)
        if self.on_updated is not None:
            self.on_updated(run_id)

    # ------------------------------------------------------------------ reading
    def _transcript(self, run: Run) -> Path | None:
        if run.transcript_path:
            return Path(run.transcript_path)
        if not run.cli_session_id:
            return None
        if run.cli == Cli.CLAUDE:
            return claude_transcript(run.cwd, run.cli_session_id, self._claude_config_dir)
        return agy_transcript(run.cli_session_id, self._home)

    def refresh(self, run_id: str, final: bool = False, last_try: bool = True) -> bool:
        """Reads the run's transcripts and stores the figures. Returns True when a final read
        of Claude missed `cost-state` and is worth another try (`last_try` False)."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return False
            cli = Cli(run.cli)
            with self._lock:
                readers = self._readers.setdefault(run_id, _Readers(cli))
            usage = readers.read(self._transcript(run), list(run.extra_transcripts or []))
            before = usage_payload(run)
            if usage is not None:
                self._apply(run, usage)
            retry = False
            if final:
                exact = run.usage_source == COST_STATE or cli != Cli.CLAUDE
                if not exact and not last_try:
                    retry = True
                    run.usage_status = UsageStatus.PARTIAL
                elif usage is None and run.cost_usd is None:
                    run.usage_status = UsageStatus.UNAVAILABLE
                else:
                    run.usage_status = UsageStatus.FINAL
            elif usage is not None:
                run.usage_status = UsageStatus.PARTIAL
            run.usage_read_at = utcnow()
            after = usage_payload(run)
            db.commit()
        if not retry and final:
            with self._lock:
                self._readers.pop(run_id, None)
        before.pop("read_at")
        if {k: v for k, v in after.items() if k != "read_at"} != before:
            self.publish(run_id, {"type": "usage", "run_id": run_id, "usage": after})
            if self.on_updated is not None:
                self.on_updated(run_id)
        return retry

    @staticmethod
    def _apply(run: Run, usage: Usage) -> None:
        run.input_tokens = usage.input_tokens
        run.output_tokens = usage.output_tokens
        run.thinking_tokens = usage.thinking_tokens
        run.cache_read_tokens = usage.cache_read_tokens
        run.cache_creation_tokens = usage.cache_creation_tokens
        run.usage_models = usage.models
        if usage.source == COST_STATE:
            run.cost_usd = usage.cost_usd
            run.usage_source = COST_STATE
        else:
            # Claude: the cost so far comes from the status line (kept as it is).
            run.usage_source = usage.source

    # ------------------------------------------------------------------ backfill
    def backfill(self) -> int:
        """Queues a final read of every finished run never read (runs from before phase 07,
        or runs that ended while the backend was down)."""
        with self._db() as db:
            ids = list(
                db.scalars(
                    select(Run.id)
                    .where(
                        Run.usage_status.in_([UsageStatus.PENDING, UsageStatus.PARTIAL]),
                        Run.status.not_in([s.value for s in ACTIVE_STATUSES]),
                    )
                    .order_by(Run.created_at)
                )
            )
        for run_id in ids:
            self.request(run_id, final=True, retry=False)
        return len(ids)
