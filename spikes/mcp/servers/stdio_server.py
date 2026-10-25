"""Probe MCP server over stdio: a read-only tool, a destructive one and one that echoes env."""

import os
import sys
import time

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

mode = os.environ.get("PROBE_MODE", "ok")
if mode == "crash":
    print("probe-server: fatal: cannot open database (simulated)", file=sys.stderr)
    sys.exit(3)
if mode == "slow":
    time.sleep(float(os.environ.get("PROBE_DELAY", "20")))

server = MCPServer("probe-stdio")


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def read_note(topic: str) -> str:
    """Read the note about a topic."""
    return f"NOTE[{topic}]=PROBE-READ-4417"


@server.tool(annotations=ToolAnnotations(destructiveHint=True))
def write_note(topic: str, text: str) -> str:
    """Overwrite the note about a topic."""
    return f"WROTE[{topic}]=PROBE-WRITE-9082"


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def show_env(name: str) -> str:
    """Return the value of an environment variable of the server process."""
    return f"ENV[{name}]={os.environ.get(name, '<unset>')}"


@server.tool()
def pid() -> str:
    """Return the process id of the server."""
    return f"PID={os.getpid()}"


if __name__ == "__main__":
    server.run("stdio")
