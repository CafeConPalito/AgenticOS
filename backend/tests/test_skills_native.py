"""The CLIs' own skill mechanism (phase 17, block 4; spikes S1, S2): Claude gets the run's skills as
a plugin (`--plugin-dir`), agy inside its workspace plugin; their hooks say which one was loaded,
and nothing of the person's configuration changes (CA8)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_adapters import allowed, context, fake_which  # noqa: F401 - the fixture is autouse

from agentic_os.models import Cli, EventKind, PermissionMode, Run, RunEvent, RunSkill
from agentic_os.services.adapters import adapter_for
from agentic_os.services.adapters.agy import plugin_dir
from agentic_os.services.skills.runtime import native_name


def _skills(tmp_path: Path, run_id: str = "run-1", **sizes: int) -> Path:
    """The run's skills folder, as prepare_run leaves it: one folder per skill."""
    folder = tmp_path / "data" / "runs" / run_id / "plugin" / "skills"
    for name, size in (sizes or {"revision": 100}).items():
        skill = folder / name
        (skill / "scripts").mkdir(parents=True)
        body = "x" * size
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n{body}", "utf-8")
        (skill / "scripts" / "run.py").write_text("print(1)", "utf-8")
    return folder


def _with_skills(ctx, folder: Path | None):
    return dataclasses.replace(ctx, skills_dir=folder)


# ------------------------------------------------------------------ hooks → skill
@pytest.mark.parametrize(
    ("cli", "payload", "expected"),
    [
        ("claude", {"tool_name": "Skill", "tool_input": {"skill": "aos:revision"}}, "revision"),
        ("claude", {"tool_name": "Skill", "tool_input": {"skill": "code-review"}}, None),
        ("claude", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, None),
        (
            "agy",
            {
                "toolCall": {
                    "name": "read_file",
                    "args": {"Path": r"C:\p\.agents\plugins\agentic-os\skills\revision\SKILL.md"},
                }
            },
            "revision",
        ),
        ("agy", {"toolCall": {"name": "read_file", "args": {"Path": "C:/p/README.md"}}}, None),
        (
            "agy",
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "SKILL.md"}}},
            None,
        ),
    ],
)
def test_the_hooks_tell_which_skill_the_cli_loaded(cli, payload, expected):
    assert native_name(cli, "PreToolUse", payload) == expected
    assert native_name(cli, "PostToolUse", payload) is None


# ------------------------------------------------------------------------- Claude
def test_claude_gets_the_skills_as_a_plugin_and_may_load_them(tmp_path: Path):
    folder = _skills(tmp_path)
    ctx = _with_skills(context(tmp_path, Cli.CLAUDE, PermissionMode.ASK), folder)
    argv = adapter_for(Cli.CLAUDE).prepare(ctx).argv
    plugin = folder.parent
    assert argv[argv.index("--plugin-dir") + 1] == str(plugin)
    assert json.loads((plugin / ".claude-plugin" / "plugin.json").read_text("utf-8")) == {
        "name": "aos"
    }
    assert "Skill" in allowed(argv)
    settings = json.loads((ctx.run_dir / "settings.json").read_text("utf-8"))
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Agent|Task|Skill|mcp__.*"


def test_claude_without_skills_has_no_plugin(tmp_path: Path):
    ctx = _with_skills(context(tmp_path, Cli.CLAUDE), tmp_path / "no-hay")
    argv = adapter_for(Cli.CLAUDE).prepare(ctx).argv
    assert "--plugin-dir" not in argv
    assert "Skill" not in allowed(argv)


