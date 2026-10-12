"""Emulated terminal screen of a run, used to read the CLI's TUI state (spike P1/P2).

The raw output still goes to the viewers untouched; this only answers questions such as
"is the folder-trust dialog showing?" or "is the agent busy?".
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

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

# Dialogs Agentic OS never answers for the user (a consent, not a technicality): the run
# records an event so the UI can ask the human to take the control.
HUMAN_DIALOGS = {
    # Claude Code, first start in bypassPermissions («Autónomo»): stored in ~/.claude.json.
    "bypass_permissions_consent": re.compile(r"Bypass Permissions mode[\s\S]*Yes, I accept"),
}

# agy's idle input footer: the prompt can be typed (spike P5 waited for the same).
INPUT_READY = re.compile(r"\? for shortcuts")

# agy's permission dialog for an MCP tool of our plugin (`<plugin>_<server>/<tool>`).
AGENTIC_OS_TOOL_PREFIX = "agentic-os_agentic-os/"
ALWAYS_ALLOW = re.compile(r"2\. Yes, and always allow tool .* in this conversation")
MCP_DIALOG_LINES = 14  # the dialog must be at the bottom: an answered one scrolls away
DIALOG_LINES = 12  # same for the trust dialog

# Permission dialogs of the CLIs (phase 06, captured with Claude Code 2.1.296 and agy 1.3.3).
# The emulated screen may misplace Claude's text (wide glyphs): only short, stable fragments
# are matched, and the details of Claude's request come from its PermissionRequest hook.
CLAUDE_PERMISSION = re.compile(r"\bamend\b")  # «Tab to amend», sometimes «Tab t  amend»
CLAUDE_YES_OPTION = re.compile(r"\b1\.?\s+Yes\b")
CLAUDE_QUESTION = re.compile(r"(?:Do )?you want to [^?]*\?")
# The «No» option is the third one: «3. No» (sometimes drawn as «No   3.»).
CLAUDE_NO_OPTION = re.compile(r"\b3\.\s*No\b|\bNo\s+3\.")
AGY_COMMAND_REQUEST = "Requesting permission for:"
AGY_DENY_OPTION = re.compile(r"No, (cancel|deny)")
PERMISSION_LINES = 24  # the dialog must be at the bottom of the screen

# Out of quota (phase 07). No real screen has been seen yet: the texts come from the CLIs'
# binaries (Claude Code 2.1.296, agy 1.3.3; evidence C0). Not quota: Claude's «Context limit
# reached» and its fast-mode limits («You've hit your fast limit», «Fast limit reached»).
QUOTA_PATTERNS = {
    Cli.CLAUDE: re.compile(
        r"Usage limit reached|You've hit your (?!fast)[\w -]*limit|usage limit (?:will )?reset",
        re.IGNORECASE,
    ),
    Cli.AGY: re.compile(r"Quota exhausted|Out of credits|RESOURCE_EXHAUSTED", re.IGNORECASE),
}
# When the quota comes back, if the CLI says it.
QUOTA_RESET = {
    Cli.CLAUDE: re.compile(r"\bresets?\b[^|·\n]{1,60}", re.IGNORECASE),
    Cli.AGY: re.compile(r"Refreshes in [^|·\n]{1,40}", re.IGNORECASE),
}
QUOTA_LINES = 10  # only the bottom of the screen: the agent's own text may mention a quota


@dataclass(frozen=True)
class PermissionDialog:
    kind: str  # "command" (agy), "tool" (agy, not ours) or "claude"
    subject: str  # the command, the tool or Claude's question

    @property
    def signature(self) -> str:
        # Claude's question is generic and redraws garble it: not part of the identity (two
        # dialogs in a row are told apart because answering one resets the session's state).
        return self.kind if self.kind == "claude" else f"{self.kind}:{self.subject}"


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
        """(dialog visible, "Yes" option selected). Only the bottom of the screen counts:
        agy leaves the answered dialog drawn above its TUI."""
        lines = [line for line in self.text().splitlines() if line.strip()]
        screen = "\n".join(lines[-DIALOG_LINES:])
        return bool(TRUST_OPTION.search(screen)), bool(TRUST_SELECTED.search(screen))

    def waiting_for_human(self) -> str | None:
        """A dialog only the human should answer, at the bottom of the screen: its key."""
        lines = [line for line in self.text().splitlines() if line.strip()]
        tail = "\n".join(lines[-DIALOG_LINES:])
        for key, pattern in HUMAN_DIALOGS.items():
            if pattern.search(tail):
                return key
        return None

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

    def permission_dialog(self) -> PermissionDialog | None:
        """A permission dialog of the CLI waiting for an answer, at the bottom of the screen.
        In both CLIs the first option («Yes») is selected: Enter approves, Esc rejects. Our own
        MCP tools in agy are not reported (they are approved automatically)."""
        lines = [line.strip() for line in self.text().splitlines() if line.strip()]
        tail = lines[-PERMISSION_LINES:]
        if self.cli == Cli.CLAUDE:
            footer = tail[-6:]
            if not any(CLAUDE_PERMISSION.search(line) and "Tab" in line for line in footer):
                return None
            if not any(CLAUDE_YES_OPTION.search(line) for line in tail):
                return None
            if not any(CLAUDE_NO_OPTION.search(line) for line in tail):
                return None
            question = next(
                (m.group(0) for line in tail if (m := CLAUDE_QUESTION.search(line))), ""
            )
            return PermissionDialog("claude", question)
        if not any(AGY_DENY_OPTION.search(line) for line in tail):
            return None
        if AGY_COMMAND_REQUEST in tail:
            at = tail.index(AGY_COMMAND_REQUEST)
            command = tail[at + 1] if at + 1 < len(tail) else ""
            return PermissionDialog("command", command)
        if "Allow calling this tool?" in tail:
            at = len(tail) - 1 - tail[::-1].index("Allow calling this tool?")
            tool = tail[at - 1] if at > 0 else ""
            if tool.startswith(AGENTIC_OS_TOOL_PREFIX):
                return None
            return PermissionDialog("tool", tool)
        return None

    def quota_notice(self) -> str | None:
        """The CLI's «out of quota / usage limit» notice at the bottom of the screen: its
        line, plus the reset time when the CLI gives it."""
        lines = [line.strip() for line in self.text().splitlines() if line.strip()]
        tail = lines[-QUOTA_LINES:]
        pattern = QUOTA_PATTERNS.get(self.cli)
        if pattern is None:
            return None
        hit = next((line for line in reversed(tail) if pattern.search(line)), None)
        if hit is None:
            return None
        notice = hit.strip("│|╭╮╰╯─ ").strip()
        reset_pattern = QUOTA_RESET.get(self.cli)
        if reset_pattern is not None and not reset_pattern.search(notice):
            reset = next((m.group(0) for line in tail if (m := reset_pattern.search(line))), None)
            if reset:
                notice = f"{notice} · {reset.strip()}"
        return notice[:300]

    def exit_armed(self) -> bool:
        return bool(EXIT_ARMED.search(self.text()))

    def exit_acknowledged(self) -> bool:
        return bool(EXIT_ACK[self.cli].search(self.text()))

    def footer_busy(self) -> bool:
        lines = [line for line in self.text().splitlines() if line.strip()]
        return bool(BUSY_FOOTER[self.cli].search("\n".join(lines[-4:])))
