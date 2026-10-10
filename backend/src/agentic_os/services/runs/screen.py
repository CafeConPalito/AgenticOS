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

# agy's first Ctrl+C only arms the exit; a second one counts once this notice is shown.
EXIT_ARMED = re.compile(r"ctrl\+c again to exit", re.IGNORECASE)

# agy's idle input footer: the prompt can be typed (spike P5 waited for the same).
INPUT_READY = re.compile(r"\? for shortcuts")

# agy's permission dialog for an MCP tool of our plugin (`<plugin>_<server>/<tool>`).
AGENTIC_OS_TOOL_PREFIX = "agentic-os_agentic-os/"
ALWAYS_ALLOW = re.compile(r"2\. Yes, and always allow tool .* in this conversation")
MCP_DIALOG_LINES = 14  # the dialog must be at the bottom: an answered one scrolls away

# Printed once the CLI accepted the exit (it may still take a few seconds to end).
EXIT_ACK = {
    Cli.CLAUDE: re.compile(r"Resume this session|claude --resume"),
    Cli.AGY: re.compile(r"Resume with -c|agy --conversation"),
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

    def ready_for_prompt(self) -> bool:
        """agy shows its input (footer «? for shortcuts») and no dialog is waiting."""
        if self.trust_dialog()[0]:
            return False
        lines = [line for line in self.text().splitlines() if line.strip()]
        return bool(INPUT_READY.search("\n".join(lines[-4:])))

    def agentic_os_tool_request(self) -> tuple[str, bool] | None:
        """agy's «Allow calling this tool?» dialog for one of *our* MCP tools, if it is the
        latest thing on screen: (tool id, "always allow in this conversation" selected)."""
        lines = [line.strip() for line in self.text().splitlines() if line.strip()]
        tail = lines[-MCP_DIALOG_LINES:]
        indexes = [i for i, line in enumerate(tail) if line == "Allow calling this tool?"]
        if not indexes or indexes[-1] == 0:
            return None
        at = indexes[-1]
        tool = tail[at - 1]
        if not tool.startswith(AGENTIC_OS_TOOL_PREFIX):
            return None  # someone else's tool (or a command): the human decides
        option = next((line for line in tail[at + 1 :] if ALWAYS_ALLOW.search(line)), None)
        if option is None:
            return None
        return tool, option.startswith((">", "❯"))

    def exit_armed(self) -> bool:
        return bool(EXIT_ARMED.search(self.text()))

    def exit_acknowledged(self) -> bool:
        return bool(EXIT_ACK[self.cli].search(self.text()))

    def footer_busy(self) -> bool:
        lines = [line for line in self.text().splitlines() if line.strip()]
        return bool(BUSY_FOOTER[self.cli].search("\n".join(lines[-4:])))
