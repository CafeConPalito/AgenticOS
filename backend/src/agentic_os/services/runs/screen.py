"""Emulated terminal screen of a run, used to read the CLI's TUI state (spike P1/P2).

The raw output still goes to the viewers untouched; this only answers questions such as
"is the folder-trust dialog showing?" or "is the agent busy?".
"""

from __future__ import annotations

import re
import threading

import pyte

from agentic_os.models.agent import Cli

# Both CLIs offer "Yes, I trust this folder"; the cursor is ❯ in Claude Code and > in agy.
TRUST_OPTION = re.compile(r"Yes, I trust this folder")
TRUST_SELECTED = re.compile(r"[❯>]\s*Yes, I trust this folder")

# Footer shown while a turn is running (spike P2).
BUSY_FOOTER = {
    Cli.CLAUDE: re.compile(r"esc to interrupt", re.IGNORECASE),
    Cli.AGY: re.compile(r"esc to cancel|Generating", re.IGNORECASE),
}


class ScreenState:
    def __init__(self, cli: Cli, cols: int, rows: int) -> None:
        self.cli = cli
        self._lock = threading.Lock()
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

    def feed(self, data: str) -> None:
        with self._lock:
            self._stream.feed(data)

    def resize(self, cols: int, rows: int) -> None:
        with self._lock:
            self._screen.resize(rows, cols)

    def text(self) -> str:
        with self._lock:
            return "\n".join(line.rstrip() for line in self._screen.display)

    def trust_dialog(self) -> tuple[bool, bool]:
        """(dialog visible, "Yes" option selected)."""
        screen = self.text()
        return bool(TRUST_OPTION.search(screen)), bool(TRUST_SELECTED.search(screen))

    def footer_busy(self) -> bool:
        lines = [line for line in self.text().splitlines() if line.strip()]
        return bool(BUSY_FOOTER[self.cli].search("\n".join(lines[-4:])))
