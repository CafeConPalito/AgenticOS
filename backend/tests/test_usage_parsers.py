"""Usage parsers with real transcripts (Claude Code 2.1.296, agy 1.3.3; evidence C0)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentic_os.services.usage.parsers import (
    ASSISTANT_ROWS,
    COST_STATE,
    TRANSCRIPT_FULL,
    AgyReader,
    ClaudeReader,
    agy_usage,
    claude_usage,
)
from agentic_os.services.usage.paths import (
    agy_transcript,
    claude_config_dir,
    claude_project_slug,
    claude_transcript,
)

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"


def test_claude_cost_state_is_exact_and_includes_subagents() -> None:
    usage = claude_usage(FIXTURES / "claude-2.1.296-subagent" / "session.jsonl")
    assert usage is not None
    assert usage.source == COST_STATE
    assert usage.cost_usd == pytest.approx(0.009872485)
    assert (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_creation_tokens,
        usage.thinking_tokens,
    ) == (1754, 1564, 261471, 42426, 480)
    assert usage.models["claude-haiku-5-5"]["cost_usd"] == pytest.approx(0.009872485)


def test_claude_rows_fallback_deduplicates_messages_and_adds_subagents(tmp_path: Path) -> None:
    # The same session before it closed: no cost-state row yet.
    src = FIXTURES / "claude-2.1.296-subagent"
    shutil.copytree(src, tmp_path / "s")
    session = tmp_path / "s" / "session.jsonl"
    rows = [r for r in session.read_text("utf-8").splitlines() if '"cost-state"' not in r]
    session.write_text("\n".join(rows) + "\n", "utf-8")
    usage = claude_usage(session)
    assert usage is not None
    assert usage.source == ASSISTANT_ROWS
    assert usage.cost_usd is None
    assert (
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_creation_tokens,
        usage.thinking_tokens,
    ) == (16, 1491, 220326, 42383, 429)


def test_claude_session_killed_without_cost_state() -> None:
    usage = claude_usage(FIXTURES / "claude-2.1.296-no-cost-state.jsonl")
    assert usage is not None and usage.source == ASSISTANT_ROWS
    assert (usage.output_tokens, usage.cache_read_tokens, usage.thinking_tokens) == (
        328,
        67542,
        227,
    )


def test_claude_last_cost_state_wins() -> None:
    usage = claude_usage(FIXTURES / "claude-2.1.296-two-turns.jsonl")
    assert usage is not None and usage.source == COST_STATE
    assert usage.cost_usd == pytest.approx(0.00506875)
    assert usage.input_tokens == 1678


def test_agy_sums_steps_without_cost() -> None:
    usage = agy_usage(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
    assert usage is not None
    assert usage.source == TRANSCRIPT_FULL
    assert (usage.input_tokens, usage.output_tokens, usage.cost_usd) == (90094, 1979, None)
    child = agy_usage(FIXTURES / "agy-1.3.3-subagent-child.jsonl")
    assert child is not None
    total = usage.add(child)
    assert (total.input_tokens, total.output_tokens, total.cost_usd) == (123455, 4142, None)


def test_missing_empty_and_broken_transcripts(tmp_path: Path) -> None:
    assert claude_usage(tmp_path / "nope.jsonl") is None
    assert agy_usage(tmp_path / "nope.jsonl") is None
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", "utf-8")
    assert claude_usage(empty) is None
    broken = tmp_path / "broken.jsonl"
    broken.write_text(
        '{"type": "assistant", "message": {"id": "m1", "usage": {"output_tokens": 5}}}\n'
        "not json at all\n"
        '["a list"]\n'
        '{"type": "assistant", "message": {"id": "m2", "usage": {"output_tokens": "x",'
        ' "input_tokens": null, "brand_new_field": 3}}}\n'
        '{"type": "something-new", "totalCostUSD": 99}\n',
        "utf-8",
    )
    usage = claude_usage(broken)
    assert usage is not None and (usage.output_tokens, usage.input_tokens) == (5, 0)
    # A row with no counters is not usage.
    agy = tmp_path / "agy.jsonl"
    agy.write_text('{"step_index": 0, "type": "USER_INPUT"}\n', "utf-8")
    assert agy_usage(agy) is None


def test_incremental_reading(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    reader = AgyReader(path)
    assert reader.read() is None  # does not exist yet
    path.write_text('{"step_index": 1, "input_tokens": 10, "output_tokens": 1}\n', "utf-8")
    first = reader.read()
    assert first is not None and first.input_tokens == 10
    with path.open("a", encoding="utf-8") as file:
        # A line still being written is not read until it is complete.
        file.write('{"step_index": 2, "input_tokens": 20, "output_tokens": 2}\n{"step_ind')
    second = reader.read()
    assert second is not None and second.input_tokens == 30
    with path.open("a", encoding="utf-8") as file:
        file.write('ex": 3, "input_tokens": 5}\n')
    third = reader.read()
    assert third is not None and third.input_tokens == 35
    # Rewritten (shrunk): read again from the start.
    path.write_text('{"step_index": 1, "input_tokens": 7}\n', "utf-8")
    fourth = reader.read()
    assert fourth is not None and fourth.input_tokens == 7


def test_claude_reader_switches_to_cost_state_when_the_session_closes(tmp_path: Path) -> None:
    source = (FIXTURES / "claude-2.1.296-two-turns.jsonl").read_text("utf-8").splitlines()
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(r for r in source if '"cost-state"' not in r) + "\n", "utf-8")
    reader = ClaudeReader(path)
    live = reader.read()
    assert live is not None and live.source == ASSISTANT_ROWS
    with path.open("a", encoding="utf-8") as file:
        file.write(next(r for r in source if '"cost-state"' in r) + "\n")
    final = reader.read()
    assert final is not None and final.source == COST_STATE
    assert final.cost_usd == pytest.approx(0.00506875)


def test_paths() -> None:
    cwd = r"C:\Users\x\AppData\Local\Temp\proj_1"
    assert claude_project_slug(cwd) == "C--Users-x-AppData-Local-Temp-proj-1"
    config = claude_config_dir({"CLAUDE_CONFIG_DIR": r"D:\claude-config"})
    assert config == Path(r"D:\claude-config")
    assert claude_transcript(cwd, "abc", config) == (
        config / "projects" / "C--Users-x-AppData-Local-Temp-proj-1" / "abc.jsonl"
    )
    home = Path(r"C:\Users\x")
    assert agy_transcript("conv", home) == (
        home / ".gemini/antigravity-cli/brain/conv/.system_generated/logs/transcript_full.jsonl"
    )


def test_statusline_fixture_has_the_live_cost() -> None:
    data = json.loads((FIXTURES / "claude-2.1.296-statusline.json").read_text("utf-8"))
    assert data["cost"]["total_cost_usd"] == pytest.approx(0.0042495)
