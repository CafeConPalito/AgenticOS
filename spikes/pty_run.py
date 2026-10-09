"""P1–P3: run a CLI inside a real pseudo-terminal (Windows ConPTY via pywinpty).

`PtyRun` streams raw output to a log file, keeps a `pyte` screen so the current terminal
contents can be captured as plain text, and lets a script type, press keys and resize.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import pyte
from winpty import PtyProcess

KEYS = {
    "enter": "\r",
    "esc": "\x1b",
    "ctrl_c": "\x03",
    "ctrl_d": "\x04",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "tab": "\t",
    "shift_tab": "\x1b[Z",
}


# Markers a running Claude Code session sets for its children. Inherited by a spawned CLI they
# disable transcripts and alter behaviour. User configuration (CLAUDE_CONFIG_DIR,
# CLAUDE_CODE_GIT_BASH_PATH, CLAUDE_CODE_USE_BEDROCK…) is deliberately kept.
SESSION_MARKERS = {
    "CLAUDECODE",
    "CLAUDE_PID",
    "CLAUDE_EFFORT",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_AGENT_SDK_VERSION",
}


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a spawned CLI without the parent Claude Code session's markers."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in SESSION_MARKERS}
    env.update(extra or {})
    return env


def agy_permission_request(screen: str) -> tuple[str, str] | None:
    """Classifies the permission dialog agy is showing, reading only the dialog itself (the
    echoed prompt elsewhere on screen must not influence the decision).

    Returns ("mcp", "<server>/<tool>"), ("command", "<command line>") or None.
    """
    lines = screen.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "Allow calling this tool?":
            # The tool id is the nearest non-blank line above (the TUI may pad with blanks).
            above = next((lines[j].strip() for j in range(i - 1, -1, -1) if lines[j].strip()), "")
            return "mcp", above
        if line.strip() == "Run this command?":
            start = next(
                (j for j in range(i, -1, -1) if "Requesting permission for:" in lines[j]), i
            )
            return "command", " ".join(x.strip() for x in lines[start + 1 : i])
    return None


def approve_only_agentic_os(run: PtyRun) -> tuple[str, str] | None:
    """If agy shows a permission dialog: approve it only for our own MCP tools, deny anything
    else (shell commands, other servers). Returns the request handled, if any."""
    request = agy_permission_request(run.snapshot())
    if request is None:
        return None
    run.key("enter" if request[0] == "mcp" and request[1].startswith("agentic-os") else "esc")
    time.sleep(2)
    return request


TRUST_DIALOG = {
    "claude": (r"trust this folder", r"❯ Yes, I trust"),
    "agy": (r"trust the contents", r"> Yes, I trust"),
}


def accept_trust(run: PtyRun, cli: str, timeout: float = 30) -> bool:
    """Accepts the folder-trust dialog. Keys sent before the menu is interactive are dropped,
    so the selection is retried until the screen shows "Yes" selected and the dialog closes."""
    question, yes_selected = TRUST_DIALOG[cli]
    if not run.wait_screen(question, timeout=timeout):
        return False
    for _ in range(10):
        time.sleep(0.5)
        if not re.search(yes_selected, run.snapshot()):
            run.key("down")
            if not run.wait_screen(yes_selected, timeout=1.5):
                continue
        run.key("enter")
        time.sleep(1)
        if not re.search(question, run.snapshot(), re.IGNORECASE):
            return True
    return False


class PtyRun:
    def __init__(
        self,
        argv: list[str],
        cwd: Path,
        log_path: Path,
        env: dict[str, str] | None = None,
        cols: int = 120,
        rows: int = 40,
    ) -> None:
        self.argv = argv
        self.log_path = log_path
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.output: list[str] = []
        self.last_output_at = time.monotonic()
        self.started_at = time.monotonic()
        self._lock = threading.Lock()
        self._log = log_path.open("w", encoding="utf-8", newline="")
        self.proc = PtyProcess.spawn(
            argv, cwd=str(cwd), env=env or clean_env(), dimensions=(rows, cols)
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # -- output ---------------------------------------------------------------------------
    def _read_loop(self) -> None:
        while True:
            try:
                chunk = self.proc.read(4096)
            except EOFError:
                break
            except Exception:  # noqa: BLE001 - the PTY closes abruptly when the process exits
                break
            if not chunk:
                if not self.proc.isalive():
                    break
                time.sleep(0.02)
                continue
            with self._lock:
                self.output.append(chunk)
                self.stream.feed(chunk)
                self.last_output_at = time.monotonic()
                self._log.write(chunk)
                self._log.flush()

    def text(self) -> str:
        """Everything written so far with ANSI escape sequences stripped."""
        with self._lock:
            raw = "".join(self.output)
        return re.sub(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]", "", raw)

    def snapshot(self) -> str:
        """Current visible screen as plain text (trailing blanks trimmed)."""
        with self._lock:
            lines = [line.rstrip() for line in self.screen.display]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    # -- input ----------------------------------------------------------------------------
    def send(self, text: str) -> None:
        self.proc.write(text)

    def type_line(self, text: str, settle: float = 0.4) -> None:
        """Types text, waits for the TUI to render it, then presses Enter."""
        self.send(text)
        time.sleep(settle)
        self.send(KEYS["enter"])

    def key(self, name: str) -> None:
        self.send(KEYS[name])

    def resize(self, cols: int, rows: int) -> None:
        self.proc.setwinsize(rows, cols)
        with self._lock:
            self.screen.resize(rows, cols)

    # -- waiting --------------------------------------------------------------------------
    def wait_screen(self, pattern: str, timeout: float = 60) -> bool:
        """Waits until the visible screen matches `pattern` (regex)."""
        regex = re.compile(pattern, re.IGNORECASE)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if regex.search(self.snapshot()):
                return True
            if not self.proc.isalive():
                return bool(regex.search(self.snapshot()))
            time.sleep(0.2)
        return False

    def wait_idle(self, quiet: float = 3.0, timeout: float = 120) -> bool:
        """Waits until there has been no output for `quiet` seconds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if time.monotonic() - self.last_output_at >= quiet:
                return True
            time.sleep(0.2)
        return False

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    # -- lifecycle ------------------------------------------------------------------------
    def alive(self) -> bool:
        return self.proc.isalive()

    def wait_exit(self, timeout: float = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.proc.isalive():
                return True
            time.sleep(0.2)
        return False

    def close(self) -> None:
        if self.proc.isalive():
            self.proc.terminate(force=True)
        self._reader.join(timeout=3)
        self._log.close()
