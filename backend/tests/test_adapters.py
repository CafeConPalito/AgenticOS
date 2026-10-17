"""CLI adapters: argv and files per permission mode, and the agy workspace plugin lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_os.models import Cli, PermissionMode
from agentic_os.services.adapters import LaunchContext, adapter_for
from agentic_os.services.adapters.agy import EXCLUDE_LINE, plugin_dir, remove_plugin
from agentic_os.services.runs import launcher


@pytest.fixture(autouse=True)
def fake_which(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: f"C:/bin/{name}.exe")


def context(
    tmp_path: Path,
    cli: Cli,
    mode: PermissionMode = PermissionMode.ASK,
    tools: tuple[str, ...] = (),
    model: str = "",
    prompt: str = "Arregla el login",
    run_id: str = "run-1",
    extra_dirs: tuple[str, ...] = (),
) -> LaunchContext:
    project = tmp_path / "proyecto"
    project.mkdir(exist_ok=True)
    return LaunchContext(
        run_id=run_id,
        cli=cli,
        model=model,
        prompt=prompt,
        permission_mode=mode,
        allowed_tools=tools,
        cwd=project,
        run_dir=tmp_path / "data" / "runs" / run_id,
        base_url="http://127.0.0.1:9999",
        token="tok-" + "x" * 30,
        instructions="# Tu rol: Dev\n",
        hook_command=r"C:\Users\usuario\AppData\Roaming\AGENTI~1\runs\run-1\hook.cmd",
        extra_dirs=extra_dirs,
    )


def option(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def allowed(argv: list[str]) -> list[str]:
    start = argv.index("--allowedTools") + 1
    end = next((i for i in range(start, len(argv)) if argv[i].startswith("--")), len(argv))
    return argv[start:end]


# ---------------------------------------------------------------- Claude Code
def test_claude_is_isolated_with_its_own_files_and_the_prompt_first(tmp_path: Path):
    ctx = context(tmp_path, Cli.CLAUDE, model="opus")
    spec = adapter_for(Cli.CLAUDE).prepare(ctx)
    argv = spec.argv
    assert argv[:2] == ["C:/bin/claude.exe", "Arregla el login"]
    assert option(argv, "--session-id") == spec.session_id
    assert option(argv, "--setting-sources") == "project,local"
    assert "--strict-mcp-config" in argv
    assert option(argv, "--model") == "opus"
    for flag, name in (
        ("--settings", "settings.json"),
        ("--mcp-config", "mcp.json"),
        ("--append-system-prompt-file", "instructions.md"),
    ):
        assert Path(option(argv, flag)) == ctx.run_dir / name  # never inside the project
    assert not any(ctx.cwd.iterdir())

    mcp = json.loads((ctx.run_dir / "mcp.json").read_text("utf-8"))["mcpServers"]["agentic-os"]
    assert mcp == {
        "type": "http",
        "url": "http://127.0.0.1:9999/r/mcp",
        "headers": {"Authorization": f"Bearer {ctx.token}"},
    }
    hooks = json.loads((ctx.run_dir / "settings.json").read_text("utf-8"))["hooks"]
    assert set(hooks) == {
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "SessionEnd",
        "SubagentStart",
        "SubagentStop",
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
    }
    # Tool hooks only for the native subagent tool (no curl on every tool call).
    assert hooks["PreToolUse"][0]["matcher"] == "Agent|Task"
    assert "matcher" not in hooks["Stop"][0]
    assert hooks["Stop"][0]["hooks"][0]["command"] == f'"{ctx.hook_command}" Stop'
    # Phase 07: the status line reports the session's cost through the same script.
    settings = json.loads((ctx.run_dir / "settings.json").read_text("utf-8"))
    assert settings["statusLine"] == {
        "type": "command",
        "command": f'"{ctx.hook_command}" StatusLine',
    }
    assert (ctx.run_dir / "instructions.md").read_text("utf-8") == "# Tu rol: Dev\n"


@pytest.mark.parametrize(
    ("mode", "permission", "tools"),
    [
        (PermissionMode.ASK, "manual", ["mcp__agentic-os__*"]),
        (
            PermissionMode.RESTRICTED,
            "acceptEdits",
            ["mcp__agentic-os__*", "Read", "Glob", "Grep", "Bash(git:*)", "PowerShell(git *)"],
        ),
        (PermissionMode.AUTONOMOUS, "bypassPermissions", ["mcp__agentic-os__*"]),
    ],
)
def test_claude_permission_modes(tmp_path: Path, mode, permission, tools):
    ctx = context(tmp_path, Cli.CLAUDE, mode=mode, tools=("read", "git", "browser"))
    argv = adapter_for(Cli.CLAUDE).prepare(ctx).argv
    assert option(argv, "--permission-mode") == permission
    assert allowed(argv) == tools


def test_claude_prompt_starting_with_a_dash(tmp_path: Path):
    ctx = context(tmp_path, Cli.CLAUDE, prompt="--help me con el login")
    assert adapter_for(Cli.CLAUDE).prepare(ctx).argv[1] == " --help me con el login"


def test_claude_runs_with_the_login_folder_of_its_account(tmp_path: Path, monkeypatch):
    """Phase 10: the account's folder wins over a CLAUDE_CONFIG_DIR of the person; the system
    account adds nothing, so the person's own configuration is kept."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "C:/mine")
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    base = context(tmp_path, Cli.CLAUDE)
    system = adapter_for(Cli.CLAUDE).prepare(base)
    assert system.env["CLAUDE_CONFIG_DIR"] == "C:/mine"
    assert "CLAUDE_CODE_CHILD_SESSION" not in system.env  # session markers are still removed

    from dataclasses import replace

    own = replace(base, account_env={"CLAUDE_CONFIG_DIR": "C:/data/accounts/a1"})
    assert adapter_for(Cli.CLAUDE).prepare(own).env["CLAUDE_CONFIG_DIR"] == "C:/data/accounts/a1"


