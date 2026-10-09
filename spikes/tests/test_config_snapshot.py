import json
from pathlib import Path

import common


def test_snapshot_detects_mcp_change_but_ignores_run_state(tmp_path: Path, monkeypatch):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"numStartups": 1, "mcpServers": {}}), "utf-8")
    monkeypatch.setattr(common, "CLAUDE_CONFIG", [claude_json])
    monkeypatch.setattr(common, "GEMINI_DIR", tmp_path / "no-gemini")

    before = common.ConfigSnapshot.take()
    claude_json.write_text(json.dumps({"numStartups": 2, "mcpServers": {}}), "utf-8")
    assert before.diff(common.ConfigSnapshot.take()) == []

    claude_json.write_text(
        json.dumps({"numStartups": 3, "mcpServers": {"x": {"type": "http"}}}), "utf-8"
    )
    changes = before.diff(common.ConfigSnapshot.take())
    assert len(changes) == 1 and "mcpServers" in changes[0]


def test_snapshot_ignores_volatile_gemini_state(tmp_path: Path, monkeypatch):
    gemini = tmp_path / ".gemini"
    (gemini / "antigravity-cli" / "log").mkdir(parents=True)
    (gemini / "config").mkdir()
    monkeypatch.setattr(common, "CLAUDE_CONFIG", [])
    monkeypatch.setattr(common, "GEMINI_DIR", gemini)

    before = common.ConfigSnapshot.take()
    (gemini / "antigravity-cli" / "log" / "run.log").write_text("x", "utf-8")
    assert before.diff(common.ConfigSnapshot.take()) == []

    (gemini / "config" / "mcp.json").write_text("{}", "utf-8")
    assert before.diff(common.ConfigSnapshot.take()) == [f"added: {gemini / 'config' / 'mcp.json'}"]
