import pytest

from agentic_os.errors import ApiError
from agentic_os.models.agent import Cli
from agentic_os.services.runs import launcher


@pytest.fixture(autouse=True)
def fake_which(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: f"C:/bin/{name}.exe")


def test_claude_command_is_isolated_and_prompt_first():
    spec = launcher.build_launch(Cli.CLAUDE, "opus", "Arregla el login")
    argv = spec.argv
    assert argv[:2] == ["C:/bin/claude.exe", "Arregla el login"]
    assert argv[argv.index("--session-id") + 1] == spec.session_id
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert argv[argv.index("--model") + 1] == "opus"


def test_claude_without_model_uses_cli_default():
    assert "--model" not in launcher.build_launch(Cli.CLAUDE, "", "x").argv


def test_agy_command():
    spec = launcher.build_launch(Cli.AGY, "gemini-3.8-flash-low", "Revisa")
    assert spec.argv == ["C:/bin/agy.exe", "--model", "gemini-3.8-flash-low", "-i", "Revisa"]
    assert spec.session_id is None


def test_overrides_replace_the_executable():
    spec = launcher.build_launch(Cli.AGY, "", "x", {"agy": ["python", "fake.py"]})
    assert spec.argv == ["python", "fake.py", "-i", "x"]


def test_missing_cli(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    with pytest.raises(ApiError) as error:
        launcher.build_launch(Cli.CLAUDE, "", "x")
    assert error.value.code == "cli_not_installed"


def test_env_drops_session_markers_but_keeps_user_config():
    env = launcher.clean_env(
        {
            "PATH": "x",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_CHILD_SESSION": "1",
            "CLAUDE_CONFIG_DIR": "D:/claude",
            "CLAUDE_CODE_GIT_BASH_PATH": "C:/git/bash.exe",
        }
    )
    assert env == {
        "PATH": "x",
        "CLAUDE_CONFIG_DIR": "D:/claude",
        "CLAUDE_CODE_GIT_BASH_PATH": "C:/git/bash.exe",
    }


def test_batch_shims_are_refused(monkeypatch):
    # cmd.exe would re-parse the prompt: `&` or `%VAR%` could run other commands.
    monkeypatch.setattr(launcher.shutil, "which", lambda name: f"C:/npm/{name}.CMD")
    with pytest.raises(ApiError) as error:
        launcher.build_launch(Cli.CLAUDE, "", 'arregla el "x" & calc')
    assert error.value.code == "cli_shim_unsupported"


def test_prompt_starting_with_a_dash_is_not_an_option():
    claude = launcher.build_launch(Cli.CLAUDE, "", "--help me con el login").argv
    assert claude[1] == " --help me con el login"
    agy = launcher.build_launch(Cli.AGY, "", "-p resume").argv
    assert agy[-2:] == ["-i", " -p resume"]
