"""Installing an agent CLI from the app (phase 23, ADR 0029).

Only the official installer of each CLI, shown to the person before it runs and run in a terminal
they see (the same terminal protocol as a login, `accounts_login.LoginSession`). When it ends the
CLIs are probed again: `cli_paths` finds the new one without restarting the app.

The installers were read on 2026-10-31. Both install for the user alone, without administrator
rights or Node.js, check the checksum of what they download, and ask nothing.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

from agentic_os.errors import ApiError
from agentic_os.models import Cli
from agentic_os.services.accounts_login import LoginSession
from agentic_os.services.clis import installer_for
from agentic_os.services.runs.launcher import clean_env


def powershell_argv(command: str) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]


class CliInstalls:
    """The installations in progress, one per CLI."""

    def __init__(self) -> None:
        self._live: dict[str, LoginSession] = {}
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        # The argv of an installation (tests swap in a fake installer).
        self.argv_for: Callable[[Cli], list[str] | None] = self._official_argv
        # Called (from the installation's thread) once it ended: the CLIs are probed again.
        self.on_end: Callable[[str], None] = lambda cli: None

    @staticmethod
    def _official_argv(cli: Cli) -> list[str] | None:
        installer = installer_for(cli)
        return powershell_argv(installer.command) if installer else None

    def get(self, cli: str) -> LoginSession | None:
        with self._lock:
            return self._live.get(cli)

    def start(self, cli: Cli) -> LoginSession:
        """Runs the CLI's installer in a terminal (the one already running, if there is one)."""
        if self.loop is None:
            raise RuntimeError("CliInstalls.loop is not set (lifespan not started)")
        argv = self.argv_for(cli)
        if argv is None:
            raise ApiError(409, "no_installer", f"{cli.value} has no installer for this system")
        with self._lock:
            current = self._live.get(cli.value)
            if current is not None and current.alive:
                return current
            session = LoginSession(
                cli.value, argv, clean_env(), str(Path.home()), self.loop, self.on_end
            )
            try:
                session.start()
            except Exception as error:
                raise ApiError(500, "install_failed", str(error)) from error
            self._live[cli.value] = session
            return session

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._live.values())
        for session in sessions:
            session.kill()
