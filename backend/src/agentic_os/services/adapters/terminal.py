"""How a terminal of the person's own starts (phase 23, ADR 0029): the CLI as they would open it,
with the chosen account, and only what the app needs to read its usage.

No instructions, no prompt, no MCP server and no permission flags: the CLI asks the person as
usual. The hooks and Claude's status line stay, because they tell the session's id, its
transcript and its cost (phase 07).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from agentic_os.models import Cli
from agentic_os.services.adapters.agy import (
    RUN_MARKER,
    exclude_from_git,
    plugin_dir,
    remove_plugin,
)
from agentic_os.services.adapters.base import CliAdapter, LaunchContext, write_json
from agentic_os.services.hooks import (
    AGY_TOOL_MATCHER,
    CLAUDE_TOOL_MATCHER,
    HOOK_EVENTS,
    STATUS_LINE,
    TOOL_EVENTS,
)
from agentic_os.services.runs.launcher import LaunchSpec, clean_env, resolve_executable


class TerminalClaudeAdapter(CliAdapter):
    cli = Cli.CLAUDE

    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        prefix = resolve_executable(self.cli, ctx.overrides)
        hooks = {
            event: [
                {"hooks": [{"type": "command", "command": f'"{ctx.hook_command}" {event}'}]}
                | ({"matcher": CLAUDE_TOOL_MATCHER} if event in TOOL_EVENTS else {})
            ]
            for event in HOOK_EVENTS[self.cli]
        }
        status_line = {"type": "command", "command": f'"{ctx.hook_command}" {STATUS_LINE}'}
        settings = write_json(
            ctx.run_dir / "settings.json", {"hooks": hooks, "statusLine": status_line}
        )
        session_id = str(uuid.uuid4())
        # The person's own settings, MCP servers and memory stay: only ours are added.
        argv = [*prefix, "--session-id", session_id, "--settings", str(settings)]
        return LaunchSpec(argv, {**clean_env(), **ctx.account_env}, session_id)


class TerminalAgyAdapter(CliAdapter):
    """agy reads hooks only from a workspace plugin: one of ours with nothing but the hooks, out
    of git and removed when the terminal closes (as in an agent's run)."""

    cli = Cli.AGY

    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        prefix = resolve_executable(self.cli, ctx.overrides)
        folder = plugin_dir(ctx.cwd)
        shutil.rmtree(folder, ignore_errors=True)
        write_json(folder / "plugin.json", {"name": "agentic-os", RUN_MARKER: ctx.run_id})

        def hook(event: str) -> dict:
            return {"type": "command", "command": f"{ctx.hook_command} {event}"}

        hooks = {
            "agentic-os": {
                event: [
                    {"matcher": AGY_TOOL_MATCHER, "hooks": [hook(event)]}
                    if event in TOOL_EVENTS
                    else hook(event)
                ]
                for event in HOOK_EVENTS[self.cli]
            }
        }
        write_json(folder / "hooks.json", hooks)
        exclude_from_git(ctx.cwd)
        return LaunchSpec([*prefix], {**clean_env(), **ctx.account_env}, None)

    def cleanup(self, ctx: LaunchContext) -> None:
        remove_plugin(ctx.cwd, ctx.run_id)

    def recover(self, cwd: Path, run_id: str) -> None:
        remove_plugin(cwd, run_id)


def terminal_adapter(cli: Cli) -> CliAdapter:
    return TerminalClaudeAdapter() if cli == Cli.CLAUDE else TerminalAgyAdapter()
