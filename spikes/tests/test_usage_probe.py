import json
from pathlib import Path

from usage_probe import (
    agy_transcript,
    agy_usage,
    claude_project_slug,
    claude_transcript,
    claude_usage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_claude_usage_reads_latest_cost_state():
    usage = claude_usage(FIXTURES / "claude_transcript.jsonl")
    assert usage.source == "claude:cost-state"
    assert usage.cost_usd == 0.00422583
    assert (usage.input_tokens, usage.output_tokens) == (8, 888)
    assert (usage.cache_read_tokens, usage.cache_creation_tokens) == (49163, 22027)
    assert usage.thinking_tokens == 284
    assert list(usage.models) == ["claude-haiku-5-5"]


def test_claude_usage_falls_back_to_assistant_rows(tmp_path: Path):
    rows = [
        r
        for r in map(json.loads, (FIXTURES / "claude_transcript.jsonl").read_text().splitlines())
        if r["type"] != "cost-state"
    ]
    # Duplicate the first assistant row: the same API message must be counted once.
    first = next(r for r in rows if r["type"] == "assistant")
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in [*rows, first]), "utf-8")
    usage = claude_usage(transcript)
    assert usage.source == "claude:assistant-rows"
    assert usage.cost_usd is None
    assert usage.output_tokens > 0
    # Claude writes one row per content block, all sharing the API message id.
    unique_messages = {r["message"]["id"] for r in rows if r["type"] == "assistant"}
    assert sum(m["messages"] for m in usage.models.values()) == len(unique_messages)


def test_claude_transcript_path_uses_cwd_slug(tmp_path: Path):
    cwd = r"C:\Users\me\AppData\Local\AgenticOS-spike\sandbox\run-1"
    assert claude_project_slug(cwd) == "C--Users-me-AppData-Local-AgenticOS-spike-sandbox-run-1"
    path = claude_transcript(cwd, "abc", home=tmp_path)
    assert path == tmp_path / ".claude" / "projects" / claude_project_slug(cwd) / "abc.jsonl"


def test_null_token_fields_count_as_zero(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    rows = [
        {
            "type": "cost-state",
            "totalCostUSD": 0.01,
            "modelUsage": {"m": {"inputTokens": 5, "outputTokens": None, "thinkingTokens": None}},
        }
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in rows), "utf-8")
    usage = claude_usage(transcript)
    assert (usage.input_tokens, usage.output_tokens, usage.thinking_tokens) == (5, 0, 0)

    agy = tmp_path / "agy.jsonl"
    agy.write_text(json.dumps({"input_tokens": 3, "output_tokens": None}), "utf-8")
    assert agy_usage(agy).input_tokens == 3


def test_agy_usage_sums_steps():
    usage = agy_usage(FIXTURES / "agy_transcript_full.jsonl")
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (11690, 19, 0)
    assert usage.cost_usd is None


def test_agy_transcript_path(tmp_path: Path):
    path = agy_transcript("conv-1", home=tmp_path)
    assert path.parts[-5:] == (
        "brain",
        "conv-1",
        ".system_generated",
        "logs",
        "transcript_full.jsonl",
    )
