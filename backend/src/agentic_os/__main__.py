"""Entry point: `agentic-os-backend` / `python -m agentic_os`.

Sidecar protocol (ADR 0002): with `--port 0` the backend binds a free port and, once it is
serving, prints `AGENTIC_OS_READY {"port": N}` on stdout. With `--parent-pid` it shuts down
when that process disappears, so it never outlives the desktop app.
"""

import argparse
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
from agentic_os.config import get_settings
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


def watch_parent(pid: int, on_exit: Callable[[], None], interval: float) -> threading.Thread:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(interval):
            if not pid_exists(pid):
                log.warning("parent process gone, shutting down", parent_pid=pid)
                on_exit()
                return

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
    parser.add_argument("--watchdog-interval", type=float, default=2.0)
    parser.add_argument("--reload", action="store_true", help="dev only: auto-reload")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    if args.reload:
        uvicorn.run(
            "agentic_os.app:create_app",
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
