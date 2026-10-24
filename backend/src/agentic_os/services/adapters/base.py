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
    # The login the run uses (phase 10): the environment that points the CLI to its folder.
    # Empty for the system account, which is the CLI's own configuration.
    account_env: Mapping[str, str] = field(default_factory=dict)
    # Linked repositories outside `cwd` (phase 12): the CLI is told it may work there too.
    extra_dirs: tuple[str, ...] = ()
    # The project lets agents use git freely (phase 12): no permission prompt for it.
    git_authorized: bool = False
    # The run's skills, one folder each (phase 17): passed to the CLI's own skill mechanism.
    skills_dir: Path | None = None

    @property
    def native_skills(self) -> list[Path]:
        if self.skills_dir is None or not self.skills_dir.is_dir():
            return []
        return sorted(p for p in self.skills_dir.iterdir() if (p / "SKILL.md").is_file())

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


def claude_permissions(
    mode: PermissionMode,
    allowed_tools: tuple[str, ...],
    git_authorized: bool = False,
    skills: bool = False,
) -> list[str]:
    """`--permission-mode` and `--allowedTools` for an agent (spike P6, ADR 0004).

    Our own MCP tools are always pre-approved. In "autonomous" the list is not applied: denying
    tools on top of bypassPermissions is no barrier (the model can use the shell instead).
    With `git_authorized` (phase 12, spike S2) git is allowed in every other mode: both rules are
    needed, Claude uses the Bash tool or the PowerShell one.
    """
    if mode == PermissionMode.AUTONOMOUS:
        return ["--permission-mode", "bypassPermissions", "--allowedTools", AGENTIC_OS_TOOLS]
    tools = [AGENTIC_OS_TOOLS]
    if skills:  # loading a skill only reads its instructions; its scripts still ask (S1)
        tools.append("Skill")
    if git_authorized:
        tools += CLAUDE_TOOLS["git"]
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
