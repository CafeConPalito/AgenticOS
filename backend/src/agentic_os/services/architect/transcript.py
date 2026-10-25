"""The Architect's replies, read from the CLI's own transcript (phase 19, spikes S1-S2).

The chat shows clean text, not the terminal: Claude writes each assistant block to its JSONL
transcript as it goes (`{"type": "assistant", "message": {"content": [{"type": "text"…}]}}`)
and agy writes `PLANNER_RESPONSE` steps (`{"type": "PLANNER_RESPONSE", "content": "…"}`). A
reader remembers how far it got, so a turn's text arrives block by block while the turn runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_os.models import Cli


def _claude_text(entry: dict) -> list[str]:
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content") or []
    return [
        block["text"].strip()
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and str(block.get("text", "")).strip()
    ]


def _agy_text(entry: dict) -> list[str]:
    if entry.get("type") != "PLANNER_RESPONSE":
        return []
    text = str(entry.get("content") or "").strip()
    return [text] if text else []


def replies(cli: Cli, lines: list[str]) -> list[str]:
    """The reply texts in these transcript lines, in order."""
    read = _claude_text if cli == Cli.CLAUDE else _agy_text
    found: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            found += read(entry)
    return found


class TranscriptReader:
    """Reads the new replies of one transcript from where it stopped. Only whole lines count:
    the CLI may be writing the last one."""

    def __init__(self, cli: Cli, path: str | Path, start_at_end: bool = True) -> None:
        self.cli = cli
        self.path = Path(path)
        self.offset = self._size() if start_at_end else 0

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def read_new(self) -> list[str]:
        try:
            with self.path.open("rb") as file:
                file.seek(self.offset)
                data = file.read()
        except OSError:
            return []
        end = data.rfind(b"\n")
        if end < 0:
            return []
        self.offset += end + 1
        lines = data[: end + 1].decode("utf-8", "replace").splitlines()
        return replies(self.cli, lines)
