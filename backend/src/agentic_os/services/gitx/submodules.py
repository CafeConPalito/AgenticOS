"""Submodules (phase 12, ADR 0017). Starting and updating them downloads, so those are jobs."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from agentic_os.services.gitx import remotes
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

State = Literal["ok", "not_initialized", "modified", "conflict"]


class SubmoduleInfo(BaseModel):
    path: str
    sha: str
    describe: str = ""
    state: State
    url: str = ""


LINE = re.compile(
    r"^(?P<mark>[ +\-U])(?P<sha>[0-9a-f]{7,64}) (?P<path>.+?)(?: \((?P<describe>.*)\))?$"
)
STATES: dict[str, State] = {" ": "ok", "-": "not_initialized", "+": "modified", "U": "conflict"}


def submodules(repo: Repo) -> list[SubmoduleInfo]:
    out = repo.attempt("submodule", "status") or ""
    urls = _urls(repo)
    found = []
    for line in out.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        path = match.group("path")
        found.append(
            SubmoduleInfo(
                path=path,
                sha=match.group("sha"),
                describe=match.group("describe") or "",
                state=STATES[match.group("mark")],
                url=urls.get(path, ""),
            )
        )
    return found


def _urls(repo: Repo) -> dict[str, str]:
    """`.gitmodules`: the address of each submodule, by path."""
    out = repo.attempt(
        "config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.(path|url)$"
    )
    if not out:
        return {}
    by_name: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        name, _, field = key.removeprefix("submodule.").rpartition(".")
        by_name.setdefault(name, {})[field] = value.strip()
    return {v["path"]: v.get("url", "") for v in by_name.values() if "path" in v}


def update_args(path: str | None = None) -> list[str]:
    """Starts (if needed) and updates submodules to the commit the repository records."""
    return [
        "submodule",
        "update",
        "--init",
        "--recursive",
        "--progress",
        *(["--", path] if path else []),
    ]


def add(repo: Repo, url: str, path: str) -> None:
    clean = path.strip().strip("/")
    if not clean or clean.startswith("-") or ".." in clean.split("/"):
        raise GitxError("invalid_path", "that folder is not valid", status=422)
    with repo.write():
        repo.run(
            "submodule",
            "add",
            "--",
            remotes._check_url(url),
            clean,
            timeout=300,
            interactive=True,
            config=("protocol.file.allow=always",),
        )


def remove(repo: Repo, path: str) -> None:
    """Takes a submodule out: deinitialized, deleted from the work tree and from `.gitmodules`
    (the change is staged; the commit is the person's)."""
    with repo.write():
        repo.run("submodule", "deinit", "-f", "--", path, literal=True)
        repo.run("rm", "-f", "--", path, literal=True)


def use_commit(repo: Repo, path: str, rev: str) -> None:
    """Points the submodule at another commit (checks it out inside, then stages the change)."""
    inner = Repo(str(repo_path(repo, path)))
    with repo.write():
        inner.run("checkout", "--detach", rev)
        repo.run("add", "--", path, literal=True)


def repo_path(repo: Repo, path: str):
    from pathlib import Path

    target = Path(repo.path) / path
    if not target.is_dir():
        raise GitxError("submodule_not_initialized", f"{path} is not initialized", status=409)
    return target
