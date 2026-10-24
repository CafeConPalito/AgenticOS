"""Probe MCP server over streamable HTTP; every request needs `X-Probe-Key: <PROBE_KEY>`."""

import os
import sys

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse

KEY = os.environ.get("PROBE_KEY", "probe-secret-1234")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

server = MCPServer("probe-http")


@server.tool()
def ping(text: str) -> str:
    """Echo a text."""
    return f"PONG[{text}]=PROBE-HTTP-5521"


app = server.streamable_http_app(streamable_http_path="/mcp")


class Auth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            if headers.get("x-probe-key") != KEY:
                await PlainTextResponse("unauthorized", status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app = Auth(app)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
