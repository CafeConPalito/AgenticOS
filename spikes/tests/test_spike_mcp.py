import asyncio
from pathlib import Path

import httpx

from mcp import Client
from spike_mcp import SpikeMcp

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def call_tool(url: str) -> str:
    async def go() -> str:
        async with Client(url) as client:
            result = await client.call_tool("report_status", {"message": "probando"})
            return result.content[0].text

    return asyncio.run(go())


def test_tool_calls_are_logged_with_the_run_token(tmp_path: Path):
    server = SpikeMcp({"run-a"}, tmp_path / "calls.jsonl")
    server.start()
    try:
        assert "run-a" in call_tool(server.path_url("run-a"))
        calls = server.calls()
        assert [c["run"] for c in calls] == ["run-a"]
        assert calls[0]["tool"] == "report_status"
        assert calls[0]["args"] == {"message": "probando"}
    finally:
        server.stop()


def test_bearer_token_is_accepted(tmp_path: Path):
    server = SpikeMcp({"run-b"}, tmp_path / "calls.jsonl")
    server.start()
    try:
        response = httpx.post(
            server.url,
            headers={"Authorization": "Bearer run-b", **MCP_HEADERS},
            json=INITIALIZE,
        )
        assert response.status_code == 200
    finally:
        server.stop()


def test_unknown_token_is_rejected(tmp_path: Path):
    server = SpikeMcp({"run-a"}, tmp_path / "calls.jsonl")
    server.start()
    try:
        bad = {"Authorization": "Bearer nope", **MCP_HEADERS}
        assert httpx.post(server.url, headers=bad, json=INITIALIZE).status_code == 401
        no_token = httpx.post(server.url, headers=MCP_HEADERS, json=INITIALIZE)
        assert no_token.status_code == 401
        path_token = httpx.post(server.path_url("nope"), headers=MCP_HEADERS, json=INITIALIZE)
        assert path_token.status_code == 401
        assert server.calls() == []
    finally:
        server.stop()
