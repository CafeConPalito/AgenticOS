"""Cloning and starting repositories (phase 12, ADR 0017)."""

from __future__ import annotations

import re
from pathlib import Path

from agentic_os.services import paths
from agentic_os.services.gitx import remotes
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

NAME = re.compile(r"[^/\\:]+?(?:\.git)?/?$")


def folder_name(url: str) -> str:
    """The folder a clone of `url` gets by default (`https://x/y/app.git` → `app`)."""
    match = NAME.search(url.strip().rstrip("/"))
    name = (match.group(0) if match else "").removesuffix("/").removesuffix(".git")
    return name or "repo"


def target(parent: str, name: str) -> Path:
    """The folder to clone into: `name` inside `parent`, which must not exist yet."""
    resolved, _ = paths.normalize(parent)
    folder = Path(resolved)
    if not folder.is_dir():
        raise GitxError("folder_not_found", "the folder to clone into does not exist", status=422)
    clean = name.strip()
    if (
        not clean
        or clean in (".", "..")
        or any(c in clean for c in '/\\:*?"<>|')
        or clean.startswith("-")
    ):
        raise GitxError("invalid_path", "that folder name is not valid", status=422)
    destination = folder / clean
    if destination.exists():
        raise GitxError("folder_exists", f"{clean} already exists", status=409)
    return destination


def clone_args(url: str, destination: Path) -> list[str]:
    """`git clone`; the job runs it from the parent folder (the repository does not exist yet)."""
    return ["clone", "--progress", "--", remotes._check_url(url), destination.name]


def init(path: str, branch: str = "main") -> None:
    """Makes a folder a repository (the folder is created if it does not exist)."""
    resolved, _ = paths.normalize(path)
    folder = Path(resolved)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / ".git").exists():
        raise GitxError("repo_exists", "that folder is already a repository", status=409)
    clean = branch.strip() or "main"
    if clean.startswith("-"):
        raise GitxError("invalid_ref", "that branch name is not valid", status=422)
    Repo(str(folder)).run("init", "-q", "-b", clean)
