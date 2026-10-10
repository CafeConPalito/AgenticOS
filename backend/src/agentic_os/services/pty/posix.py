import threading

from ptyprocess import PtyProcessUnicode

from agentic_os.services.pty.base import PtyProcess


class PosixPty(PtyProcess):
    """Unix PTY via ptyprocess (Linux/macOS; used by the future server mode)."""

    def __init__(self, proc: PtyProcessUnicode) -> None:
        self._proc = proc
        self._write_lock = threading.Lock()

    @classmethod
    def spawn(
        cls, argv: list[str], cwd: str, env: dict[str, str], cols: int, rows: int
    ) -> "PosixPty":
        return cls(PtyProcessUnicode.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols)))

    @property
    def pid(self) -> int:
        return self._proc.pid

    def read(self) -> str:
        try:
            return self._proc.read(65536)
        except EOFError:
            return ""

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
