import asyncio
import subprocess
import sys
import time

import httpx
import httpx2
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from mcp import ClientSession, StdioServerParameters


async def stdio():
    p = StdioServerParameters(command=sys.executable, args=["mcp/servers/stdio_server.py"])
    async with stdio_client(p) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = (await s.list_tools()).tools
        print("stdio:", [(t.name, t.annotations and t.annotations.read_only_hint) for t in tools])
        print((await s.call_tool("read_note", {"topic": "x"})).content[0].text)


async def http():
    srv = subprocess.Popen([sys.executable, "mcp/servers/http_server.py", "8765"])
    time.sleep(3)
    try:
        print("no key:", httpx.post("http://127.0.0.1:8765/mcp", json={}).status_code)
        async with (
            httpx2.AsyncClient(headers={"X-Probe-Key": "probe-secret-1234"}) as c,
            streamable_http_client("http://127.0.0.1:8765/mcp", http_client=c) as (r, w),
        ):
            async with ClientSession(r, w) as s:
                await s.initialize()
                print("http:", [t.name for t in (await s.list_tools()).tools])
    finally:
        srv.kill()


asyncio.run(stdio())
asyncio.run(http())
