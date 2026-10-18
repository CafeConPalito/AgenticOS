"""Git LFS: which files it tracks and the commands that fetch them (phase 12, ADR 0017)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo


class LfsState(BaseModel):
    installed: bool  # git-lfs is on this machine
    used: bool  # the repository tracks some pattern with it
    patterns: list[str]
    files: int = 0  # files stored with LFS in this checkout


def installed(repo: Repo) -> bool:
    return repo.attempt("lfs", "version") is not None


def patterns(repo: Repo) -> list[str]:
    """The patterns `.gitattributes` sends to LFS (`filter=lfs`)."""
    attributes = Path(repo.path) / ".gitattributes"
    if not attributes.is_file():
        return []
    found = []
    for line in attributes.read_text("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) > 1 and "filter=lfs" in parts[1:]:
            found.append(parts[0])
    return found


def state(repo: Repo) -> LfsState:
    tracked = patterns(repo)
    has = installed(repo)
    files = 0
    if has and tracked:
        files = len((repo.attempt("lfs", "ls-files", "--name-only") or "").splitlines())
    return LfsState(installed=has, used=bool(tracked), patterns=tracked, files=files)


def _need(repo: Repo) -> None:
    if not installed(repo):
        raise GitxError("lfs_missing", "Git LFS is not installed", status=409)


def track(repo: Repo, pattern: str) -> None:
    clean = pattern.strip()
    if not clean or clean.startswith("-") or "\n" in clean:
        raise GitxError("invalid_pattern", "that pattern is not valid", status=422)
    _need(repo)
    with repo.write():
        repo.run("lfs", "track", "--", clean)


def untrack(repo: Repo, pattern: str) -> None:
    _need(repo)
    with repo.write():
        repo.run("lfs", "untrack", "--", pattern.strip())


def pull_args() -> list[str]:
    return ["lfs", "pull"]
