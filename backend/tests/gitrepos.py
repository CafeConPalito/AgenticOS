"""Real temporary git repositories for the phase 12 tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

IDENTITY = (
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
)


def sh(cwd: Path, *args: str, check: bool = True) -> str:
    """Runs git in `cwd`; returns its stdout, stripped."""
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "protocol.file.allow=always", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def make_repo(folder: Path, branch: str = "main", files: dict[str, str] | None = None) -> Path:
    """A repository with one commit (`README.md` and `files`) and an identity configured."""
    folder.mkdir(parents=True, exist_ok=True)
    sh(folder, "init", "-q", "-b", branch)
    sh(folder, "config", "user.name", "Test")
    sh(folder, "config", "user.email", "test@example.com")
    sh(folder, "config", "commit.gpgsign", "false")
    sh(folder, "config", "core.autocrlf", "false")  # the same on every machine
    write(folder, "README.md", "hola\n")
    for name, text in (files or {}).items():
        write(folder, name, text)
    sh(folder, "add", "-A")
    sh(folder, "commit", "-q", "-m", "init")
    return folder


def write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8", newline="\n")
    return path


def commit_file(folder: Path, name: str, text: str, message: str | None = None) -> str:
    write(folder, name, text)
    sh(folder, "add", "-A")
    sh(folder, "commit", "-q", "-m", message or f"edit {name}")
    return sh(folder, "rev-parse", "HEAD")


def make_bare(folder: Path, branch: str = "main") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    sh(folder, "init", "-q", "--bare", "-b", branch)
    return folder
