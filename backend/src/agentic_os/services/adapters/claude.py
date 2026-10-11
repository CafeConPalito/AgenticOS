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
from agentic_os.services.hooks import CLAUDE_TOOL_MATCHER, HOOK_EVENTS, TOOL_EVENTS
from agentic_os.services.runs.launcher import (
    LaunchSpec,
    clean_env,
    resolve_executable,
    safe_prompt,
)


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
        settings = write_json(run_dir / "settings.json", {"hooks": hooks})
        mcp = write_json(
            run_dir / "mcp.json",
            {
                "mcpServers": {
                    "agentic-os": {
                        "type": "http",
                        "url": f"{ctx.base_url}/r/mcp",
                        "headers": {"Authorization": f"Bearer {ctx.token}"},
                    }
                }
            },
        )
        session_id = str(uuid.uuid4())
        # The prompt goes first: variadic options (--allowedTools, --mcp-config) would swallow
        # a trailing positional prompt.
        argv = [
            *prefix,
            safe_prompt(ctx.prompt),
            "--session-id",
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
            *claude_permissions(ctx.permission_mode, ctx.allowed_tools),
        ]
        if ctx.model:
            argv += ["--model", ctx.model]
        return LaunchSpec(argv, clean_env(), session_id)
