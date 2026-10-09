import asyncio
from pathlib import Path

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from spike_mcp import SpikeMcp


def call(url: str, headers: dict[str, str] | None = None) -> str:
    async def go() -> str:
        async with (
            httpx2.AsyncClient(headers=headers or {}, timeout=10) as http,
            Client(streamable_http_client(url, http_client=http)) as client,
        ):
            result = await client.call_tool("report_status", {"message": "probando"})
            return result.content[0].text

    return asyncio.run(go())


def test_tool_calls_are_logged_with_the_run_token(tmp_path: Path):
    server = SpikeMcp({"run-a", "run-b"}, tmp_path / "calls.jsonl")
    server.start()
    try:
        assert "run-a" in call(server.url, {"Authorization": "Bearer run-a"})
        assert "run-b" in call(server.path_url("run-b"))
        calls = server.calls()
        assert [c["run"] for c in calls] == ["run-a", "run-b"]
        assert calls[0]["tool"] == "report_status"
        assert calls[0]["args"] == {"message": "probando"}
    finally:
        server.stop()


def test_unknown_token_is_rejected(tmp_path: Path):
    server = SpikeMcp({"run-a"}, tmp_path / "calls.jsonl")
    server.start()
    try:
        response = httpx.post(server.url, headers={"Authorization": "Bearer nope"}, json={})
        assert response.status_code == 401
        assert httpx.post(server.path_url("nope"), json={}).status_code == 401
        assert server.calls() == []
    finally:
        server.stop()
