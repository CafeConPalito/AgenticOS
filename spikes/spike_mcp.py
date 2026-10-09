"""P5: minimal `agentic-os` MCP server (streamable HTTP) with per-run tokens.

A run is identified by a token, sent either as `Authorization: Bearer <token>` or in the URL
path (`/r/<token>/mcp`) for CLIs that cannot send headers. Every tool call is appended to a
JSONL log so a scenario can prove which run called what.

Usage (standalone): uv run python spike_mcp.py <token> [<token>...]
"""

from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
from mcp.server.mcpserver import Context, MCPServer

RUN_HEADER = "x-agentic-run"
PATH_TOKEN = re.compile(r"^/r/([A-Za-z0-9_-]+)(/mcp.*)$")


class TokenGate:
    """ASGI middleware: accepts only known run tokens and exposes them as a header."""

    def __init__(self, app, tokens: set[str]) -> None:
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = None
        match = PATH_TOKEN.match(scope["path"])
        if match:
            token = match.group(1)
            scope = {**scope, "path": match.group(2), "raw_path": match.group(2).encode()}
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        if not token and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if token not in self.tokens:
            body = json.dumps({"error": "unknown run token"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        scope["headers"] = [
            *[(k, v) for k, v in scope.get("headers") or [] if k != RUN_HEADER.encode()],
            (RUN_HEADER.encode(), token.encode()),
        ]
        await self.app(scope, receive, send)


class SpikeMcp:
    def __init__(self, tokens: set[str], log_path: Path) -> None:
        self.tokens = tokens
        self.log_path = log_path
        self.port: int | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def _record(self, ctx: Context, tool: str, args: dict) -> str:
        headers = ctx.headers or {}
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "run": headers.get(RUN_HEADER),
            "tool": tool,
            "args": args,
            "user_agent": headers.get("user-agent"),
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return f"ok ({tool} registrado para la ejecución {entry['run']})"

    def build_app(self):
        server = MCPServer(
            "agentic-os",
            instructions=(
                "Servidor de coordinación de Agentic OS. Informa de tu progreso con "
                "report_status y llama a complete_task cuando termines la tarea."
            ),
        )

        @server.tool()
        def report_status(message: str, ctx: Context) -> str:
            """Informa a Agentic OS de en qué estás trabajando ahora mismo."""
            return self._record(ctx, "report_status", {"message": message})

        @server.tool()
        def complete_task(summary: str, ctx: Context) -> str:
            """Marca la tarea actual como terminada, con un resumen del resultado."""
            return self._record(ctx, "complete_task", {"summary": summary})

        return TokenGate(server.streamable_http_app(), self.tokens)

    def start(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(self.build_app(), log_level="warning", lifespan="on")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return self.url

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"

    def path_url(self, token: str) -> str:
        return f"http://127.0.0.1:{self.port}/r/{token}/mcp"

    def calls(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text("utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)


if __name__ == "__main__":
    mcp_server = SpikeMcp(set(sys.argv[1:]) or {"dev"}, Path("mcp-calls.jsonl"))
    print("listening on", mcp_server.start())
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mcp_server.stop()
