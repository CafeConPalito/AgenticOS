"""What every CLI adapter shares: the launch context, the permission translation and the
run's files (ADR 0004 / 0008)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from agentic_os.models import Cli, PermissionMode
from agentic_os.services.runs.launcher import LaunchSpec


@dataclass(frozen=True)
class LaunchContext:
    run_id: str
    cli: Cli
    model: str
    prompt: str
    permission_mode: PermissionMode
    allowed_tools: tuple[str, ...]
    cwd: Path
    run_dir: Path  # <data_dir>/runs/<id>/: never inside the project
    base_url: str  # http://127.0.0.1:<port> of this backend
    token: str
    instructions: str
    hook_command: str  # e.g. C:\Users\…\HOOK~1.CMD (no spaces, no quotes)
    overrides: Mapping[str, list[str]] = field(default_factory=dict)
    # «Reanudar sesión» (phase 08): the CLI session to continue instead of starting a new one.
    resume_session: str | None = None

    @property
    def mcp_url(self) -> str:
        return f"{self.base_url}/r/{self.token}/mcp"


class CliAdapter(ABC):
    cli: Cli

    @abstractmethod
    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        """Writes the run's files and returns how to start the CLI."""

    def deferred_prompt(self, ctx: LaunchContext) -> str | None:
        """Prompt to type once the MCP server is connected (None: it is in the argv)."""
        return None

    def cleanup(self, ctx: LaunchContext) -> None:
        """Removes whatever the run left outside its run folder (nothing by default)."""
        return

    def recover(self, cwd: Path, run_id: str) -> None:
        """Cleans up after a run that was interrupted (backend crash, forced close)."""
        return


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return path


# Agent tools (phase 02) → Claude Code tool rules. "browser" has no Claude equivalent.
CLAUDE_TOOLS: dict[str, tuple[str, ...]] = {
    "read": ("Read", "Glob", "Grep"),
    "edit": ("Edit", "Write", "NotebookEdit"),
    "terminal": ("Bash", "PowerShell"),
    "git": ("Bash(git:*)", "PowerShell(git *)"),
    "web": ("WebFetch", "WebSearch"),
}
AGENTIC_OS_TOOLS = "mcp__agentic-os__*"


def claude_permissions(mode: PermissionMode, allowed_tools: tuple[str, ...]) -> list[str]:
    """`--permission-mode` and `--allowedTools` for an agent (spike P6, ADR 0004).

    Our own MCP tools are always pre-approved. In "autonomous" the list is not applied: denying
    tools on top of bypassPermissions is no barrier (the model can use the shell instead).
    """
    if mode == PermissionMode.AUTONOMOUS:
        return ["--permission-mode", "bypassPermissions", "--allowedTools", AGENTIC_OS_TOOLS]
    tools = [AGENTIC_OS_TOOLS]
    if mode == PermissionMode.RESTRICTED:
        for name in allowed_tools:
            tools += [t for t in CLAUDE_TOOLS.get(name, ()) if t not in tools]
        return ["--permission-mode", "acceptEdits", "--allowedTools", *tools]
    return ["--permission-mode", "manual", "--allowedTools", *tools]


def agy_permissions(mode: PermissionMode) -> list[str]:
    if mode == PermissionMode.AUTONOMOUS:
        return ["--dangerously-skip-permissions"]
    if mode == PermissionMode.RESTRICTED:
        return ["--mode", "accept-edits"]
    return []
