"""Sanity checks for the fake CLI itself, driven through a real pseudo-terminal."""

import os
import sys
import threading
import time
from pathlib import Path

from agentic_os.services.pty import spawn

FAKE_CLI = str(Path(__file__).with_name("fake_cli.py"))


class Reader:
    def __init__(self, proc) -> None:
        self.proc = proc
        self.text = ""
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            chunk = self.proc.read()
            if not chunk:
                return
            self.text += chunk

    def wait_for(self, needle: str, timeout: float = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if needle in self.text:
                return True
            time.sleep(0.05)
        return False


def start(tmp_path, *args: str):
    proc = spawn([sys.executable, FAKE_CLI, *args], str(tmp_path), dict(os.environ))
    return proc, Reader(proc)


def test_trust_answer_interrupt_and_exit(tmp_path):
    proc, reader = start(tmp_path, "hola")
    try:
        assert reader.wait_for("trust the files")
        time.sleep(0.3)
        proc.write("\x1b[B")
        assert reader.wait_for("❯ Yes, I trust")
        proc.write("\r")
        assert reader.wait_for("● RESPUESTA: hola")

        proc.write("LARGO\r")
        assert reader.wait_for("esc to interrupt")
        time.sleep(0.4)
        proc.write("\x1b")
        assert reader.wait_for("Interrupted")

        proc.write("/exit\r")
        deadline = time.monotonic() + 10
        while proc.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert proc.exit_code == 0
    finally:
        proc.terminate()


def test_ignore_exit(tmp_path):
    proc, reader = start(tmp_path, "--no-trust", "--ignore-exit", "x")
    try:
        assert reader.wait_for("● RESPUESTA: x")
        proc.write("/exit\r")
        assert reader.wait_for("(ignoring /exit)")
        assert proc.is_alive()
    finally:
        proc.terminate()
