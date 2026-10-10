"""Command line and environment to start an agent CLI interactively (spike: ADR 0003/0004).

Phase 03 keeps it minimal: every run uses the "ask" permission mode and no injected
instructions or MCP; the adapters of phase 04 replace this with the full per-agent setup.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from agentic_os.errors import ApiError
from agentic_os.models.agent import Cli

# Markers a running Claude Code session sets for its children. Inherited by a spawned CLI they
# disable transcripts and alter behaviour. User configuration (CLAUDE_CONFIG_DIR,
# CLAUDE_CODE_GIT_BASH_PATH, CLAUDE_CODE_USE_BEDROCK…) is deliberately kept.
SESSION_MARKERS = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_PID",
        "CLAUDE_EFFORT",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_SESSION_ATTENDED",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_AGENT_SDK_VERSION",
    }
)

EXECUTABLES = {Cli.CLAUDE: "claude", Cli.AGY: "agy"}


@dataclass(frozen=True)
class LaunchSpec:
    argv: list[str]
    env: dict[str, str]
    session_id: str | None


def clean_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if base is None else base
    return {k: v for k, v in source.items() if k.upper() not in SESSION_MARKERS}


def resolve_executable(cli: Cli, overrides: Mapping[str, list[str]] | None = None) -> list[str]:
    """argv prefix that starts the CLI (an override replaces it, e.g. the fake CLI in tests)."""
    if overrides and cli.value in overrides:
        return list(overrides[cli.value])
    path = shutil.which(EXECUTABLES[cli])
    if not path:
        raise ApiError(422, "cli_not_installed", f"{EXECUTABLES[cli]} is not installed", "cli")
    return [path]


def build_launch(
    cli: Cli,
    model: str,
    prompt: str,
    overrides: Mapping[str, list[str]] | None = None,
) -> LaunchSpec:
    prefix = resolve_executable(cli, overrides)
    if cli == Cli.CLAUDE:
        session_id = str(uuid.uuid4())
        # The prompt goes first: variadic options would swallow a trailing positional prompt.
        argv = [
            *prefix,
            prompt,
            "--session-id",
            session_id,
            "--setting-sources",
            "project,local",
            "--strict-mcp-config",
            "--permission-mode",
            "manual",
        ]
        if model:
            argv += ["--model", model]
        return LaunchSpec(argv, clean_env(), session_id)
    argv = [*prefix]
    if model:
        argv += ["--model", model]
    argv += ["-i", prompt]
    return LaunchSpec(argv, clean_env(), None)
