"""A terminal in a repository's folder, for what the Git tab does not cover (`bisect`,
`filter-repo`, aliases…). Phase 12, ADR 0017.

It is the same live pseudo-terminal the login of an account uses (`LoginSession`): the page shows
it with the terminal component and talks to it over the same WebSocket protocol. Closing it
tells the tab to read the repository again.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from agentic_os.errors import ApiError
from agentic_os.services.accounts_login import LoginSession
from agentic_os.services.runs.launcher import clean_env

MAX_OPEN = 4


def shell_argv() -> list[str]:
    """Git Bash if Git for Windows has it, else the system shell."""
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            root = Path(git).resolve().parent.parent
            for candidate in (root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"):
                if candidate.is_file():
                    return [str(candidate), "--login", "-i"]
        return [shutil.which("powershell.exe") or "powershell.exe", "-NoLogo"]
    return [os.environ.get("SHELL") or "/bin/sh", "-i"]


class ShellSessions:
    """The terminals open now, at most `MAX_OPEN`."""

    def __init__(self) -> None:
        self._live: dict[str, tuple[str, LoginSession]] = {}
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        # Called, from the terminal's thread, with the repository it was opened in.
        self.on_end: Callable[[str], None] = lambda repo_id: None

    def open(self, repo_id: str, folder: str) -> str:
        if self.loop is None:
            raise RuntimeError("ShellSessions.loop is not set (lifespan not started)")
        with self._lock:
            self._forget_finished()
            if len(self._live) >= MAX_OPEN:
                raise ApiError(409, "too_many_terminals", "close a terminal before opening another")
            shell_id = uuid.uuid4().hex
            session = LoginSession(
                shell_id,
                shell_argv(),
                clean_env(),
                folder,
                self.loop,
                lambda _id, repo=repo_id: self.on_end(repo),
                cols=120,
                rows=30,
            )
            session.start()
            self._live[shell_id] = (repo_id, session)
        return shell_id

    def get(self, shell_id: str) -> LoginSession | None:
        with self._lock:
            found = self._live.get(shell_id)
        return found[1] if found else None

    def close(self, shell_id: str) -> bool:
        with self._lock:
            found = self._live.pop(shell_id, None)
        if found is None:
            return False
        found[1].kill()
        return True

    def of_repo(self, repo_id: str) -> list[str]:
        with self._lock:
            return [i for i, (repo, s) in self._live.items() if repo == repo_id and s.alive]

    def shutdown(self) -> None:
        with self._lock:
            sessions = [s for _repo, s in self._live.values()]
            self._live.clear()
        for session in sessions:
            session.kill()

    def _forget_finished(self) -> None:
        for shell_id in [i for i, (_r, s) in self._live.items() if not s.alive]:
            del self._live[shell_id]
