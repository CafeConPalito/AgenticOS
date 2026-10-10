import threading
import time

from winpty import PtyProcess as _WinPty

from agentic_os.services.pty.base import PtyProcess


class WindowsPty(PtyProcess):
    """ConPTY via pywinpty."""

    def __init__(self, proc: _WinPty) -> None:
        self._proc = proc
        self._write_lock = threading.Lock()

    @classmethod
    def spawn(
        cls, argv: list[str], cwd: str, env: dict[str, str], cols: int, rows: int
    ) -> "WindowsPty":
        return cls(_WinPty.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols)))

    @property
    def pid(self) -> int:
        return self._proc.pid

    def read(self) -> str:
        while True:
            try:
                chunk = self._proc.read(65536)
            except EOFError:
                return ""
            if chunk:
                return chunk
            if not self._proc.isalive():
                return ""
            time.sleep(0.01)

    def write(self, data: str) -> None:
        with self._write_lock:
            if self._proc.isalive():
                self._proc.write(data)

    def resize(self, cols: int, rows: int) -> None:
        if self._proc.isalive():
            self._proc.setwinsize(rows, cols)

    def is_alive(self) -> bool:
        return self._proc.isalive()

    @property
    def exit_code(self) -> int | None:
        return None if self._proc.isalive() else self._proc.exitstatus

    def terminate(self) -> None:
        if self._proc.isalive():
            self._proc.terminate(force=True)
