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

import structlog

from agentic_os.models.agent import Cli
from agentic_os.models.run import Activity, RunStatus
from agentic_os.services import pty as pty_service
from agentic_os.services.hooks import HookEffect
from agentic_os.services.pty import PtyProcess
from agentic_os.services.runs.launcher import LaunchSpec
from agentic_os.services.runs.screen import PermissionDialog, ScreenState

log = structlog.get_logger(__name__)

SCROLLBACK_LIMIT = 2 * 1024 * 1024  # characters kept in memory per run
VIEWER_BACKLOG_LIMIT = 4096  # queued messages before a slow viewer is dropped
BUSY_GRACE = 1.5  # seconds of recent output that still count as "busy"
TRUST_WINDOW = 90.0  # seconds after start during which the trust dialog is handled
STOP_TIMEOUT = 15.0  # to get the CLI to accept the exit
EXIT_GRACE = 10.0  # once accepted, time it gets to close by itself (agy/Claude need ~6 s)
EXIT_ARM_DELAY = 0.5  # agy ignores a second Ctrl+C sent right after its notice appears
MCP_WAIT = 60.0  # agy: send the prompt anyway if its input never looked ready by then
MCP_PROBE_WAIT = 15.0  # agy: how long `/mcp` gets to connect our MCP server
PROMPT_CONFIRM = 10.0  # agy: retype the prompt once if no turn started meanwhile
COMPLETE_CLOSE_AFTER = 60.0  # after complete_task, close even if no end-of-turn hook arrives
CONTINUE_MESSAGE = "Continúa con la tarea."