# ---------------------------------------------------------------- agy
@pytest.mark.parametrize(
    ("mode", "flags"),
    [
        (PermissionMode.ASK, []),
        (PermissionMode.RESTRICTED, ["--mode", "accept-edits"]),
        (PermissionMode.AUTONOMOUS, ["--dangerously-skip-permissions"]),
    ],
)
def test_agy_starts_without_the_prompt(tmp_path: Path, mode, flags):
    ctx = context(tmp_path, Cli.AGY, mode=mode, model="gemini-3.8-flash-low")
    adapter = adapter_for(Cli.AGY)
    spec = adapter.prepare(ctx)
    assert spec.argv == ["C:/bin/agy.exe", "--model", "gemini-3.8-flash-low", *flags]
    assert "-i" not in spec.argv and spec.session_id is None
    assert adapter.deferred_prompt(ctx) == "Arregla el login"
    assert adapter_for(Cli.AGY).deferred_prompt(context(tmp_path, Cli.AGY, prompt="/x")) == " /x"


def test_agy_workspace_plugin(tmp_path: Path):
    ctx = context(tmp_path, Cli.AGY)
    adapter_for(Cli.AGY).prepare(ctx)
    plugin = plugin_dir(ctx.cwd)
    assert json.loads((plugin / "plugin.json").read_text("utf-8")) == {
        "name": "agentic-os",
        "agenticOsRun": "run-1",
    }
    mcp = json.loads((plugin / "mcp_config.json").read_text("utf-8"))
    assert mcp == {"mcpServers": {"agentic-os": {"url": ctx.mcp_url}}}
    assert ctx.token in ctx.mcp_url
    hooks = json.loads((plugin / "hooks.json").read_text("utf-8"))["agentic-os"]
    assert set(hooks) == {"PreInvocation", "Stop", "PreToolUse", "PostToolUse"}
    assert hooks["PreToolUse"][0]["matcher"] == "invoke_subagent"
    assert hooks["PreToolUse"][0]["hooks"][0]["type"] == "command"
    assert hooks["Stop"][0]["type"] == "command"
    command = hooks["Stop"][0]["command"]
    assert command == f"{ctx.hook_command} Stop" and '"' not in command  # cmd.exe, no quotes
    assert (plugin / "rules" / "AGENTS.md").read_text("utf-8") == "# Tu rol: Dev\n"

    adapter_for(Cli.AGY).cleanup(ctx)
    assert not (ctx.cwd / ".agents").exists()  # nothing of ours is left in the project


def test_agy_plugin_is_excluded_from_git_once(tmp_path: Path):
    ctx = context(tmp_path, Cli.AGY)
    (ctx.cwd / ".git" / "info").mkdir(parents=True)
    (ctx.cwd / ".git" / "info" / "exclude").write_text("# local\n*.log", "utf-8")
    adapter_for(Cli.AGY).prepare(ctx)
    adapter_for(Cli.AGY).prepare(context(tmp_path, Cli.AGY, run_id="run-2"))
    exclude = (ctx.cwd / ".git" / "info" / "exclude").read_text("utf-8")
    assert exclude == f"# local\n*.log\n{EXCLUDE_LINE}\n"


def test_cleanup_only_removes_our_own_plugin(tmp_path: Path):
    ctx = context(tmp_path, Cli.AGY)
    adapter_for(Cli.AGY).prepare(ctx)
    (ctx.cwd / ".agents" / "rules").mkdir()  # the user's own agy config stays
    assert not remove_plugin(ctx.cwd, "otra-ejecucion")
    assert plugin_dir(ctx.cwd).exists()
    adapter_for(Cli.AGY).recover(ctx.cwd, "run-1")
    assert not plugin_dir(ctx.cwd).exists()
    assert (ctx.cwd / ".agents" / "rules").is_dir()


# ------------------------------------------------------------ linked repositories (phase 12)
@pytest.mark.parametrize("cli", [Cli.CLAUDE, Cli.AGY])
def test_linked_repositories_are_handed_to_the_cli_one_flag_each(tmp_path: Path, cli: Cli):
    dirs = (str(tmp_path / "shared lib"), str(tmp_path / "other"))
    argv = adapter_for(cli).prepare(context(tmp_path, cli, extra_dirs=dirs)).argv
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"] == list(dirs)
    plain = adapter_for(cli).prepare(context(tmp_path, cli, run_id="run-2")).argv
    assert "--add-dir" not in plain
