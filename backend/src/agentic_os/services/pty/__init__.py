import sys

from agentic_os.services.pty.base import PtyProcess


def spawn(
    argv: list[str], cwd: str, env: dict[str, str], cols: int = 120, rows: int = 32
) -> PtyProcess:
    """Starts `argv` in a pseudo-terminal (ConPTY on Windows, a Unix PTY elsewhere)."""
    if sys.platform == "win32":
        from agentic_os.services.pty.windows import WindowsPty

        return WindowsPty.spawn(argv, cwd, env, cols, rows)
    from agentic_os.services.pty.posix import PosixPty

    return PosixPty.spawn(argv, cwd, env, cols, rows)


__all__ = ["PtyProcess", "spawn"]
