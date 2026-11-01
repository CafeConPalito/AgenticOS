"""«Reanudar sesión» (phase 08): the adapters' argv, the usage of a resumed session and the
screen of a CLI that lost the conversation. End to end: test_resume_e2e.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_adapters import context, option

from agentic_os.models import Cli
from agentic_os.services.adapters import adapter_for
from agentic_os.services.runs import launcher
from agentic_os.services.runs.screen import ScreenState
from agentic_os.services.usage.parsers import (
    AgyReader,
    ClaudeReader,
    agy_baseline,
    claude_baseline,
)


@pytest.fixture(autouse=True)
def fake_which(monkeypatch):
    monkeypatch.setattr(launcher.cli_paths.shutil, "which", lambda name: f"C:/bin/{name}.exe")


# ---------------------------------------------------------------- adapters
def test_claude_resumes_its_session_with_the_new_configuration(tmp_path: Path):
    ctx = context(tmp_path, Cli.CLAUDE)
    ctx = ctx.__class__(**{**ctx.__dict__, "resume_session": "abc-123"})
    spec = adapter_for(Cli.CLAUDE).prepare(ctx)
    assert option(spec.argv, "--resume") == "abc-123"
    assert "--session-id" not in spec.argv
    assert spec.session_id == "abc-123"
    # The new run's hooks and MCP server (evidence R1: not stored in the session).
    assert option(spec.argv, "--mcp-config") == str(ctx.run_dir / "mcp.json")
    assert option(spec.argv, "--settings") == str(ctx.run_dir / "settings.json")


def test_agy_resumes_its_conversation_with_a_new_plugin(tmp_path: Path):
    ctx = context(tmp_path, Cli.AGY)
    ctx = ctx.__class__(**{**ctx.__dict__, "resume_session": "conv-9"})
    spec = adapter_for(Cli.AGY).prepare(ctx)
    assert option(spec.argv, "--conversation") == "conv-9"
    assert spec.session_id == "conv-9"
    plugin = ctx.cwd / ".agents" / "plugins" / "agentic-os"
    assert ctx.token in (plugin / "mcp_config.json").read_text("utf-8")


def test_a_new_session_is_not_a_resume(tmp_path: Path):
    spec = adapter_for(Cli.CLAUDE).prepare(context(tmp_path, Cli.CLAUDE))
    assert "--resume" not in spec.argv and "--session-id" in spec.argv
    spec = adapter_for(Cli.AGY).prepare(context(tmp_path, Cli.AGY, run_id="run-2"))
    assert "--conversation" not in spec.argv


# ---------------------------------------------------------------- usage of a resumed session
def write(path: Path, *rows: dict) -> None:
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def assistant(tokens: int) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": f"msg-{tokens}",
            "model": "m",
            "usage": {"input_tokens": tokens, "output_tokens": 1},
        },
    }


def cost_state(cost: float, tokens: int) -> dict:
    return {
        "type": "cost-state",
        "totalCostUSD": cost,
        "modelUsage": {"m": {"inputTokens": tokens, "outputTokens": 10, "costUSD": cost}},
    }


def test_claude_after_a_clean_close_subtracts_the_carried_totals(tmp_path: Path):
    transcript = tmp_path / "s.jsonl"
    write(transcript, assistant(100), cost_state(0.5, 100))
    baseline = claude_baseline(transcript)
    assert baseline["offset"] == transcript.stat().st_size
    assert baseline["cost_state"]["totalCostUSD"] == 0.5

    reader = ClaudeReader(transcript, baseline)
    write(transcript, assistant(40))
    live = reader.read()
    assert (live.source, live.input_tokens, live.cost_usd) == ("assistant-rows", 40, None)
    # Claude carries the session's totals over: the new cost-state is cumulative.
    write(transcript, cost_state(0.7, 140))
    final = reader.read()
    assert final.source == "cost-state"
    assert final.input_tokens == 40 and final.output_tokens == 0
    assert final.cost_usd == pytest.approx(0.2)
    assert final.models["m"]["cost_usd"] == pytest.approx(0.2)


def test_claude_after_a_crash_starts_from_zero(tmp_path: Path):
    transcript = tmp_path / "s.jsonl"
    write(transcript, assistant(100))  # killed: no cost-state
    baseline = claude_baseline(transcript)
    assert baseline["cost_state"] is None
    write(transcript, assistant(30), cost_state(0.1, 30))
    final = ClaudeReader(transcript, baseline).read()
    assert (final.input_tokens, final.cost_usd) == (30, 0.1)


def test_agy_reads_only_the_new_steps(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    write(transcript, {"step_index": 1, "input_tokens": 500, "output_tokens": 5})
    baseline = agy_baseline(transcript)
    write(transcript, {"step_index": 2, "input_tokens": 70, "output_tokens": 7})
    usage = AgyReader(transcript, baseline).read()
    assert (usage.input_tokens, usage.output_tokens) == (70, 7)


def test_without_a_baseline_everything_counts(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    write(transcript, {"step_index": 1, "input_tokens": 500})
    assert AgyReader(transcript).read().input_tokens == 500


# ---------------------------------------------------------------- screen
def test_claude_says_it_has_no_such_conversation():
    screen = ScreenState(Cli.CLAUDE, 120, 30)
    assert not screen.session_missing()
    screen.feed("No conversation found with session ID: 00000000-0000-4000-8000-000000000000\r\n")
    assert screen.session_missing()


def test_the_message_quoted_by_the_agent_is_not_a_lost_session():
    screen = ScreenState(Cli.CLAUDE, 120, 30)
    screen.feed("grep: screen.py: No conversation found with session ID\r\n")
    screen.feed("".join(f"línea {n}\r\n" for n in range(10)))
    assert not screen.session_missing()


def test_the_real_screen_of_claude(tmp_path: Path):
    log = (
        Path(__file__).parents[2] / "docs/phases/08-empaquetado/evidencias/r1-claude-bogus.raw.log"
    )
    screen = ScreenState(Cli.CLAUDE, 120, 30)
    screen.feed(log.read_text("utf-8", errors="replace"))
    assert screen.session_missing()
