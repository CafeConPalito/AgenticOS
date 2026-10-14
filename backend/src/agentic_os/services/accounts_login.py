"""Logging an account in from the app (phase 10, ADR 0014).

The login of a CLI is interactive: it opens the browser and, when it cannot, prints a URL and
waits for a code. So it runs in a pseudo-terminal the person sees (the same WebSocket protocol as
a run's terminal) and not in the background. When the process ends, the account's session is
checked again.

- Claude Code: `claude auth login --claudeai [--email <email>]`, with the account's own
  `CLAUDE_CONFIG_DIR`: the login lands in its folder and `~/.claude` is not touched.
- agy has no login command: its TUI offers the login when nobody is logged in, so it opens the
  TUI for the person to sign in and leave.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

import structlog

from agentic_os.errors import ApiError
from agentic_os.models import Cli, CliAccount
from agentic_os.services import accounts as account_ops
from agentic_os.services.pty import PtyProcess, spawn
from agentic_os.services.runs.launcher import clean_env, resolve_executable
from agentic_os.services.runs.session import SCROLLBACK_LIMIT, VIEWER_BACKLOG_LIMIT, Viewer

log = structlog.get_logger()

# A login nobody finishes must not keep a CLI process forever.
LOGIN_TIMEOUT = 15 * 60.0


def login_argv(
    account: CliAccount, overrides: Mapping[str, list[str]], email: str = ""
) -> list[str]:
    prefix = resolve_executable(Cli(account.cli), overrides)
    if account.cli == Cli.CLAUDE:
        argv = [*prefix, "auth", "login", "--claudeai"]
        if email.strip():
            argv += ["--email", email.strip()]
        return argv
    return prefix  # agy: its TUI asks for the login


class LoginSession:
    """One login terminal. Any viewer may type: there is no run to protect from the keyboard."""

    def __init__(
        self,
        account_id: str,
        argv: list[str],
        env: dict[str, str],
        cwd: str,
        loop: asyncio.AbstractEventLoop,
        on_end: Callable[[str], None],
        cols: int = 100,
        rows: int = 28,
    ) -> None:
        self.account_id = account_id
        self.argv, self.env, self.cwd = argv, env, cwd
        self.loop = loop
        self.on_end = on_end
        self.cols, self.rows = cols, rows
        self.exit_code: int | None = None
        self._pty: PtyProcess | None = None
        self._scrollback: list[str] = []
        self._scrollback_size = 0
        self._viewers: dict[str, Viewer] = {}
        self._lock = threading.RLock()
        self._finished = threading.Event()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._pty = spawn(self.argv, self.cwd, self.env, self.cols, self.rows)
        threading.Thread(
            target=self._read_loop, name=f"login-{self.account_id}", daemon=True
        ).start()
        threading.Thread(target=self._watchdog, name="login-watchdog", daemon=True).start()

    @property
    def alive(self) -> bool:
        return not self._finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    def kill(self) -> None:
        if self._pty is not None:
            with contextlib.suppress(OSError):
                self._pty.terminate()

    def _watchdog(self) -> None:
        if not self._finished.wait(LOGIN_TIMEOUT):
            log.info("login timed out", account=self.account_id)
            self.kill()

    def _read_loop(self) -> None:
        pty = self._pty
        assert pty is not None
        try:
            while True:
                chunk = pty.read()
                if not chunk:
                    break
                with self._lock:
                    self._scrollback.append(chunk)
                    self._scrollback_size += len(chunk)
                    while self._scrollback_size > SCROLLBACK_LIMIT and len(self._scrollback) > 1:
                        self._scrollback_size -= len(self._scrollback.pop(0))
                self._publish({"type": "output", "data": chunk})
        except Exception:
            log.exception("login reader failed", account=self.account_id)
            with contextlib.suppress(OSError):
                pty.terminate()
        finally:
            deadline = time.monotonic() + 5
            while pty.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.exit_code = pty.exit_code
            # The session is checked first: whoever hears the exit then reads a fresh state, and
            # the account is not «logging in» any more only once that is settled.
            try:
                self.on_end(self.account_id)
            except Exception:
                log.exception("login follow-up failed", account=self.account_id)
            self._publish({"type": "exit", "code": self.exit_code, "status": "exited"})
            self._finished.set()

    # ------------------------------------------------------------------ viewers
    def attach(self, client_id: str) -> tuple[str, Viewer]:
        viewer = Viewer(client_id)
        with self._lock:
            snapshot = "".join(self._scrollback)
            self._viewers[client_id] = viewer
        return snapshot, viewer

    def detach(self, client_id: str) -> None:
        with self._lock:
            self._viewers.pop(client_id, None)

    def state_message(self) -> dict:
        # Everyone may type: the page treats the controller as itself.
        return {
            "type": "state",
            "status": "running" if self.alive else "exited",
            "activity": "idle",
            "controller": None,
            "cols": self.cols,
            "rows": self.rows,
        }

    def _publish(self, message: dict) -> None:
        if self.loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):  # the loop may be closing
            self.loop.call_soon_threadsafe(self._broadcast, message)

    def _broadcast(self, message: dict) -> None:
        with self._lock:
            viewers = list(self._viewers.values())
        for viewer in viewers:
            if viewer.queue.qsize() > VIEWER_BACKLOG_LIMIT:
                self.detach(viewer.client_id)
                viewer.queue.put_nowait(None)
            else:
                viewer.queue.put_nowait(message)

    # ------------------------------------------------------------------ input
    def write_input(self, client_id: str, data: str) -> bool:
        if self._pty is None or not self.alive:
            return False
        self._pty.write(data)
        return True

    def resize(self, client_id: str, cols: int, rows: int) -> None:
        cols, rows = max(20, min(cols, 400)), max(5, min(rows, 200))
        if (cols, rows) == (self.cols, self.rows) or self._pty is None:
            return
        self.cols, self.rows = cols, rows
        self._pty.resize(cols, rows)


class AccountLogins:
    """The logins in progress, one per account."""

    def __init__(self, overrides: Mapping[str, list[str]]) -> None:
        self._overrides = overrides
        self._live: dict[str, LoginSession] = {}
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        # Called (from the login's thread) once it ended, to check the session again.
        self.on_end: Callable[[str], None] = lambda account_id: None

    def get(self, account_id: str) -> LoginSession | None:
        with self._lock:
            session = self._live.get(account_id)
        return session if session is not None and session.alive else None

    def live_ids(self) -> set[str]:
        with self._lock:
            return {a for a, s in self._live.items() if s.alive}

    def start(self, account: CliAccount, email: str = "") -> LoginSession:
        """Opens the login terminal of an account (the one already open if there is one)."""
        if self.loop is None:
            raise RuntimeError("AccountLogins.loop is not set (lifespan not started)")
        with self._lock:
            current = self._live.get(account.id)
            if current is not None and current.alive:
                return current
            argv = login_argv(account, self._overrides, email)
            env = {**clean_env(), **account_ops.env_for(account)}
            session = LoginSession(account.id, argv, env, str(Path.home()), self.loop, self.on_end)
            try:
                session.start()
            except Exception as error:
                raise ApiError(500, "login_failed", str(error)) from error
            self._live[account.id] = session
            return session

    def stop(self, account_id: str) -> None:
        session = self.get(account_id)
        if session is not None:
            session.kill()

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._live.values())
        for session in sessions:
            session.kill()
