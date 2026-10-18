"""The worktrees of a repository, the app's own among them (phase 12, ADR 0017)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo


class WorktreeInfo(BaseModel):
    path: str
    head: str | None = None
    branch: str | None = None
    main: bool = False  # the repository's own folder
    locked: bool = False
    prunable: bool = False  # its folder is gone
    task: bool = False  # made by Agentic OS for a task (`<project>.wt\\T-n`)


def worktrees(repo: Repo) -> list[WorktreeInfo]:
    out = repo.run("worktree", "list", "--porcelain")
    found: list[WorktreeInfo] = []
    for block in out.split("\n\n"):
        info: dict[str, str] = {}
        for line in block.strip().splitlines():
            key, _, value = line.partition(" ")
            info[key] = value
        if "worktree" not in info:
            continue
        path = info["worktree"]
        found.append(
            WorktreeInfo(
                path=path,
                head=info.get("HEAD"),
                branch=info["branch"].removeprefix("refs/heads/") if "branch" in info else None,
                main=not found,
                locked="locked" in info,
                prunable="prunable" in info,
                task=".wt" in Path(path).parent.name or Path(path).parent.name.endswith(".wt"),
            )
        )
    return found


def remove(repo: Repo, path: str, force: bool = False) -> None:
    """Deletes a worktree's folder and forgets it. The main folder cannot be removed, and
    neither can one the app is using for a task (it releases those itself)."""
    known = {w.path.replace("\\", "/"): w for w in worktrees(repo)}
    target = known.get(path.replace("\\", "/"))
    if target is None:
        raise GitxError("unknown_ref", "that is not a worktree of this repository", status=404)
    if target.main:
        raise GitxError("bad_worktree", "the repository's own folder cannot be removed", status=422)
    with repo.write():
        repo.run("worktree", "remove", *(["--force"] if force else []), "--", target.path)


def prune(repo: Repo) -> None:
    with repo.write():
        repo.run("worktree", "prune")
