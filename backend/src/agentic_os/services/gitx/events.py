"""Live events of the Git tab: job progress and «this repository changed» (phase 12).

Producers (job threads, request threads) call `publish` from anywhere; each WebSocket client
reads its own queue on the event loop it lives in.
"""

from __future__ import annotations

import asyncio
import threading

import structlog

log = structlog.get_logger()

MAX_QUEUE = 500  # a client that cannot keep up loses its oldest events, not the server's memory


class GitEvents:
    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue[dict], asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(MAX_QUEUE)
        with self._lock:
            self._subscribers[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    def publish(self, event: dict) -> None:
        with self._lock:
            targets = list(self._subscribers.items())
        for queue, loop in targets:
            try:
                loop.call_soon_threadsafe(self._put, queue, event)
            except RuntimeError:  # that loop is closed: the client is gone
                self.unsubscribe(queue)

    @staticmethod
    def _put(queue: asyncio.Queue[dict], event: dict) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)

    def changed(self, repo_id: str) -> None:
        self.publish({"type": "repo_changed", "repo_id": repo_id})
