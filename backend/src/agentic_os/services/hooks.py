"""CLI hooks → Agentic OS (ADR 0008).

Each run gets a `hook.cmd` in its run folder that POSTs the hook payload (JSON on stdin) to
`/r/<token>/hook/<event>` with curl.exe (shipped with Windows 10/11, starts in milliseconds)
and **always exits 0**: a failing hook blocks the tool call in agy. The script is referenced by
its 8.3 short path because agy runs hook commands through cmd.exe and breaks quoted paths.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from pathlib import Path

from agentic_os.models import Activity, Cli

# Hooks each adapter registers. agy fires PreInvocation on every model step of a turn.
# Pre/PostToolUse are only for the CLIs' native subagents (spike P10): Claude's `Agent` tool
# (with SubagentStart/Stop), agy's `invoke_subagent` (agy hooks have no matcher: every tool).
HOOK_EVENTS: dict[Cli, tuple[str, ...]] = {
    Cli.CLAUDE: (
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "SessionEnd",
        "SubagentStart",
        "SubagentStop",
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
    ),
    Cli.AGY: ("PreInvocation", "Stop", "PreToolUse", "PostToolUse"),
}
# Claude: tool hooks restricted to these tools (`matcher`).
CLAUDE_TOOL_MATCHER = "Agent|Task"
AGY_TOOL_MATCHER = "invoke_subagent"
TOOL_EVENTS = {"PreToolUse", "PostToolUse"}
TURN_START = {"UserPromptSubmit", "PreInvocation"}
TURN_END = {"Stop"}


def short_path(path: Path) -> str:
    """8.3 path without spaces (Windows); the path itself elsewhere."""
    if sys.platform != "win32":
        return str(path)
    buffer = ctypes.create_unicode_buffer(1024)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else str(path)


def write_hook_script(run_dir: Path, base_url: str, token: str) -> str:
    """Writes the run's hook script and returns how to invoke it (no quotes, no spaces)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    url = f"{base_url}/r/{token}/hook"
    if sys.platform == "win32":
        script = run_dir / "hook.cmd"
        script.write_text(
            '@curl.exe -s -m 3 -o NUL -X POST -H "Content-Type: application/json" '
            f"--data-binary @- {url}/%1\r\n@exit /b 0\r\n",
            "ascii",
        )
    else:
        script = run_dir / "hook.sh"
        script.write_text(
            "#!/bin/sh\ncurl -s -m 3 -o /dev/null -X POST -H 'Content-Type: application/json' "
            f'--data-binary @- "{url}/$1"\nexit 0\n',
            "ascii",
        )
        script.chmod(0o755)
    return short_path(script)


@dataclass(frozen=True)
class HookEffect:
    activity: Activity | None = None
    turn_started: bool = False
    turn_ended: bool = False
    session_id: str | None = None
    # Claude PermissionRequest: «Bash: git push», «Write: nota.txt»…
    permission_request: str | None = None


def describe_tool(tool: object, tool_input: object) -> str:
    """A short human description of a tool call, from a hook payload."""
    name = str(tool or "")
    data = tool_input if isinstance(tool_input, dict) else {}
    for key in ("command", "file_path", "url", "pattern", "description", "path"):
        if data.get(key):
            return f"{name}: {data[key]}" if name else str(data[key])
    return name


def interpret(cli: Cli, event: str, payload: object) -> HookEffect:
    data = payload if isinstance(payload, dict) else {}
    session_id = data.get("conversationId") if cli == Cli.AGY else None
    if event == "PermissionRequest":
        return HookEffect(
            permission_request=describe_tool(data.get("tool_name"), data.get("tool_input"))
        )
    if event in TURN_START:
        return HookEffect(Activity.BUSY, turn_started=True, session_id=session_id)
    if event in TURN_END:
        return HookEffect(Activity.IDLE, turn_ended=True, session_id=session_id)
    return HookEffect(session_id=session_id)
