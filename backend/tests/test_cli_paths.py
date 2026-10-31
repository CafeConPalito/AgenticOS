"""A CLI installed while the app runs is found without restarting it (phase 23, ADR 0029)."""

import os
import sys
from pathlib import Path

import pytest

from agentic_os.services import cli_paths

REAL_SEARCH_PATH = cli_paths.search_path  # taken before the autouse fixture swaps it

EXE = ".exe" if sys.platform == "win32" else ""


def fake_cli(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / f"{name}{EXE}"
    program.write_bytes(b"")
    program.chmod(0o755)
    return program


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    folders: list[str] = []
    monkeypatch.setattr(cli_paths, "search_path", REAL_SEARCH_PATH)
    monkeypatch.setattr(cli_paths, "registry_paths", lambda: folders)
    monkeypatch.setattr(cli_paths, "KNOWN_DIRS", (tmp_path / "conocida",))
    monkeypatch.setenv("PATH", str(tmp_path / "vacia"))
    if sys.platform == "win32":
        monkeypatch.setenv("PATHEXT", ".EXE")
    return folders


def test_finds_a_cli_in_the_users_path_of_the_registry_with_its_variables(
    registry: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    program = fake_cli(tmp_path / "instalado" / "bin", "agy")
    monkeypatch.setenv("MI_CARPETA", str(tmp_path / "instalado"))
    assert cli_paths.which("agy") is None
    registry.append("%MI_CARPETA%" + os.sep + "bin")  # what the installer wrote meanwhile
    assert Path(cli_paths.which("agy") or "").resolve() == program.resolve()


def test_finds_a_cli_in_the_folder_its_installer_uses(registry: list[str], tmp_path: Path):
    program = fake_cli(tmp_path / "conocida", "claude")
    assert Path(cli_paths.which("claude") or "").resolve() == program.resolve()


def test_the_process_path_comes_first(registry: list[str], tmp_path: Path, monkeypatch):
    first = fake_cli(tmp_path / "proceso", "claude")
    fake_cli(tmp_path / "conocida", "claude")
    monkeypatch.setenv("PATH", str(tmp_path / "proceso"))
    assert Path(cli_paths.which("claude") or "").resolve() == first.resolve()
