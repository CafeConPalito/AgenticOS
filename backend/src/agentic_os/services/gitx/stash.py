"""Stash: setting changes aside and bringing them back (phase 12, ADR 0017)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from agentic_os.services.gitx import merge, read
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

SEP = "\x1f"
END = "\x1e"


class StashEntry(BaseModel):
    index: int
    ref: str  # stash@{0}
    sha: str
    message: str
    date: datetime
    # `--include-untracked` keeps the new files in a commit of their own: `<sha>^3`.
    has_untracked: bool = False


def entries(repo: Repo) -> list[StashEntry]:
    out = repo.run("stash", "list", f"--format=%gd{SEP}%H{SEP}%at{SEP}%gs{SEP}%P{END}")
    found = []
    for position, record in enumerate(r for r in out.split(END) if r.strip()):
        ref, sha, at, message, parents = record.strip("\n").split(SEP)
        found.append(
            StashEntry(
                index=position,
                ref=ref,
                sha=sha,
                message=message,
                date=datetime.fromtimestamp(int(at), UTC),
                has_untracked=len(parents.split()) >= 3,
            )
        )
    return found


def push(repo: Repo, message: str | None = None, include_untracked: bool = True) -> bool:
    """Sets the uncommitted changes aside. False when there was nothing to set aside."""
    args = ["stash", "push"]
    if include_untracked:
        args.append("--include-untracked")
    if message:
        args += ["-m", message]
    with repo.write():
        out = repo.run(*args)
    return "No local changes" not in out


def resolve(repo: Repo, ref: str) -> StashEntry:
    for entry in entries(repo):
        if ref in (entry.ref, entry.sha, str(entry.index)):
            return entry
    raise GitxError("unknown_ref", f"there is no stash {ref!r}", status=404)


def parent_of(repo: Repo, entry: StashEntry) -> str:
    """What a stash is compared with to see its changes: the commit it was made on."""
    return read.parent_or_empty(read.commit_detail(repo, entry.sha))


def apply(repo: Repo, ref: str, drop: bool = False) -> merge.OpResult:
    """Brings a stash back onto the work tree (`drop`: and forgets it, like `stash pop`). A
    stash that does not fit leaves conflicts to resolve, and is kept either way."""
    entry = resolve(repo, ref)
    with repo.write():
        try:
            repo.run("stash", "apply", entry.ref)
        except GitxError as error:
            unmerged = read.status(repo).conflicts
            if error.code == "conflicts" or unmerged:
                return merge.OpResult(
                    status="conflicts", conflicts=[f.path for f in unmerged], message=error.message
                )
            raise
        if drop:
            repo.run("stash", "drop", entry.ref)
    return merge.OpResult(status="done")


def drop(repo: Repo, ref: str) -> None:
    entry = resolve(repo, ref)
    with repo.write():
        repo.run("stash", "drop", entry.ref)


def to_branch(repo: Repo, ref: str, name: str) -> None:
    """A new branch from the commit the stash was made on, with the stash applied (and dropped)."""
    entry = resolve(repo, ref)
    with repo.write():
        repo.run("stash", "branch", name, entry.ref)
