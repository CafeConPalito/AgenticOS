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


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a spawned CLI without markers inherited from the Claude Code session
    running these spikes (they disable transcripts and alter behaviour)."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith("CLAUDE") or k.upper() == "CLAUDE_CONFIG_DIR"
    }
    env.update(extra or {})
    return env


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
