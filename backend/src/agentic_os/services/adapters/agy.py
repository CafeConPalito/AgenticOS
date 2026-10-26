"""Antigravity CLI: a workspace plugin in the project folder (ADR 0004).

agy has no per-session flags for instructions, MCP or hooks, but it discovers plugins in
`.agents/plugins/` of its working folder. The plugin is excluded from git, rewritten for
every run (new token) and removed when the run ends. agy connects the plugin's MCP server
asynchronously, so it starts without `-i` and the prompt is typed once the server sees it.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path

from agentic_os.models import Cli
from agentic_os.services import agy_status
from agentic_os.services.adapters.base import (
    PROPOSE_AGENT,
    CliAdapter,
    LaunchContext,
    agy_permissions,
    write_json,
)
from agentic_os.services.hooks import AGY_TOOL_MATCHER, HOOK_EVENTS, TOOL_EVENTS
from agentic_os.services.runs.launcher import LaunchSpec, clean_env, resolve_executable
from agentic_os.services.skills.format import AGY_MAX_BYTES

PLUGIN = Path(".agents") / "plugins" / "agentic-os"
EXCLUDE_LINE = ".agents/plugins/agentic-os/"
RUN_MARKER = "agenticOsRun"


def plugin_dir(cwd: Path) -> Path:
    return cwd / PLUGIN


def git_common_dir(cwd: Path) -> Path | None:
    """The repo's git dir, also for a worktree (whose `.git` is a file pointing to it)."""
    git = cwd / ".git"
    if git.is_dir():
        return git
    if not git.is_file():
        return None
    try:
        line = git.read_text("utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = (cwd / line.removeprefix("gitdir:").strip()).resolve()
    common = gitdir / "commondir"  # worktrees share info/exclude with the main repo
    if common.is_file():
        return (gitdir / common.read_text("utf-8").strip()).resolve()
    return gitdir


def exclude_from_git(cwd: Path) -> None:
    """Adds the plugin to `info/exclude` (local, never committed), once: it holds the run's
    token in its MCP URL."""
    git = git_common_dir(cwd)
    if git is None:  # not a repo
        return
    exclude = git / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text("utf-8") if exclude.exists() else ""
    if EXCLUDE_LINE in current.splitlines():
        return
    separator = "" if not current or current.endswith("\n") else "\n"
    exclude.write_text(f"{current}{separator}{EXCLUDE_LINE}\n", "utf-8")


def remove_plugin(cwd: Path, run_id: str) -> bool:
    """Removes our plugin if it belongs to `run_id` (never someone else's)."""
    folder = plugin_dir(cwd)
    try:
        marker = json.loads((folder / "plugin.json").read_text("utf-8")).get(RUN_MARKER)
    except (OSError, ValueError):
        return False
    if marker != run_id:
        return False
    shutil.rmtree(folder, ignore_errors=True)
    for parent in (folder.parent, folder.parent.parent):  # .agents/plugins, .agents
        with contextlib.suppress(OSError):
            parent.rmdir()  # only if empty
    return True


TASK_POINTER = " … (la tarea completa está en tus instrucciones, en la sección «Tarea»)"


def typed_prompt(prompt: str) -> str:
    """The prompt as typed into the TUI. Enter would send a multi-line prompt at its first
    line break, so only the first line is typed and the whole task goes into the rules."""
    prompt = prompt.strip()
    first, *rest = prompt.splitlines() or [""]
    text = f"{first.strip()[:200]}{TASK_POINTER}" if rest else prompt
    return f" {text}" if text.startswith("/") else text  # "/…" would be a slash command


def plugin_rules(instructions: str, prompt: str) -> str:
    if len(prompt.strip().splitlines()) <= 1:
        return instructions
    return f"{instructions.rstrip()}\n\n# Tarea\n{prompt.strip()}\n"


class AgyAdapter(CliAdapter):
    cli = Cli.AGY

    @staticmethod
    def _hook(ctx: LaunchContext, event: str) -> dict:
        return {"type": "command", "command": f"{ctx.hook_command} {event}"}

    def prepare(self, ctx: LaunchContext) -> LaunchSpec:
        prefix = resolve_executable(self.cli, ctx.overrides)
        folder = plugin_dir(ctx.cwd)
        shutil.rmtree(folder, ignore_errors=True)  # a stale plugin of ours would be replaced
        write_json(folder / "plugin.json", {"name": "agentic-os", RUN_MARKER: ctx.run_id})
        # agy expands no variables: the external connections carry their values in clear
        # (spike S2). The folder is ours alone, out of git, and removed when the run ends.
        servers: dict = {"agentic-os": {"url": ctx.mcp_url}}
        if not ctx.can_propose_agents:  # phase 19: the tool is not there (spike S2 of phase 18)
            servers["agentic-os"]["disabledTools"] = [PROPOSE_AGENT]
        if ctx.connections:
            servers |= ctx.connections.servers
        write_json(folder / "mcp_config.json", {"mcpServers": servers})
        # With skills, reading their SKILL.md is how agy loads one: that read is watched too.
        matcher = f"{AGY_TOOL_MATCHER}|read_file" if ctx.native_skills else AGY_TOOL_MATCHER
        # agy runs hooks through cmd.exe and mangles quoted paths: the short path, unquoted.
        # Tool events take a matcher and nested hooks (spike P9); the others, a flat list.
        hooks = {
            "agentic-os": {
                event: [
                    {"matcher": matcher, "hooks": [self._hook(ctx, event)]}
                    if event in TOOL_EVENTS
                    else self._hook(ctx, event)
                ]
                for event in HOOK_EVENTS[self.cli]
            }
        }
        write_json(folder / "hooks.json", hooks)
        # Phase 17, spike S2: our skills inside the plugin (agy skips a SKILL.md over 24 KB:
        # those are only reachable with use_skill).
        for skill in ctx.native_skills:
            if (skill / "SKILL.md").stat().st_size <= AGY_MAX_BYTES:
                shutil.copytree(skill, folder / "skills" / skill.name)
        rules = folder / "rules" / "AGENTS.md"
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text(plugin_rules(ctx.instructions, ctx.prompt), "utf-8")
        exclude_from_git(ctx.cwd)
        argv = [*prefix]
        if ctx.resume_session:  # the workspace plugin above is the new run's (evidence R1)
            argv += ["--conversation", ctx.resume_session]
        if ctx.model:
            argv += ["--model", ctx.model]
        argv += agy_permissions(ctx.permission_mode)
        for folder in ctx.extra_dirs:
            argv += ["--add-dir", folder]
        # With the opt-in status line installed (agy_status), this is how agy's script knows which
        # run to report its quota to; without it, nothing reads the variable.
        env = {
            **clean_env(),
            **ctx.account_env,
            **agy_status.environment(ctx.base_url, ctx.token),
        }
        return LaunchSpec(argv, env, ctx.resume_session)

    def deferred_prompt(self, ctx: LaunchContext) -> str | None:
        return typed_prompt(ctx.prompt)

    def cleanup(self, ctx: LaunchContext) -> None:
        remove_plugin(ctx.cwd, ctx.run_id)

    def recover(self, cwd: Path, run_id: str) -> None:
        remove_plugin(cwd, run_id)
