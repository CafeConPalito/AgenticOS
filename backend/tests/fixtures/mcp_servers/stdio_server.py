"""A stdio MCP server for the connection tests (phase 18). `PROBE_MODE` makes it misbehave:
`crash` (exits at once, saying why on stderr), `leak` (prints `$LEAK` on stderr and exits) and
`slow` (waits `PROBE_DELAY` seconds before it starts). `PROBE_EXTRA_TOOL=1` adds a tool."""

import os
import sys
import time

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

mode = os.environ.get("PROBE_MODE", "ok")
if mode == "crash":
    print("probe-server: fatal: cannot open database (simulated)", file=sys.stderr)
    sys.exit(3)
if mode == "leak":
    print(f"probe-server: fatal: bad token {os.environ.get('LEAK', '')}", file=sys.stderr)
    sys.exit(3)
if mode == "slow":
    time.sleep(float(os.environ.get("PROBE_DELAY", "20")))

server = MCPServer("probe-stdio")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def read_note(topic: str) -> str:
    """Read the note about a topic."""
    return f"NOTE[{topic}]=PROBE-READ-4417"


@server.tool(annotations=ToolAnnotations(destructive_hint=True))
def write_note(topic: str, text: str) -> str:
    """Overwrite the note about a topic."""
    return f"WROTE[{topic}]=PROBE-WRITE-9082"


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def show_env(name: str) -> str:
    """Return the value of an environment variable of the server process."""
    return f"ENV[{name}]={os.environ.get(name, '<unset>')}"


if os.environ.get("PROBE_EXTRA_TOOL"):

    @server.tool()
    def extra() -> str:
        """A tool that appears later."""
        return "EXTRA"


if __name__ == "__main__":
    server.run("stdio")
