"""P8: token usage (and cost when available) per CLI session, read from the CLIs' own files.

- Claude Code: ~/.claude/projects/<cwd-slug>/<session-id>.jsonl. The latest `cost-state` row
  holds totalCostUSD and per-model usage for the whole session; assistant rows hold per-message
  usage (fallback). Subagents have their own files under <session-id>/subagents/.
- Antigravity CLI: ~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/
  transcript_full.jsonl, with input/output/cache tokens per step. No cost is recorded.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

HOME = Path.home()


@dataclass
class Usage:
    source: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float | None = None
    models: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------------------- Claude Code
def claude_project_slug(cwd: Path | str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", str(cwd))


def claude_transcript(cwd: Path | str, session_id: str, home: Path = HOME) -> Path:
    return home / ".claude" / "projects" / claude_project_slug(cwd) / f"{session_id}.jsonl"


def _rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def claude_usage(transcript: Path) -> Usage:
    rows = _rows(transcript)
    states = [r for r in rows if r.get("type") == "cost-state"]
    if states:
        state = states[-1]
        usage = Usage("claude:cost-state", cost_usd=state.get("totalCostUSD"))
        for model, m in (state.get("modelUsage") or {}).items():
            usage.models[model] = m
            usage.input_tokens += m.get("inputTokens", 0)
            usage.output_tokens += m.get("outputTokens", 0)
            usage.cache_read_tokens += m.get("cacheReadInputTokens", 0)
            usage.cache_creation_tokens += m.get("cacheCreationInputTokens", 0)
            usage.thinking_tokens += m.get("thinkingTokens", 0)
        return usage

    # Fallback: per-message usage (one row per API message; de-duplicate by message id).
    usage = Usage("claude:assistant-rows")
    seen: set[str] = set()
    for row in rows:
        message = row.get("message") or {}
        if row.get("type") != "assistant" or not message.get("usage"):
            continue
        key = message.get("id") or row.get("requestId") or row.get("uuid")
        if key in seen:
            continue
        seen.add(key)
        u = message["usage"]
        usage.input_tokens += u.get("input_tokens", 0)
        usage.output_tokens += u.get("output_tokens", 0)
        usage.cache_read_tokens += u.get("cache_read_input_tokens", 0)
        usage.cache_creation_tokens += u.get("cache_creation_input_tokens", 0)
        usage.thinking_tokens += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0)
        model = message.get("model", "?")
        usage.models.setdefault(model, {"messages": 0})["messages"] += 1
    return usage


# ---------------------------------------------------------------------------- Antigravity
def agy_transcript(conversation_id: str, home: Path = HOME) -> Path:
    return (
        home
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )


def agy_usage(transcript: Path) -> Usage:
    usage = Usage("agy:transcript_full")
    for row in _rows(transcript):
        usage.input_tokens += row.get("input_tokens", 0) or 0
        usage.output_tokens += row.get("output_tokens", 0) or 0
        usage.cache_read_tokens += row.get("cache_read_tokens", 0) or 0
        usage.thinking_tokens += row.get("thinking_tokens", 0) or 0
    return usage
