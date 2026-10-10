from abc import ABC, abstractmethod


class PtyProcess(ABC):
    """A child process attached to a pseudo-terminal.

    `read` blocks until output is available and returns "" once the process has exited and
    the output is drained. All other methods are non-blocking and safe to call from any thread.
    """

    @property
    @abstractmethod
    def pid(self) -> int: ...

    @abstractmethod
    def read(self) -> str: ...

    @abstractmethod
    def write(self, data: str) -> None: ...

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None: ...

    @abstractmethod
    def is_alive(self) -> bool: ...

    @property
    @abstractmethod
    def exit_code(self) -> int | None: ...

    @abstractmethod
    def terminate(self) -> None:
        """Kills the process (and closes the terminal)."""
