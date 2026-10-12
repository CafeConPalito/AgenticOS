"""Token usage (and cost when the CLI records it) from the CLIs' own transcripts (ADR 0005, 0011).

- Claude Code: the latest `cost-state` row holds the exact totals of the whole session (with its
  native subagents), but it is only written when the session closes. Until then, the
  `assistant` rows (one per content block; the same `message.id` repeats its usage) give an
  approximation that misses Claude's internal calls (evidence C0).
- agy: one `PLANNER_RESPONSE` row per model call with its tokens. No cost.

The formats are internal and undocumented: unknown rows and fields are ignored, broken lines
are skipped, and a transcript with nothing useful yields `None` («consumo no disponible»).
Transcripts only grow, so each one is read incrementally from where the last read stopped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COST_STATE = "cost-state"
ASSISTANT_ROWS = "assistant-rows"
TRANSCRIPT_FULL = "transcript_full"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    # Per model: the same counters (and `cost_usd` when known).
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    source: str = ""

    def add(self, other: Usage) -> Usage:
        """Sum of two readings (e.g. a run and its agy native subagents)."""
        total = Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.thinking_tokens + other.thinking_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
            _sum_cost(self.cost_usd, other.cost_usd),
            {name: dict(values) for name, values in self.models.items()},
            self.source or other.source,
        )
        for name, values in other.models.items():
            mine = total.models.setdefault(name, {})
            for key, value in values.items():
                if isinstance(value, int | float):
                    mine[key] = mine.get(key, 0) + value
        return total


def _sum_cost(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _n(data: object, key: str) -> int:
    """A token counter that tolerates missing keys, nulls and wrong types."""
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _f(data: object, key: str) -> float | None:
    value = data.get(key) if isinstance(data, dict) else None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


class TranscriptCursor:
    """Reads a JSONL file from where the previous read stopped. If the file shrinks (it was
    rewritten), it starts again from the beginning."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0
        self._rest = b""
        self.rows_seen = 0

    def read(self) -> bool:
        """Feeds the new complete lines to `on_row`. False if the file does not exist."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return False
        if size < self._offset:
            self._offset, self._rest = 0, b""
            self.reset()
        if size == self._offset:
            return True
        with self.path.open("rb") as file:
            file.seek(self._offset)
            chunk = file.read(size - self._offset)
        self._offset += len(chunk)
        lines = (self._rest + chunk).split(b"\n")
        self._rest = lines.pop()  # an unfinished line waits for the next read
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                self.rows_seen += 1
                self.on_row(row)
        return True

    def reset(self) -> None:
        self.rows_seen = 0

    def on_row(self, row: dict[str, Any]) -> None:
        raise NotImplementedError


class ClaudeCursor(TranscriptCursor):
    def reset(self) -> None:
        super().reset()
        self.cost_state: dict[str, Any] | None = None
        self.messages: dict[str, tuple[str, dict[str, Any]]] = {}

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.reset()

    def on_row(self, row: dict[str, Any]) -> None:
        kind = row.get("type")
        if kind == COST_STATE:
            self.cost_state = row
            return
        message = row.get("message")
        if kind != "assistant" or not isinstance(message, dict):
            return
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return
        key = message.get("id") or row.get("requestId") or row.get("uuid") or self.rows_seen
        # The rows of a message repeat its usage; the latest one wins.
        self.messages[str(key)] = (str(message.get("model") or "?"), usage)

    def from_cost_state(self) -> Usage | None:
        state = self.cost_state
        if state is None:
            return None
        usage = Usage(cost_usd=_f(state, "totalCostUSD"), source=COST_STATE)
        models = state.get("modelUsage")
        for name, values in (models if isinstance(models, dict) else {}).items():
            if not isinstance(values, dict):
                continue
            entry = {
                "input_tokens": _n(values, "inputTokens"),
                "output_tokens": _n(values, "outputTokens"),
                "thinking_tokens": _n(values, "thinkingTokens"),
                "cache_read_tokens": _n(values, "cacheReadInputTokens"),
                "cache_creation_tokens": _n(values, "cacheCreationInputTokens"),
            }
            if (cost := _f(values, "costUSD")) is not None:
                entry["cost_usd"] = cost
            usage.models[str(name)] = entry
            usage.input_tokens += entry["input_tokens"]
            usage.output_tokens += entry["output_tokens"]
            usage.thinking_tokens += entry["thinking_tokens"]
            usage.cache_read_tokens += entry["cache_read_tokens"]
            usage.cache_creation_tokens += entry["cache_creation_tokens"]
        return usage

    def from_rows(self) -> Usage | None:
        if not self.messages:
            return None
        usage = Usage(source=ASSISTANT_ROWS)
        for model, values in self.messages.values():
            details = values.get("output_tokens_details")
            entry = {
                "input_tokens": _n(values, "input_tokens"),
                "output_tokens": _n(values, "output_tokens"),
                "thinking_tokens": _n(details, "thinking_tokens"),
                "cache_read_tokens": _n(values, "cache_read_input_tokens"),
                "cache_creation_tokens": _n(values, "cache_creation_input_tokens"),
            }
            usage = usage.add(Usage(**entry, models={model: dict(entry)}))
        usage.source = ASSISTANT_ROWS
        return usage


class AgyCursor(TranscriptCursor):
    def reset(self) -> None:
        super().reset()
        self.steps: dict[str, dict[str, int]] = {}

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.reset()

    def on_row(self, row: dict[str, Any]) -> None:
        counters = {
            "input_tokens": _n(row, "input_tokens"),
            "output_tokens": _n(row, "output_tokens"),
            "thinking_tokens": _n(row, "thinking_tokens"),
            "cache_read_tokens": _n(row, "cache_read_tokens"),
        }
        if not any(counters.values()):
            return
        key = row.get("step_index")
        self.steps[str(key if key is not None else f"row{self.rows_seen}")] = counters

    def usage(self) -> Usage | None:
        if not self.steps:
            return None
        usage = Usage(source=TRANSCRIPT_FULL)
        for step in self.steps.values():
            usage.input_tokens += step["input_tokens"]
            usage.output_tokens += step["output_tokens"]
            usage.thinking_tokens += step["thinking_tokens"]
            usage.cache_read_tokens += step["cache_read_tokens"]
        return usage


def claude_subagent_files(transcript: Path) -> list[Path]:
    """Claude keeps each native subagent in `<session>/subagents/*.jsonl`."""
    folder = transcript.with_suffix("") / "subagents"
    try:
        return sorted(folder.glob("*.jsonl"))
    except OSError:
        return []


class ClaudeReader:
    """The usage of one Claude session: its transcript and its native subagents' files."""

    def __init__(self, transcript: Path) -> None:
        self.main = ClaudeCursor(transcript)
        self.subagents: dict[Path, ClaudeCursor] = {}

    def read(self) -> Usage | None:
        if not self.main.read():
            return None
        exact = self.main.from_cost_state()
        if exact is not None:
            return exact  # it already includes the native subagents
        for path in claude_subagent_files(self.main.path):
            self.subagents.setdefault(path, ClaudeCursor(path)).read()
        total: Usage | None = None
        for cursor in (self.main, *self.subagents.values()):
            part = cursor.from_rows()
            if part is not None:
                total = part if total is None else total.add(part)
        if total is not None:
            total.source = ASSISTANT_ROWS
        return total


class AgyReader:
    """The usage of one agy conversation."""

    def __init__(self, transcript: Path) -> None:
        self.cursor = AgyCursor(transcript)

    def read(self) -> Usage | None:
        if not self.cursor.read():
            return None
        return self.cursor.usage()


def claude_usage(transcript: Path) -> Usage | None:
    return ClaudeReader(transcript).read()


def agy_usage(transcript: Path) -> Usage | None:
    return AgyReader(transcript).read()
