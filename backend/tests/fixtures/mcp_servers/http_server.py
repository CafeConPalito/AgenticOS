"""A streamable HTTP MCP server for the connection tests (phase 18): every request needs the
header `X-Probe-Key: <key>`."""

import threading
import time

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse


def build_app(key: str):
    server = MCPServer("probe-http")

    @server.tool()
    def ping(text: str) -> str:
        """Echo a text."""
        return f"PONG[{text}]=PROBE-HTTP-5521"

    inner = server.streamable_http_app(streamable_http_path="/mcp")

    class Auth:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
                if headers.get("x-probe-key") != key:
                    await PlainTextResponse("unauthorized", status_code=401)(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    return Auth(inner)  # the lifespan scope goes through to the MCP app


class Running:
    """The server in a thread of the test process, on a free port."""

    def __init__(self, key: str, port: int) -> None:
        app = build_app(key)
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", lifespan="auto"
        )
        self.server = uvicorn.Server(config)
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "Running":
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
