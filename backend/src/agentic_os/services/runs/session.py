"""A live run: one agent CLI in a pseudo-terminal, shared by any number of viewers.

Threads:
- reader: blocks on the PTY, appends output to the log and the scrollback, feeds the
  emulated screen and hands each chunk to the asyncio loop for the viewers;
- ticker: every 250 ms accepts the folder-trust dialog and recomputes the activity.

Viewers are asyncio queues and are only touched from the event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agentic_os.models.agent import Cli
from agentic_os.models.run import Activity, RunStatus
from agentic_os.services import pty as pty_service
from agentic_os.services.pty import PtyProcess
from agentic_os.services.runs.launcher import LaunchSpec
from agentic_os.services.runs.screen import ScreenState

SCROLLBACK_LIMIT = 2 * 1024 * 1024  # characters kept in memory per run
VIEWER_BACKLOG_LIMIT = 4096  # queued messages before a slow viewer is dropped
BUSY_GRACE = 1.5  # seconds of recent output that still count as "busy"
TRUST_WINDOW = 90.0  # seconds after start during which the trust dialog is handled
STOP_TIMEOUT = 15.0
CONTINUE_MESSAGE = "Continúa con la tarea."

ESC, ENTER, CTRL_C, DOWN = "\x1b", "\r", "\x03", "\x1b[B"

Message = dict
StateCallback = Callable[[dict], None]


class ControlConflict(Exception):
    """Another viewer holds the control of the run."""


@dataclass
class Viewer:
    client_id: str
    queue: asyncio.Queue[Message | None] = field(default_factory=asyncio.Queue)


class RunSession:
    def __init__(
        self,
        run_id: str,
        cli: Cli,
        launch: LaunchSpec,
        cwd: str,
        log_path: Path,
        loop: asyncio.AbstractEventLoop,
        on_change: StateCallback,
        cols: int = 120,
        rows: int = 32,
    ) -> None:
        self.run_id = run_id
        self.cli = cli
        self.launch = launch
        self.cwd = cwd
        self.log_path = log_path
        self.loop = loop
        self.on_change = on_change
        self.cols, self.rows = cols, rows

        self.status = RunStatus.STARTING
        self.activity = Activity.IDLE
        self.controller: str | None = None
        self.exit_code: int | None = None
        self.started_at = 0.0

        self._pty: PtyProcess | None = None
        self._screen = ScreenState(cli, cols, rows)
        self._scrollback: list[str] = []
        self._scrollback_size = 0
        self._last_output = 0.0
        self._typed = False
        self._stop_requested = False
        self._trust_done = False
        self._finished = threading.Event()
        self._lock = threading.RLock()  # state + scrollback
        self._viewers: dict[str, Viewer] = {}

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("a", encoding="utf-8", newline="")
        self._pty = pty_service.spawn(
            self.launch.argv, self.cwd, self.launch.env, self.cols, self.rows
        )
        self.started_at = time.monotonic()
        self._set(status=RunStatus.RUNNING)
        threading.Thread(
            target=self._read_loop, name=f"run-{self.run_id}-reader", daemon=True
        ).start()
        threading.Thread(
            target=self._tick_loop, name=f"run-{self.run_id}-ticker", daemon=True
        ).start()

    @property
    def alive(self) -> bool:
        return not self._finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    def stop(self, timeout: float | None = None) -> None:
        """Graceful exit (/exit or double Ctrl+C), killing the process if it does not comply."""
        if not self.alive or self._pty is None:
            return
        self._stop_requested = True

        def run() -> None:
            pty = self._pty
            assert pty is not None
            with contextlib.suppress(Exception):
                if self.cli == Cli.CLAUDE:
                    pty.write(ESC)
                    time.sleep(0.5)
                    pty.write("/exit")
                    time.sleep(0.4)
                    pty.write(ENTER)
                else:
                    pty.write(CTRL_C)
                    time.sleep(0.5)
                    pty.write(CTRL_C)
            if not self._finished.wait(STOP_TIMEOUT if timeout is None else timeout):
                pty.terminate()

        threading.Thread(target=run, name=f"run-{self.run_id}-stop", daemon=True).start()

    def kill(self) -> None:
        self._stop_requested = True
        if self._pty is not None:
            self._pty.terminate()

    # ------------------------------------------------------------------ viewers
    def attach(self, client_id: str) -> tuple[str, Viewer]:
        """Registers a viewer (event loop only). Returns the scrollback snapshot first."""
        viewer = Viewer(client_id)
        with self._lock:
            snapshot = "".join(self._scrollback)
            self._viewers[client_id] = viewer
        return snapshot, viewer

    def detach(self, client_id: str) -> None:
        with self._lock:
            self._viewers.pop(client_id, None)

    @property
    def viewer_count(self) -> int:
        return len(self._viewers)

    def state_message(self) -> Message:
        return {
            "type": "state",
            "status": self.status.value,
            "activity": self.activity.value,
            "controller": self.controller,
        }

    def _broadcast(self, message: Message) -> None:
        """Event loop only."""
        with self._lock:
            viewers = list(self._viewers.values())
        for viewer in viewers:
            if viewer.queue.qsize() > VIEWER_BACKLOG_LIMIT:
                self.detach(viewer.client_id)
                viewer.queue.put_nowait(None)  # the client reconnects and gets a snapshot
            else:
                viewer.queue.put_nowait(message)

    def _publish(self, message: Message) -> None:
        """Any thread."""
        with contextlib.suppress(RuntimeError):  # loop closed during shutdown
            self.loop.call_soon_threadsafe(self._broadcast, message)

    # ------------------------------------------------------------------ input & control
    def write_input(self, client_id: str, data: str) -> bool:
        if client_id != self.controller or self._pty is None or not self.alive:
            return False
        self._typed = True
        self._pty.write(data)
        return True

    def resize(self, client_id: str, cols: int, rows: int) -> None:
        if self.controller is not None and client_id != self.controller:
            return
        cols, rows = max(20, min(cols, 400)), max(5, min(rows, 200))
        if (cols, rows) == (self.cols, self.rows) or self._pty is None:
            return
        self.cols, self.rows = cols, rows
        self._pty.resize(cols, rows)
        self._screen.resize(cols, rows)
        self.on_change({"cols": cols, "rows": rows})

    def take_control(self, client_id: str) -> None:
        with self._lock:
            if self.controller not in (None, client_id):
                raise ControlConflict(self.controller)
            if not self.alive:
                return
            first_take = self.controller is None
            self.controller = client_id
            self._typed = False
        if first_take and self._pty is not None:
            self._pty.write(ESC)  # interrupt the current turn, keep the session (ADR 0003)
        self._set(status=RunStatus.INTERVENING)

    def release_control(self, client_id: str) -> None:
        with self._lock:
            if self.controller != client_id:
                raise ControlConflict(self.controller)
            self.controller = None
            nudge = not self._typed
        if self.alive:
            self._set(status=RunStatus.RUNNING)
            if nudge and self._pty is not None:
                self._type_line(CONTINUE_MESSAGE)

    def _type_line(self, text: str) -> None:
        pty = self._pty
        assert pty is not None

        def run() -> None:
            with contextlib.suppress(Exception):
                pty.write(text)
                time.sleep(0.4)  # let the TUI render the text before submitting it
                pty.write(ENTER)

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------ threads
    def _read_loop(self) -> None:
        pty = self._pty
        assert pty is not None
        while True:
            chunk = pty.read()
            if not chunk:
                break
            with self._lock:
                self._log.write(chunk)
                self._log.flush()
                self._scrollback.append(chunk)
                self._scrollback_size += len(chunk)
                while self._scrollback_size > SCROLLBACK_LIMIT and len(self._scrollback) > 1:
                    self._scrollback_size -= len(self._scrollback.pop(0))
                self._last_output = time.monotonic()
            self._screen.feed(chunk)
            self._publish({"type": "output", "data": chunk})
        self._finish(pty)

    def _finish(self, pty: PtyProcess) -> None:
        deadline = time.monotonic() + 5
        while pty.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.exit_code = pty.exit_code
        with self._lock:
            self.controller = None
            self._log.close()
        status = RunStatus.STOPPED if self._stop_requested else RunStatus.EXITED
        self._set(status=status, activity=Activity.IDLE, exit_code=self.exit_code, ended=True)
        self._publish({"type": "exit", "code": self.exit_code, "status": status.value})
        self._finished.set()

    def _tick_loop(self) -> None:
        last_trust_action = 0.0
        while not self._finished.wait(0.25):
            now = time.monotonic()
            if not self._trust_done and now - self.started_at < TRUST_WINDOW:
                visible, selected = self._screen.trust_dialog()
                if visible and now - last_trust_action > 0.6 and self._pty is not None:
                    # Keys sent before the menu is interactive are dropped: keep trying.
                    self._pty.write(ENTER if selected else DOWN)
                    last_trust_action = now
                elif not visible and last_trust_action:
                    self._trust_done = True
            busy = self._screen.footer_busy() or now - self._last_output < BUSY_GRACE
            activity = Activity.BUSY if busy else Activity.IDLE
            if activity != self.activity and self.alive:
                self._set(activity=activity)

    # ------------------------------------------------------------------ state
    def _set(
        self,
        status: RunStatus | None = None,
        activity: Activity | None = None,
        exit_code: int | None = None,
        ended: bool = False,
    ) -> None:
        changes: dict = {}
        if status is not None and status != self.status:
            self.status = status
            changes["status"] = status
        if activity is not None and activity != self.activity:
            self.activity = activity
            changes["activity"] = activity
        if ended:
            changes["exit_code"] = exit_code
            changes["ended"] = True
        if status == RunStatus.RUNNING and "status" in changes:
            changes.setdefault("started", True)
        if changes:
            self.on_change(changes)
            self._publish(self.state_message())
