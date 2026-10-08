"""Entry point: `agentic-os-backend` / `python -m agentic_os`.

Sidecar protocol (ADR 0002): with `--port 0` the backend binds a free port and, once it is
serving, prints `AGENTIC_OS_READY {"port": N}` on stdout. With `--parent-pid` it shuts down
when that process disappears, so it never outlives the desktop app.
"""

import argparse
import contextlib
import json
import os
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import structlog
import uvicorn

from agentic_os.app import create_app
from agentic_os.config import Settings, get_settings
from agentic_os.logging_setup import configure_logging

READY_PREFIX = "AGENTIC_OS_READY"

log = structlog.get_logger()


def pid_exists(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        synchronize, wait_timeout = 0x00100000, 0x00000102
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def parent_exit_waiter(pid: int, poll_interval: float) -> Callable[[], None]:
    """Returns a blocking function that returns once process `pid` has exited.

    On Windows the process handle is opened *now*, so a later reuse of the PID cannot be
    mistaken for the parent, and the wait is event-driven instead of polled.
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        synchronize, infinite = 0x00100000, 0xFFFFFFFF
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel32.OpenProcess(synchronize, False, pid)

        def wait() -> None:
            if handle:  # no handle: the parent is already gone
                kernel32.WaitForSingleObject(handle, infinite)

        return wait

    stop = threading.Event()

    def poll() -> None:
        while pid_exists(pid):
            stop.wait(poll_interval)

    return poll


def watch_parent(
    pid: int, on_exit: Callable[[], None], poll_interval: float = 2.0, grace: float = 5.0
) -> threading.Thread:
    """Calls `on_exit` when `pid` dies; hard-exits if the process is still alive after `grace`.

    When the parent dies our stdout/stderr pipes are usually broken, so nothing here may depend
    on being able to write to them.
    """
    wait_for_parent = parent_exit_waiter(pid, poll_interval)

    def run() -> None:
        wait_for_parent()
        on_exit()
        with contextlib.suppress(Exception):
            log.warning("parent process gone, shutting down", parent_pid=pid)
        threading.Event().wait(grace)
        os._exit(0)

    thread = threading.Thread(target=run, name="parent-watchdog", daemon=True)
    thread.start()
    return thread


class ReadyServer(uvicorn.Server):
    """Uvicorn server that announces its port on stdout once it is accepting requests."""

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started and sockets:
            port = sockets[0].getsockname()[1]
            print(f"{READY_PREFIX} {json.dumps({'port': port})}", flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="agentic-os-backend")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port, help="0 = free port")
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument(
        "--watchdog-interval", type=float, default=2.0, help="parent poll interval (non-Windows)"
    )
    parser.add_argument("--reload", action="store_true", help="dev only: auto-reload")
    return parser.parse_args(argv)


def resolve_log_file(settings: Settings) -> Path | None:
    """Packaged builds always log to a file: the desktop shell does not keep our stderr."""
    if settings.log_file is not None:
        return settings.log_file
    if getattr(sys, "frozen", False):
        return settings.data_dir / "logs" / "backend.log"
    return None


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(
        settings.log_level, json=settings.log_json, log_file=resolve_log_file(settings)
    )

    if args.reload:
        # The app runs in a reloader child process; create_app configures logging there too.
        uvicorn.run(
            "agentic_os.app:create_dev_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent)],
            log_config=None,
        )
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((args.host, args.port))
    server = ReadyServer(uvicorn.Config(create_app(settings), log_config=None))

    if args.parent_pid is not None:

        def request_exit() -> None:
            server.should_exit = True

        watch_parent(args.parent_pid, request_exit, args.watchdog_interval)

    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
