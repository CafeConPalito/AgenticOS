"""Where each CLI writes a session's transcript, for runs that never sent a hook with its path
(spike P8). The path a hook reports always wins over these."""

from __future__ import annotations

import os
import re
from pathlib import Path


def claude_config_dir(env: dict[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    configured = values.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def claude_project_slug(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", cwd)


def claude_transcript(cwd: str, session_id: str, config_dir: Path | None = None) -> Path:
    base = config_dir or claude_config_dir()
    return base / "projects" / claude_project_slug(cwd) / f"{session_id}.jsonl"


def agy_transcript(conversation_id: str, home: Path | None = None) -> Path:
    return (
        (home or Path.home())
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )
