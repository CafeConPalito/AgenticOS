"""The WebSocket protocol of a live terminal, shared by the runs and the login of an account.

Server → client: `snapshot` (the scrollback), `state`, `output`, `usage`, `exit`.
Client → server: `input` (typed data) and `resize` (cols, rows).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Protocol

from fastapi import WebSocket, WebSocketDisconnect

from agentic_os.services.runs.session import Viewer


class TerminalSession(Protocol):
    """What a live terminal must offer (RunSession and LoginSession)."""

    def attach(self, client_id: str) -> tuple[str, Viewer]: ...

    def detach(self, client_id: str) -> None: ...

    def state_message(self) -> dict: ...

    def write_input(self, client_id: str, data: str) -> bool: ...

    def resize(self, client_id: str, cols: int, rows: int) -> None: ...


async def serve_terminal(websocket: WebSocket, session: TerminalSession, client_id: str) -> None:
    """Serves one viewer of a live session until it leaves or the session exits."""
    snapshot, viewer = session.attach(client_id)
    await websocket.send_json({"type": "snapshot", "data": snapshot})
    await websocket.send_json(session.state_message())

    async def pump() -> None:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await _pump()

    async def _pump() -> None:
        while True:
            message = await viewer.queue.get()
            if message is None:  # dropped for being too slow: the client reconnects
                await websocket.close(code=4408)
                return
            await websocket.send_json(message)
            if message.get("type") == "exit":
                await websocket.close()
                return

    async def listen() -> None:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            while True:
                try:
                    message = json.loads(await websocket.receive_text())
                except ValueError:
                    continue  # malformed frame: ignore it, keep the terminal open
                if not isinstance(message, dict):
                    continue
                kind = message.get("type")
                # PTY writes and resizes (which persist the size) block: keep them off the loop.
                if kind == "input" and isinstance(message.get("data"), str):
                    await asyncio.to_thread(session.write_input, client_id, message["data"])
                elif kind == "resize":
                    with contextlib.suppress(TypeError, ValueError, KeyError):
                        cols, rows = int(message["cols"]), int(message["rows"])
                        await asyncio.to_thread(session.resize, client_id, cols, rows)

    # Whichever ends first (client gone, or the session exited and we closed) ends the other.
    tasks = {asyncio.create_task(pump()), asyncio.create_task(listen())}
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        session.detach(client_id)
