"""How the Architect's CLI is started (phase 19, spikes S1-S2, plan changes 1-3).

Like an agent's run (ADR 0004) but with the Architect's MCP server instead of `agentic-os`
and none of the CLI's own tools: Claude gets `--tools ""` and only `mcp__architect__*`; agy has
no such flag, so its PreToolUse hook (the guard script) asks the backend, which denies anything
but a call to the Architect's server. Its first message goes like any other: pasted.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path

from agentic_os.models import Cli
from agentic_os.services.adapters.base import CliAdapter, LaunchContext, write_json
from agentic_os.services.adapters.claude import ClaudeAdapter
from agentic_os.services.hooks import HOOK_EVENTS, TOOL_EVENTS, write_guard_script
from agentic_os.services.runs.launcher import LaunchSpec, clean_env, resolve_executable

SERVER = "architect"
CLAUDE_TOOLS = f"mcp__{SERVER}__*"
# agy names a plugin's servers «<plugin>_<server>» (phase 18, spike S2).
AGY_SERVER = f"{SERVER}_{SERVER}"
AGY_PLUGIN = Path(".agents") / "plugins" / SERVER
RUN_MARKER = "agenticOsRun"


def mcp_url(base_url: str) -> str:
    return f"{base_url}/a/mcp"


class ArchitectClaudeAdapter(ClaudeAdapter):
    def mcp_servers(self, ctx: LaunchContext) -> dict:
        return {
            SERVER: {
                "type": "http",
                "url": mcp_url(ctx.base_url),
                "headers": {"Authorization": f"Bearer {ctx.token}"},
            }
        }

    def permission_args(self, ctx: LaunchContext) -> list[str]:
        # No tool of its own (spike S1): only the Architect's, without asking.
        return ["--tools", "", "--allowedTools", CLAUDE_TOOLS]


class ArchitectAgyAdapter(CliAdapter):
    cli = Cli.AGY

    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        prefix = resolve_executable(self.cli, ctx.overrides)
        folder = ctx.cwd / AGY_PLUGIN
        shutil.rmtree(folder, ignore_errors=True)
        write_json(folder / "plugin.json", {"name": SERVER, RUN_MARKER: ctx.run_id})
        server = {"url": mcp_url(ctx.base_url), "headers": {"Authorization": f"Bearer {ctx.token}"}}
        write_json(folder / "mcp_config.json", {"mcpServers": {SERVER: server}})
        guard = write_guard_script(ctx.run_dir, ctx.base_url, ctx.token)
        hooks: dict[str, list] = {}
        for event in HOOK_EVENTS[self.cli]:
            if event == "PreToolUse":  # every tool, through the guard
                hooks[event] = [{"matcher": "*", "hooks": [self._command(guard)]}]
            elif event in TOOL_EVENTS:
                hooks[event] = [
                    {"matcher": "*", "hooks": [self._command(f"{ctx.hook_command} {event}")]}
                ]
            else:
                hooks[event] = [self._command(f"{ctx.hook_command} {event}")]
        write_json(folder / "hooks.json", {SERVER: hooks})
        rules = folder / "rules" / "AGENTS.md"
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text(ctx.instructions, "utf-8")
        argv = [*prefix]
        if ctx.resume_session:
            argv += ["--conversation", ctx.resume_session]
        if ctx.model:
            argv += ["--model", ctx.model]
        # Its tools are denied by the guard; the Architect's MCP calls must not ask.
        argv.append("--dangerously-skip-permissions")
        return LaunchSpec(argv, {**clean_env(), **ctx.account_env}, ctx.resume_session)

    @staticmethod
    def _command(command: str) -> dict:
        return {"type": "command", "command": command}

    def deferred_prompt(self, ctx: LaunchContext) -> str | None:
        return ctx.prompt  # after `/mcp` (spike S2), pasted

    def cleanup(self, ctx: LaunchContext) -> None:
        self.recover(ctx.cwd, ctx.run_id)

    def recover(self, cwd: Path, run_id: str) -> None:
        folder = cwd / AGY_PLUGIN
        try:
            marker = json.loads((folder / "plugin.json").read_text("utf-8")).get(RUN_MARKER)
        except (OSError, ValueError):
            return
        if marker != run_id:
            return
        shutil.rmtree(folder, ignore_errors=True)
        for parent in (folder.parent, folder.parent.parent):
            with contextlib.suppress(OSError):
                parent.rmdir()


def guard_allows(cli: Cli, payload: object) -> bool:
    """Whether the tool in a PreToolUse payload of the Architect may run: only its own MCP
    server's tools."""
    data = payload if isinstance(payload, dict) else {}
    if cli == Cli.AGY:
        call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        return call.get("name") == "call_mcp_tool" and args.get("ServerName") == AGY_SERVER
    return str(data.get("tool_name", "")).startswith(f"mcp__{SERVER}__")
