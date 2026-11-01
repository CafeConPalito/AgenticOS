import pytest

from agentic_os.errors import ApiError
from agentic_os.models.agent import Cli
from agentic_os.services.runs import launcher


@pytest.fixture(autouse=True)
def fake_which(monkeypatch):
    monkeypatch.setattr(launcher.cli_paths.shutil, "which", lambda name: f"C:/bin/{name}.exe")


def test_executable_and_overrides():
    assert launcher.resolve_executable(Cli.CLAUDE) == ["C:/bin/claude.exe"]
    overrides = {"agy": ["python", "fake.py"]}
    assert launcher.resolve_executable(Cli.AGY, overrides) == ["python", "fake.py"]


def test_missing_cli(monkeypatch):
    monkeypatch.setattr(launcher.cli_paths.shutil, "which", lambda name: None)
    with pytest.raises(ApiError) as error:
        launcher.resolve_executable(Cli.CLAUDE)
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
    monkeypatch.setattr(launcher.cli_paths.shutil, "which", lambda name: f"C:/npm/{name}.CMD")
    with pytest.raises(ApiError) as error:
        launcher.resolve_executable(Cli.CLAUDE)
    assert error.value.code == "cli_shim_unsupported"


def test_prompt_starting_with_a_dash_is_not_an_option():
    assert launcher.safe_prompt("--help me con el login") == " --help me con el login"
    assert launcher.safe_prompt("Arregla -p") == "Arregla -p"
