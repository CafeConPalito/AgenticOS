"""Probe of the Architect's MCP server over streamable HTTP (phase 19, spikes S1–S2).

Read-only tools over a fake installation plus `update_sheet`, which keeps the sheet in memory.
Every call is appended to the JSONL file in ARCH_LOG (time, tool, arguments) so a spike can
see when the sheet changed relative to the CLI's turn. Requests need
`Authorization: Bearer <ARCH_TOKEN>`.

Usage: python architect_server.py <port>
"""

import json
import os
import sys
import time

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse

TOKEN = os.environ.get("ARCH_TOKEN", "arch-token-0001")
LOG = os.environ.get("ARCH_LOG", "")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766

server = MCPServer("architect")
SHEET: dict = {}
LOCKED = {"color"}


def _log(tool: str, args: dict) -> None:
    if LOG:
        with open(LOG, "a", encoding="utf-8") as fh:
            entry = {"t": time.time(), "token": TOKEN, "tool": tool, "args": args}
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@server.tool()
def list_clis() -> str:
    """CLIs instalados, con sus cuentas y los modelos que admite cada uno."""
    _log("list_clis", {})
    return json.dumps(
        [
            {"cli": "claude", "accounts": ["personal"], "models": ["haiku", "sonnet", "opus"]},
            {"cli": "agy", "accounts": ["trabajo"], "models": ["gemini-3.8-flash-low"]},
        ]
    )


@server.tool()
def search_skills(query: str) -> str:
    """Busca skills de la biblioteca por texto. Devuelve nombre y descripción."""
    _log("search_skills", {"query": query})
    return json.dumps(
        [
            {"name": "tono-de-marca", "description": "Guía de estilo y tono de la marca."},
            {"name": "seo-basico", "description": "Títulos, metadescripciones y enlaces."},
        ]
    )


@server.tool()
def get_sheet() -> str:
    """La ficha actual del agente y los campos fijados por el usuario."""
    _log("get_sheet", {})
    return json.dumps({"sheet": SHEET, "locked": sorted(LOCKED)}, ensure_ascii=False)


@server.tool()
def update_sheet(patch: dict) -> str:
    """Cambia campos de la ficha del agente (name, role, description, cli, model,
    instructions, permission_mode, skills). Los campos fijados por el usuario no se cambian."""
    _log("update_sheet", {"patch": patch})
    refused = sorted(set(patch) & LOCKED)
    SHEET.update({k: v for k, v in patch.items() if k not in LOCKED})
    answer = {"ok": True, "sheet": SHEET}
    if refused:
        answer["refused"] = {k: "campo fijado por el usuario" for k in refused}
    return json.dumps(answer, ensure_ascii=False)


app = server.streamable_http_app(streamable_http_path="/mcp")


class Auth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            if headers.get("authorization") != f"Bearer {TOKEN}":
                await PlainTextResponse("unauthorized", status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app = Auth(app)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