# ---------------------------------------------------------------------------- agy
def test_agy_gets_the_skills_in_its_plugin_except_the_too_big(tmp_path: Path):
    folder = _skills(tmp_path, revision=100, enorme=30_000)
    ctx = _with_skills(context(tmp_path, Cli.AGY), folder)
    adapter = adapter_for(Cli.AGY)
    adapter.prepare(ctx)
    plugin = plugin_dir(ctx.cwd)
    assert (plugin / "skills" / "revision" / "scripts" / "run.py").exists()
    assert not (plugin / "skills" / "enorme").exists()  # agy skips a SKILL.md over 24 KB (S2)
    hooks = json.loads((plugin / "hooks.json").read_text("utf-8"))["agentic-os"]
    assert hooks["PreToolUse"][0]["matcher"] == "invoke_subagent|call_mcp_tool|read_file"
    adapter.cleanup(ctx)
    assert not plugin.exists()


def test_agy_without_skills_does_not_watch_every_read(tmp_path: Path):
    ctx = _with_skills(context(tmp_path, Cli.AGY), None)
    adapter_for(Cli.AGY).prepare(ctx)
    hooks = json.loads((plugin_dir(ctx.cwd) / "hooks.json").read_text("utf-8"))["agentic-os"]
    assert hooks["PreToolUse"][0]["matcher"] == "invoke_subagent|call_mcp_tool"
    assert not (plugin_dir(ctx.cwd) / "skills").exists()


# ------------------------------------------------------------ the person's config
def _tree(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(folder).as_posix().encode() + path.read_bytes())
    return digest.hexdigest()


def test_preparing_and_cleaning_never_touch_the_persons_cli_folders(tmp_path: Path, monkeypatch):
    """CA8 (automatic part): ~/.claude and agy's folder are the same before and after a run with
    skills, for both CLIs. The manual part runs the real CLIs (validation)."""
    home = tmp_path / "home"
    for path, text in {
        ".claude/settings.json": "{}",
        ".claude/skills/mia/SKILL.md": "---\nname: mia\ndescription: d\n---\n",
        ".claude.json": "{}",
        ".gemini/config/skills/global/SKILL.md": "---\nname: global\ndescription: d\n---\n",
        ".gemini/antigravity-cli/settings.json": "{}",
    }.items():
        (home / path).parent.mkdir(parents=True, exist_ok=True)
        (home / path).write_text(text, "utf-8")
    monkeypatch.setattr(Path, "home", lambda: home)
    before = _tree(home)
    for cli in (Cli.CLAUDE, Cli.AGY):
        run_id = f"run-{cli.value}"
        ctx = _with_skills(context(tmp_path, cli, run_id=run_id), _skills(tmp_path, run_id))
        adapter = adapter_for(cli)
        adapter.prepare(ctx)
        adapter.cleanup(ctx)
    assert _tree(home) == before


# ------------------------------------------------------- the manager records it
def test_a_native_load_is_recorded_on_the_run(client: TestClient):
    manager = client.app.state.run_manager
    skill = client.post(
        "/api/skills", json={"scope": "general", "name": "revision", "description": "d"}
    ).json()
    with client.app.state.sessionmaker() as db:
        run = Run(
            agent_name="Dev",
            agent_color="#fff",
            project_name="",
            cli="claude",
            prompt="p",
            cwd=".",
        )
        db.add(run)
        db.flush()
        db.add(
            RunSkill(
                run_id=run.id, skill_id=skill["id"], skill_name="revision", offered="candidate"
            )
        )
        db.commit()
        run_id = run.id
    payload = {"tool_name": "Skill", "tool_input": {"skill": "aos:revision"}}
    manager.on_hook(run_id, "PreToolUse", payload)
    manager.on_hook(run_id, "PreToolUse", {"tool_name": "Skill", "tool_input": {"skill": "aos:x"}})
    with client.app.state.sessionmaker() as db:
        row = db.scalar(select(RunSkill).where(RunSkill.run_id == run_id))
        assert row.loaded_via == "native" and row.loaded_at is not None
        names = [
            (e.kind, e.name, e.detail)
            for e in db.scalars(select(RunEvent).where(RunEvent.run_id == run_id))
        ]
    assert names == [(EventKind.SYSTEM, "skill_native", "revision")]
