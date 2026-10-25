"""Claude Code: everything through flags and files in the run folder (ADR 0004)."""

from __future__ import annotations

import uuid

from agentic_os.models import Cli
from agentic_os.services.adapters.base import (
    CliAdapter,
    LaunchContext,
    claude_permissions,
    write_json,
)
from agentic_os.services.hooks import CLAUDE_TOOL_MATCHER, HOOK_EVENTS, STATUS_LINE, TOOL_EVENTS
from agentic_os.services.runs.launcher import (
    LaunchSpec,
    clean_env,
    resolve_executable,
    safe_prompt,
)
from agentic_os.services.skills.runtime import PLUGIN_NAME


class ClaudeAdapter(CliAdapter):
    cli = Cli.CLAUDE

    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        prefix = resolve_executable(self.cli, ctx.overrides)
        run_dir = ctx.run_dir
        instructions = run_dir / "instructions.md"
        instructions.parent.mkdir(parents=True, exist_ok=True)
        instructions.write_text(ctx.instructions, "utf-8")
        # Claude runs hooks through a shell (Git Bash on Windows): a quoted path keeps the
        # backslashes literal.
        hooks = {
            event: [
                {"hooks": [{"type": "command", "command": f'"{ctx.hook_command}" {event}'}]}
                | ({"matcher": CLAUDE_TOOL_MATCHER} if event in TOOL_EVENTS else {})
            ]
            for event in HOOK_EVENTS[self.cli]
        }
        # The status line reports the session's cost after every turn (phase 07): Claude only
        # writes its exact totals to the transcript when the session closes.
        status_line = {"type": "command", "command": f'"{ctx.hook_command}" {STATUS_LINE}'}
        settings = write_json(
            run_dir / "settings.json", {"hooks": hooks, "statusLine": status_line}
        )
        mcp = write_json(
            run_dir / "mcp.json",
            {
                "mcpServers": {
                    "agentic-os": {
                        "type": "http",
                        "url": f"{ctx.base_url}/r/mcp",
                        "headers": {"Authorization": f"Bearer {ctx.token}"},
                    },
                    # Phase 18: the external connections; their secrets are ${AOS_MCP_…}
                    # references to the environment below, never values (spike S1).
                    **(ctx.connections.servers if ctx.connections else {}),
                }
            },
        )
        # A resumed session keeps its id and transcript; the configuration below is the new
        # run's (evidence R1: hooks and MCP are not stored in the session).
        session_id = ctx.resume_session or str(uuid.uuid4())
        session_flag = "--resume" if ctx.resume_session else "--session-id"
        # The prompt goes first: variadic options (--allowedTools, --mcp-config) would swallow
        # a trailing positional prompt.
        argv = [
            *prefix,
            safe_prompt(ctx.prompt),
            session_flag,
            session_id,
            "--setting-sources",
            "project,local",
            "--settings",
            str(settings),
            "--mcp-config",
            str(mcp),
            "--strict-mcp-config",
            "--append-system-prompt-file",
            str(instructions),
            *claude_permissions(
                ctx.permission_mode,
                ctx.allowed_tools,
                ctx.git_authorized,
                skills=bool(ctx.native_skills),
                connections=ctx.connections,
            ),
        ]
        if ctx.model:
            argv += ["--model", ctx.model]
        for folder in ctx.extra_dirs:  # one flag each: --add-dir is variadic
            argv += ["--add-dir", folder]
        if ctx.native_skills:  # phase 17, spike S1: our skills for this session only
            plugin = ctx.skills_dir.parent
            write_json(plugin / ".claude-plugin" / "plugin.json", {"name": PLUGIN_NAME})
            argv += ["--plugin-dir", str(plugin)]
        # The account's folder wins over a CLAUDE_CONFIG_DIR of the person (system account:
        # nothing is added and their own value, if any, is kept).
        env = {**clean_env(), **ctx.account_env}
        if ctx.connections:
            env |= ctx.connections.env
            # A slow server (the first `npx` downloads it) gets time before Claude gives up on it.
            env["MCP_TIMEOUT"] = str(ctx.connections.startup_timeout * 1000)
        return LaunchSpec(argv, env, session_id)