ESC, ENTER, CTRL_C, DOWN = "\x1b", "\r", "\x03", "\x1b[B"
DELIVERY_GAP = 2.0  # seconds between two messages typed into the CLI
DELIVERY_CONFIRM = 20.0  # a typed message must start a turn within this time
MESSAGE_LIMIT = 1800  # characters typed in one message (the rest: get_context)
PERMISSION_SHOW = 0.5  # seconds a permission dialog must be on screen to be reported
PERMISSION_GONE = 1.5  # seconds it must be missing to count as answered
QUOTA_GONE = 30.0  # seconds the quota notice must be gone before a new one is reported
PERMISSION_QUIET = 1.0  # after answering one, the screen is not read for dialogs

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
        deferred_prompt: str | None = None,
        on_end: Callable[[], None] | None = None,
        on_system_event: Callable[..., None] | None = None,
        on_permission: Callable[[PermissionDialog], None] | None = None,
        on_permission_gone: Callable[[], None] | None = None,
        on_quota: Callable[[str], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.cli = cli
        self.launch = launch
        self.cwd = cwd
        self.log_path = log_path
        self.loop = loop
        self.on_change = on_change
        self.cols, self.rows = cols, rows
        # agy: the prompt is typed once its MCP server is connected (ADR 0004).
        self.deferred_prompt = deferred_prompt
        self.on_end = on_end
        self.on_system_event = on_system_event or (lambda *args, **kwargs: None)
        # A permission dialog of the CLI appeared / went away (Inbox «Aprobación», phase 06).
        self.on_permission = on_permission or (lambda dialog: None)
        self.on_permission_gone = on_permission_gone or (lambda: None)
        # The CLI says it ran out of quota / hit its usage limit (Inbox «Cuota agotada»).
        self.on_quota = on_quota or (lambda notice: None)

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
        self._stopping = False
        self._ended = False
        self.completed = False  # the agent called complete_task
        self._user_stop = False  # Parar / app closing: never reported as completed
        self._completed_at = 0.0
        self._closing_completed = False
        self._prompt_sent = False
        self._turn_seen = threading.Event()
        self._mcp_dialog_at = 0.0
        self._mcp_probe_at = 0.0
        self._human_notified: set[str] = set()
        self._closing_mcp_panel = False
        self._mcp_panel_closed_at = 0.0
        self._hooks_seen = False  # once hooks arrive they drive the activity, not the screen
        self._in_turn = False
        self.mcp_connected = False
        self._trust_done = False
        # Messages for the agent (answers, subagent results), typed when it waits for input.
        self._deliveries: list[str] = []
        self._delivered_at = 0.0
        self._permission_sig: str | None = None  # the dialog currently reported
        self._permission_candidate: str | None = None
        self._permission_seen_at = 0.0
        self._permission_missing_at = 0.0
        self._permission_quiet_until = 0.0
        self._quota_reported: str | None = None
        self._quota_missing_at = 0.0
        self._finished = threading.Event()
        self._lock = threading.RLock()  # control + scrollback
        self._state_lock = threading.RLock()  # status/activity changes and their persistence
        self._viewers: dict[str, Viewer] = {}

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("a", encoding="utf-8", newline="")
        try:
            self._pty = pty_service.spawn(
                self.launch.argv, self.cwd, self.launch.env, self.cols, self.rows
            )
        except Exception:
            self._log.close()
            raise
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

    def stop(self, timeout: float | None = None, user: bool = True) -> None:
        """Graceful exit (/exit or double Ctrl+C), killing the process if it does not comply.
        `user=False`: Agentic OS closes a completed run (it then ends as completed)."""
        if user:
            self._user_stop = True
        with self._lock:
            # A second stop (double click, app closing meanwhile) would interleave its keys.
            if not self.alive or self._pty is None or self._stopping:
                return
            self._stopping = True
        self._stop_requested = True
        limit = STOP_TIMEOUT if timeout is None else timeout

        def run() -> None:
            pty = self._pty
            assert pty is not None
            deadline = time.monotonic() + limit
            accepted = False
            try:
                accepted = self._request_exit(pty, deadline)
            except Exception:
                log.exception("graceful stop failed", run_id=self.run_id)
            # A CLI that accepted the exit is closing by itself: give it time instead of killing.
            wait = EXIT_GRACE if accepted else max(0.0, deadline - time.monotonic())
            if not self._finished.wait(wait):
                log.warning("exit timed out, terminating", run_id=self.run_id)
                with contextlib.suppress(OSError):  # it may be exiting right now
                    pty.terminate()

        threading.Thread(target=run, name=f"run-{self.run_id}-stop", daemon=True).start()

    def _request_exit(self, pty: PtyProcess, deadline: float) -> bool:
        """Sends the CLI's exit keys until it acknowledges them (True) or time runs out. The
        TUIs drop keys while they are busy (e.g. Claude Code right after a turn), so every
        attempt is verified on screen; agy also needs its second Ctrl+C after the "press ctrl+c
        again" notice, and a first Ctrl+C during a turn only interrupts it."""
        attempt = 0
        while time.monotonic() < deadline and not self._finished.is_set():
            attempt += 1
            log.info("requesting exit", run_id=self.run_id, cli=self.cli.value, attempt=attempt)
            if self.cli == Cli.CLAUDE:
                pty.write(ESC)
                time.sleep(0.5)
                pty.write("/exit")
                time.sleep(0.4)
                pty.write(ENTER)
            else:
                pty.write(CTRL_C)
                if self._wait_screen(self._screen.exit_armed, 3, deadline):
                    time.sleep(EXIT_ARM_DELAY)
                    pty.write(CTRL_C)
            if self._wait_screen(self._screen.exit_acknowledged, 3, deadline):
                log.info("exit acknowledged", run_id=self.run_id, attempt=attempt)
                return True
        return False

    def _wait_screen(self, check: Callable[[], bool], seconds: float, deadline: float) -> bool:
        """Waits until `check()` holds on the screen (or the process ended)."""
        end = min(time.monotonic() + seconds, deadline)
        while time.monotonic() < end:
            if self._finished.is_set() or check():
                return True
            time.sleep(0.1)
        return False

    def kill(self) -> None:
        self._stop_requested = True
        if self._pty is not None:
            with contextlib.suppress(OSError):  # it may be exiting right now
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
            held_control = self.controller == client_id
        # A view that leaves (closed, reloaded, navigated away) cannot keep the agent paused:
        # nobody else could take the control, and a reloaded view comes back with a new id.
        if held_control:
            with contextlib.suppress(ControlConflict):
                self.release_control(client_id)

    @property
    def viewer_count(self) -> int:
        return len(self._viewers)

    def state_message(self) -> Message:
        return {
            "type": "state",
            "status": self.status.value,
            "activity": self.activity.value,
            "controller": self.controller,
            "cols": self.cols,
            "rows": self.rows,
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

    def emit(self, message: Message) -> None:
        """Pushes a message (e.g. an event) to every viewer; any thread."""
        self._publish(message)

    def on_hook(self, effect: HookEffect) -> bool:
        """Applies a CLI hook. True when it marks a turn boundary (start or end)."""
        self._hooks_seen = True
        boundary = False
        if effect.turn_started:
            self._turn_seen.set()
            if not self._in_turn:
                self._in_turn = boundary = True
        if effect.turn_ended:
            self._in_turn, boundary = False, True
        if effect.activity is not None and self.alive:
            self._set(activity=effect.activity)
        return boundary

    def after_turn_end(self) -> None:
        """Called once the end-of-turn event is recorded: closes a completed run (so the
        events read «Fin de turno» → «cerrando»)."""
        if self.completed:
            self._close_completed("turn_end")

    def on_mcp_connected(self) -> None:
        self.mcp_connected = True

    def mark_completed(self) -> None:
        """complete_task: Agentic OS closes the CLI when the current turn ends (or after
        COMPLETE_CLOSE_AFTER if no end-of-turn hook arrives)."""
        if not self.completed:
            self.completed = True
            self._completed_at = time.monotonic()
            if not self._in_turn and self._hooks_seen:
                self._close_completed("idle")

    def _close_completed(self, reason: str) -> None:
        # Never under a human who took the control: it closes after they hand it back.
        if self._closing_completed or not self.alive or self.controller is not None:
            return
        self._closing_completed = True
        self.stop(user=False)
        self.on_system_event("closing", reason)

    def _deferred_prompt_step(self, now: float) -> None:
        """agy connects its plugin's MCP server lazily: once its input is ready, `/mcp` makes
        it connect (verified with agy 1.3.3), so the model sees our tools from the first turn.
        Then the panel is closed and the prompt typed. Typed too early, an Enter would answer
        a dialog (e.g. «No, exit»), so it is never typed blind: if agy's input never looks
        ready, the human is told instead."""
        if self.controller is not None:
            return  # the human is typing in this terminal
        if self._mcp_probe_at == 0.0:
            if self.mcp_connected and self._screen.ready_for_prompt():
                self._send_deferred_prompt(mcp_timeout=False)
            elif self._screen.ready_for_prompt():
                self._mcp_probe_at = now
                self._type_line("/mcp")
                self.on_system_event("mcp_probe")
            elif now - self.started_at > MCP_WAIT and "prompt_not_sent" not in self._human_notified:
                self._human_notified.add("prompt_not_sent")
                self.on_system_event("waiting_for_human", "prompt_not_sent")
            return
        timed_out = now - self._mcp_probe_at > MCP_PROBE_WAIT
        if (self.mcp_connected or timed_out) and not self._closing_mcp_panel:
            self._closing_mcp_panel = True
            if self._pty is not None:
                with contextlib.suppress(Exception):
                    self._pty.write(ESC)  # close the /mcp panel
            self._mcp_panel_closed_at = now
            return
        if self._closing_mcp_panel and now - self._mcp_panel_closed_at > 0.8:
            self._send_deferred_prompt(mcp_timeout=not self.mcp_connected)

    def _send_deferred_prompt(self, mcp_timeout: bool) -> None:
        """agy: types the prompt once its MCP server is connected. It is typed once: retyping
        could submit it twice (the first copy may still be in the input). If no turn starts,
        the human is told."""
        self._prompt_sent = True
        prompt = self.deferred_prompt or ""
        pty = self._pty

        def run() -> None:
            if mcp_timeout:
                self.on_system_event("mcp_timeout")
            if pty is None or not self.alive:
                return
            with contextlib.suppress(Exception):
                pty.write(prompt)
                time.sleep(0.4)  # let the TUI render the text before submitting it
                pty.write(ENTER)
            self.on_system_event("prompt_sent")
            if not self._turn_seen.wait(PROMPT_CONFIRM) and self.alive:
                self.on_system_event("waiting_for_human", "prompt_not_started")

        threading.Thread(target=run, name=f"run-{self.run_id}-prompt", daemon=True).start()

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
        # Passive viewers (the dock) adopt the PTY size instead of imposing theirs.
        self._publish(self.state_message())

    def take_control(self, client_id: str) -> None:
        with self._lock:
            if self.controller not in (None, client_id):
                raise ControlConflict(self.controller)
            if not self.alive:
                return
            first_take = self.controller is None
            self.controller = client_id
            self._typed = False
        # Esc would answer an open permission dialog («No»): leave it for the human.
        if first_take and self._pty is not None and self._screen.permission_dialog() is None:
            self._pty.write(ESC)  # interrupt the current turn, keep the session (ADR 0003)
            # An interrupted turn fires no end-of-turn hook (Claude Code): close it here.
            self._in_turn = False
            self._set(activity=Activity.IDLE)
        self._set(status=RunStatus.INTERVENING)

    def release_control(self, client_id: str) -> None:
        with self._lock:
            if self.controller != client_id:
                raise ControlConflict(self.controller)
            self.controller = None
            nudge = not self._typed
        if self.alive:
            self._set(status=RunStatus.RUNNING)
            if self.completed:
                self._completed_at = time.monotonic()  # a new window after the human's turn
                if nudge:
                    self._close_completed("released")  # the task was done: no nudge
                return
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
        try:
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
        except Exception:
            # Disk full, an escape sequence pyte cannot parse…: end the run instead of
            # leaving it "alive" forever with nobody reading the PTY.
            log.exception("run reader failed", run_id=self.run_id)
            with contextlib.suppress(OSError):
                pty.terminate()
        finally:
            self._finish(pty)

    def _finish(self, pty: PtyProcess) -> None:
        deadline = time.monotonic() + 5
        while pty.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.exit_code = pty.exit_code
        with self._lock:
            self.controller = None
            with contextlib.suppress(OSError):
                self._log.close()
        if self.completed and self._closing_completed and not self._user_stop:
            status = RunStatus.COMPLETED  # complete_task and Agentic OS closed the CLI
        elif self._stop_requested:
            status = RunStatus.STOPPED
        else:
            status = RunStatus.EXITED
        self._set(status=status, activity=Activity.IDLE, exit_code=self.exit_code, ended=True)
        self._publish({"type": "exit", "code": self.exit_code, "status": status.value})
        if self.on_end is not None:
            try:
                self.on_end()
            except Exception:
                log.exception("run cleanup failed", run_id=self.run_id)
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
            if self.deferred_prompt and not self._prompt_sent:
                self._deferred_prompt_step(now)
            if self.cli == Cli.AGY and self.controller is None:
                self._approve_agentic_os_tool(now)
            self._permission_step(now)
            self._quota_step(now)
            self._delivery_step(now)
            human = self._screen.waiting_for_human()
            if human is not None and human not in self._human_notified:
                self._human_notified.add(human)
                self.on_system_event("waiting_for_human", human)
            if (
                self.completed
                and not self._closing_completed
                and now - self._completed_at > COMPLETE_CLOSE_AFTER
            ):
                self._close_completed("timeout")
            if self._hooks_seen:
                continue  # the hooks report turn start/end exactly
            busy = self._screen.footer_busy() or now - self._last_output < BUSY_GRACE
            activity = Activity.BUSY if busy else Activity.IDLE
            if activity != self.activity and self.alive:
                self._set(activity=activity)

    def _permission_step(self, now: float) -> None:
        """Reports permission dialogs as they appear and go. TUIs redraw: a dialog must be
        seen for PERMISSION_SHOW s to count, and missing for PERMISSION_GONE s to be gone."""
        if now < self._permission_quiet_until:
            return  # an answered dialog may still be drawn for a moment
        dialog = self._screen.permission_dialog()
        if dialog is not None:
            self._permission_missing_at = 0.0
            if dialog.signature == self._permission_sig:
                return
            if self._permission_candidate != dialog.signature:
                self._permission_candidate, self._permission_seen_at = dialog.signature, now
                return
            if now - self._permission_seen_at >= PERMISSION_SHOW:
                if self._permission_sig is not None:
                    self.on_permission_gone()
                self._permission_sig = dialog.signature
                self.on_permission(dialog)
            return
        self._permission_candidate = None
        if self._permission_sig is None:
            return
        if self._permission_missing_at == 0.0:
            self._permission_missing_at = now
        elif now - self._permission_missing_at >= PERMISSION_GONE:
            self._permission_sig = None
            self._permission_missing_at = 0.0
            self.on_permission_gone()

    def _quota_step(self, now: float) -> None:
        """Reports the CLI's out-of-quota notice once. After it has been gone for a while, a
        new notice is reported again."""
        notice = self._screen.quota_notice()
        if notice is not None:
            self._quota_missing_at = 0.0
            if self._quota_reported is None:
                self._quota_reported = notice
                self.on_quota(notice)
            return
        if self._quota_reported is None:
            return
        if self._quota_missing_at == 0.0:
            self._quota_missing_at = now
        elif now - self._quota_missing_at >= QUOTA_GONE:
            self._quota_reported, self._quota_missing_at = None, 0.0

    def deliver(self, text: str) -> None:
        """Queues a message for the agent; it is typed as soon as the CLI waits for input."""
        line = " / ".join(part.strip() for part in text.splitlines() if part.strip())
        if len(line) > MESSAGE_LIMIT:
            line = line[: MESSAGE_LIMIT - 60] + "… (el resto está en get_context)"
        with self._lock:
            self._deliveries.append(line)

    def waiting_for_input(self) -> bool:
        """The CLI waits for the next message: no turn running, no dialog, no human typing."""
        if not self.alive or self._pty is None or self.controller is not None:
            return False
        if self.deferred_prompt and not self._prompt_sent:
            return False  # agy: its first prompt goes first
        if self._screen.permission_dialog() is not None or self._screen.trust_dialog()[0]:
            return False
        if self._hooks_seen:
            if self._in_turn:
                return False
        elif self._screen.footer_busy():
            return False
        return self.cli != Cli.AGY or self._screen.ready_for_prompt()

    def _delivery_step(self, now: float) -> None:
        if not self._deliveries or now - self._delivered_at < DELIVERY_GAP:
            return
        if not self.waiting_for_input():
            return
        with self._lock:
            text = self._deliveries.pop(0)
        self._delivered_at = now
        self._turn_seen.clear()
        self._type_line(text)
        self.on_system_event("message_sent", text[:200])

        def confirm() -> None:
            if not self._turn_seen.wait(DELIVERY_CONFIRM) and self.alive:
                self.on_system_event("waiting_for_human", "message_not_started")

        threading.Thread(target=confirm, name=f"run-{self.run_id}-msg", daemon=True).start()

    def answer_permission(self, approve: bool) -> bool:
        """Answers the CLI's permission dialog (Enter = «Yes», Esc = «No»). False if no dialog
        is on screen any more."""
        pty = self._pty
        if pty is None or not self.alive or self._screen.permission_dialog() is None:
            return False
        with contextlib.suppress(Exception):
            pty.write(ENTER if approve else ESC)
        # This dialog is answered: report it gone, and count the next one (even if it looks the
        # same, e.g. two «Do you want to proceed?» in a row) as a new request.
        if self._permission_sig is not None:
            self._permission_sig = None
            self._permission_candidate = None
            self._permission_missing_at = 0.0
            self.on_permission_gone()
        self._permission_quiet_until = time.monotonic() + PERMISSION_QUIET
        return True

    def _approve_agentic_os_tool(self, now: float) -> None:
        """agy asks before every MCP call unless autonomous, and no project or plugin file can
        pre-approve tools (phase 04, task 1): approve *our* tools for the conversation from the
        screen. Any other permission dialog is left to the human."""
        request = self._screen.agentic_os_tool_request()
        if request is None or self._pty is None or now - self._mcp_dialog_at < 0.6:
            return
        _tool, always_selected = request
        self._pty.write(ENTER if always_selected else DOWN)
        self._mcp_dialog_at = now + (1.0 if always_selected else 0.0)

    # ------------------------------------------------------------------ state
    def _set(
        self,
        status: RunStatus | None = None,
        activity: Activity | None = None,
        exit_code: int | None = None,
        ended: bool = False,
    ) -> None:
        with self._state_lock:
            # After the final update nothing may overwrite it (a late take_control, the
            # ticker seeing the last output as "busy"…).
            if self._ended:
                return
            self._ended = ended
            self._apply(status, activity, exit_code, ended)

    def _apply(
        self,
        status: RunStatus | None,
        activity: Activity | None,
        exit_code: int | None,
        ended: bool,
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
