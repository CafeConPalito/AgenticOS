"""Long git operations that report progress and can be cancelled: fetch, pull, push, clone…
(phase 12, ADR 0017).

A job runs in a thread. Git writes its progress on stderr ending each update with a carriage
return («Receiving objects:  45% (45/100)»), so stderr is read in pieces and split on `\\r`
and `\\n`. Cancelling kills the whole process tree (git starts helpers: ssh, credential
managers, `git-remote-https`).
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import structlog

from agentic_os.db.base import utcnow
from agentic_os.schemas.git import JobState
from agentic_os.services import proc
from agentic_os.services.gitx.errors import classify, last_line
from agentic_os.services.gitx.runner import Repo, environment

log = structlog.get_logger()

PROGRESS = re.compile(r"^(?:remote: )?(?P<phase>[A-Za-z][A-Za-z ]+?):\s+(?P<pct>\d+)%")
KEEP_FINISHED = timedelta(minutes=10)
EVENT_EVERY = 0.15  # seconds between progress events of one job
TAIL = 40  # lines of output kept for the error details


@dataclass
class _Job:
    state: JobState
    process: subprocess.Popen[bytes] | None = None
    tail: list[str] = field(default_factory=list)
    cancelled: bool = False
    last_event: float = 0.0


Listener = Callable[[dict], None]


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()
        self.listener: Listener | None = None

    # ------------------------------------------------------------------ public
    def start(
        self,
        repo: Repo,
        repo_id: str,
        kind: str,
        args: list[str],
        *,
        interactive: bool = True,
        exclusive: bool = False,
        timeout: float = 1800,
    ) -> JobState:
        """Starts `git <args>` in the background. `exclusive`: it changes the work tree or the
        branches, so it takes the repository's write lock for its whole run."""
        state = JobState(
            id=uuid.uuid4().hex,
            repo_id=repo_id,
            kind=kind,
            status="running",
            started_at=utcnow(),
        )
        job = _Job(state)
        with self._lock:
            self._forget_old()
            self._jobs[state.id] = job
        threading.Thread(
            target=self._run,
            args=(job, repo, args, interactive, exclusive, timeout),
            name=f"git-{kind}-{state.id[:6]}",
            daemon=True,
        ).start()
        self._emit(job, force=True)
        return state.model_copy()

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.state.model_copy() if job else None

    def active(self, repo_id: str | None = None) -> list[JobState]:
        with self._lock:
            return [
                j.state.model_copy()
                for j in self._jobs.values()
                if j.state.status == "running" and (repo_id is None or j.state.repo_id == repo_id)
            ]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.state.status != "running":
            return False
        job.cancelled = True
        if job.process is not None:
            kill_tree(job.process)
        return True

    def shutdown(self) -> None:
        """Cancels what is still running (the app is closing)."""
        for state in self.active():
            self.cancel(state.id)

    # ------------------------------------------------------------------ internals
    def _forget_old(self) -> None:
        cutoff = utcnow() - KEEP_FINISHED
        for job_id in [
            i
            for i, j in self._jobs.items()
            if j.state.ended_at is not None and j.state.ended_at < cutoff
        ]:
            del self._jobs[job_id]

    def _emit(self, job: _Job, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - job.last_event < EVENT_EVERY:
            return
        job.last_event = now
        if self.listener is not None:
            with contextlib.suppress(Exception):  # a listener must never break a job
                self.listener({"type": "job", "job": job.state.model_dump(mode="json")})

    def _run(
        self,
        job: _Job,
        repo: Repo,
        args: list[str],
        interactive: bool,
        exclusive: bool,
        timeout: float,
    ) -> None:
        lock = repo.write() if exclusive else contextlib.nullcontext()
        code: int | None = None
        output = ""
        try:
            with lock:
                if job.cancelled:
                    code = -1
                else:
                    code, output = self._execute(job, repo, args, interactive, timeout)
        except Exception as error:  # a job that breaks is a failed job, not a dead thread
            log.exception("git job crashed", kind=job.state.kind)
            job.state.message = str(error)
            job.state.error_code = "git_failed"
            code = -2
        self._finish(job, code, output)

    def _execute(
        self, job: _Job, repo: Repo, args: list[str], interactive: bool, timeout: float
    ) -> tuple[int, str]:
        flags = proc.NO_WINDOW
        if sys.platform == "win32":
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            repo.command(*args),
            env=environment(interactive),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
        )
        job.process = process
        if job.cancelled:  # cancelled while starting
            kill_tree(process)
        stdout: list[bytes] = []
        reader = threading.Thread(
            target=lambda: stdout.append(process.stdout.read() if process.stdout else b""),
            daemon=True,
        )
        reader.start()
        timer = threading.Timer(timeout, lambda: kill_tree(process))
        timer.start()
        try:
            self._read_progress(job, process)
            process.wait()
        finally:
            timer.cancel()
        reader.join(timeout=5)
        text = "\n".join(job.tail)
        return process.returncode, text + (
            "\n" + stdout[0].decode("utf-8", "replace") if stdout else ""
        )

    def _read_progress(self, job: _Job, process: subprocess.Popen[bytes]) -> None:
        pending = ""
        stream = process.stderr
        assert stream is not None
        while True:
            chunk = stream.read1(4096)  # type: ignore[attr-defined]
            if not chunk:
                break
            pending += chunk.decode("utf-8", "replace")
            *lines, pending = re.split(r"[\r\n]", pending)
            for line in lines:
                self._line(job, line.strip())
        if pending.strip():
            self._line(job, pending.strip())

    def _line(self, job: _Job, line: str) -> None:
        if not line:
            return
        match = PROGRESS.match(line)
        if match:
            job.state.phase = match.group("phase").strip()
            job.state.percent = int(match.group("pct"))
            self._emit(job)
            return
        job.tail.append(line)
        del job.tail[:-TAIL]
        job.state.message = line
        self._emit(job)

    def _finish(self, job: _Job, code: int | None, output: str) -> None:
        state = job.state
        if job.cancelled:
            state.status = "cancelled"
        elif code == 0:
            state.status, state.percent = "succeeded", 100
            state.error_code = None
        else:
            state.status = "failed"
            if state.error_code is None:
                state.error_code = classify(output)
            state.message = last_line(output) or state.message
        state.ended_at = utcnow()
        self._emit(job, force=True)
        if self.listener is not None:
            with contextlib.suppress(Exception):
                self.listener({"type": "repo_changed", "repo_id": state.repo_id})


def kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Ends a process and everything it started."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=proc.NO_WINDOW,
            )
    else:
        with contextlib.suppress(OSError):
            process.kill()
