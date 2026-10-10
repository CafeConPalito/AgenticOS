"""CLI adapters: how each agent CLI gets its instructions, MCP server, hooks and permissions."""

from agentic_os.models import Cli
from agentic_os.services.adapters.agy import AgyAdapter
from agentic_os.services.adapters.base import CliAdapter, LaunchContext
from agentic_os.services.adapters.claude import ClaudeAdapter

ADAPTERS: dict[Cli, CliAdapter] = {Cli.CLAUDE: ClaudeAdapter(), Cli.AGY: AgyAdapter()}


def adapter_for(cli: Cli) -> CliAdapter:
    return ADAPTERS[cli]


__all__ = ["CliAdapter", "LaunchContext", "adapter_for"]
