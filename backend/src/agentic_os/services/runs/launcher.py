"""Command line and environment to start an agent CLI interactively (spike: ADR 0003/0004).

The pieces shared by the CLI adapters (services/adapters): a clean environment, the
executable and a prompt that cannot be read as an option.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentic_os.errors import ApiError
from agentic_os.models.agent import Cli
from agentic_os.services import cli_paths

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
    path = cli_paths.which(EXECUTABLES[cli])
    if not path:
        raise ApiError(422, "cli_not_installed", f"{EXECUTABLES[cli]} is not installed", "cli")
    if Path(path).suffix.lower() in (".cmd", ".bat"):
        # cmd.exe would re-parse the command line: a prompt with `&`, `"` or `%VAR%` could run
        # other commands, and there is no reliable escaping. Only native executables.
        raise ApiError(
            422, "cli_shim_unsupported", f"{path} is a batch shim; install the native CLI", "cli"
        )
    return [path]


def safe_prompt(prompt: str) -> str:
    """A prompt starting with "-" would be parsed as an option (e.g. "--help …")."""
    return f" {prompt}" if prompt.startswith("-") else prompt
