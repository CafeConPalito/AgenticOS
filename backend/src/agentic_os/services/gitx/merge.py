"""Bringing work together: merge, rebase (plain and interactive), cherry-pick, revert, reset and
the conflicts they leave (phase 12, ADR 0017).

A conflict is not an error: the operation stops half done, git remembers it, and the person
resolves the files and continues, or aborts. Every function returns an `OpResult` saying which.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentic_os.services.gitx import read
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

Status = Literal["done", "conflicts", "up_to_date", "squashed", "stopped"]
Mode = Literal["no_ff", "ff", "squash"]
ResetMode = Literal["soft", "mixed", "hard"]
Side = Literal["ours", "theirs"]
TodoAction = Literal["pick", "reword", "squash", "fixup", "edit", "drop"]


class OpResult(BaseModel):
    status: Status
    # Files git could not merge by itself (status «conflicts»).
    conflicts: list[str] = Field(default_factory=list)
    # What git said, for the details.
    message: str = ""


def _result(repo: Repo, status: Status, output: str = "") -> OpResult:
    return OpResult(
        status=status, message=output.strip().splitlines()[-1] if output.strip() else ""
    )


def _stopped(repo: Repo, error: GitxError) -> OpResult | None:
    """The result for a command that failed because it hit conflicts or paused for an `edit`.
    None: it really failed."""
    operation = read.operation_in_progress(repo)
    if operation is None:
        return None
    unmerged = [f.path for f in read.status(repo).conflicts]
    if unmerged:
        return OpResult(status="conflicts", conflicts=unmerged, message=error.message)
    if error.code in ("conflicts", "git_failed") and operation == "rebase":
        return OpResult(status="stopped", message=error.message)
    return None


def _run(repo: Repo, *args: str, ok_status: Status = "done") -> OpResult:
    with repo.write():
        try:
            out = repo.run(*args, timeout=300)
        except GitxError as error:
            stopped = _stopped(repo, error)
            if stopped is None:
                raise
            return stopped
    if "Already up to date" in out or "is up to date" in out:
        return _result(repo, "up_to_date", out)
    # A rebase that paused on an `edit` line exits 0 and stays in progress.
    if read.operation_in_progress(repo) == "rebase":
        return _result(repo, "stopped", out)
    return _result(repo, ok_status, out)


# --------------------------------------------------------------------------------- merge
def merge(repo: Repo, ref: str, mode: Mode = "no_ff", message: str | None = None) -> OpResult:
    """Merges `ref` into the current branch. `no_ff` always makes a merge commit; `ff` moves the
    branch when it can and merges otherwise; `squash` leaves the changes staged, uncommitted."""
    args = ["merge", "--no-edit"]
    if mode == "no_ff":
        args += ["--no-ff"] + (["-m", message] if message else [])
    elif mode == "ff":
        args.append("--ff")
    else:
        args.append("--squash")
    args.append(ref)
    return _run(repo, *args, ok_status="squashed" if mode == "squash" else "done")


# --------------------------------------------------------------------------------- rebase
def rebase(repo: Repo, onto: str) -> OpResult:
    """Replays the current branch's commits on top of `onto`."""
    return _run(repo, "rebase", onto)


@dataclass
class TodoItem:
    action: TodoAction
    sha: str
    message: str | None = None  # `reword`


def plan(repo: Repo, base: str) -> list[read.CommitInfo]:
    """The commits an interactive rebase onto `base` would offer, oldest first."""
    merges = repo.run("rev-list", "--merges", "--count", f"{base}..HEAD").strip()
    if merges != "0":
        raise GitxError(
            "rebase_has_merges",
            "the commits to rebase include merges, which an interactive rebase would flatten",
            status=422,
        )
    out = repo.run(
        "log", "--reverse", "--topo-order", f"--format={read.LOG_FORMAT}", f"{base}..HEAD"
    )
    return read._commits(out)


def rebase_interactive(repo: Repo, base: str, items: list[TodoItem]) -> OpResult:
    """Rebases onto `base` with the list the person arranged: reordered, squashed, reworded,
    edited or dropped commits. Every commit of `base..HEAD` must be in the list."""
    commits = plan(repo, base)
    known = {c.sha for c in commits}
    if {i.sha for i in items} != known or len(items) != len(known):
        raise GitxError(
            "stale_rebase",
            "the commits changed since the list was made: build it again",
            status=409,
        )
    kept = [i for i in items if i.action != "drop"]
    if kept and kept[0].action in ("squash", "fixup"):
        raise GitxError(
            "bad_rebase", "the first commit cannot be squashed into nothing", status=422
        )
    scratch = Path(tempfile.mkdtemp(prefix="rebase-"))
    try:
        lines: list[str] = []
        for item in items:
            if item.action == "drop":
                lines.append(f"drop {item.sha}")
            elif item.action == "reword":
                lines.append(f"pick {item.sha}")
                note = scratch / f"{uuid.uuid4().hex}.txt"
                note.write_text((item.message or "").strip() + "\n", "utf-8", newline="\n")
                lines.append(f"exec git commit --amend --allow-empty -q -F '{note.as_posix()}'")
            else:
                lines.append(f"{item.action} {item.sha}")
        todo = scratch / "todo.txt"
        todo.write_text("\n".join(lines) + "\n", "utf-8", newline="\n")
        # git runs the editor through its own sh: a shell script with a POSIX path.
        editor = scratch / "editor.sh"
        editor.write_text(f'#!/bin/sh\ncp "{todo.as_posix()}" "$1"\n', "ascii", newline="\n")
        with repo.write():
            try:
                out = repo.run(
                    "rebase",
                    "-i",
                    base,
                    env={"GIT_SEQUENCE_EDITOR": editor.as_posix()},
                    timeout=600,
                )
            except GitxError as error:
                stopped = _stopped(repo, error)
                if stopped is None:
                    raise
                return stopped
        if read.operation_in_progress(repo) == "rebase":
            return _result(repo, "stopped", out)
        return _result(repo, "done", out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# --------------------------------------------------------------------------------- picks
def cherry_pick(repo: Repo, shas: list[str]) -> OpResult:
    return _run(repo, "cherry-pick", *shas)


def revert(repo: Repo, shas: list[str]) -> OpResult:
    return _run(repo, "revert", "--no-edit", *shas)


def reset(repo: Repo, ref: str, mode: ResetMode = "mixed") -> OpResult:
    """Moves the current branch to `ref`. `hard` also rewrites the files (the caller has
    confirmed and backed up)."""
    with repo.write():
        repo.run("reset", f"--{mode}", ref)
    return OpResult(status="done")


# --------------------------------------------------------------------------------- continue
def proceed(repo: Repo, action: Literal["continue", "skip", "abort"]) -> OpResult:
    """Carries on, skips or abandons the operation that is half done."""
    operation = read.operation_in_progress(repo)
    if operation is None or operation == "bisect":
        raise GitxError("no_operation", "there is nothing half done", status=409)
    if operation == "merge":
        if action == "abort":
            with repo.write():
                repo.run("merge", "--abort")
            return OpResult(status="done")
        if action == "skip":
            raise GitxError("bad_action", "a merge cannot be skipped", status=422)
        with repo.write():
            if read.status(repo).conflicts:
                raise GitxError("conflicts_unresolved", "resolve every conflict first", status=409)
            repo.run("commit", "--no-edit")
        return OpResult(status="done")
    command = {"rebase": "rebase", "cherry-pick": "cherry-pick", "revert": "revert"}[operation]
    if action == "continue" and read.status(repo).conflicts:
        raise GitxError("conflicts_unresolved", "resolve every conflict first", status=409)
    return _run(repo, command, f"--{action}")


# --------------------------------------------------------------------------------- conflicts
class ConflictFile(BaseModel):
    path: str
    base: str | None = None  # the common ancestor's version
    ours: str | None = None  # None: that side deleted the file
    theirs: str | None = None
    merged: str | None = None  # the file as git left it, with its conflict markers
    binary: bool = False
    ours_label: str = ""
    theirs_label: str = ""


def _stage(repo: Repo, number: int, path: str) -> str | None:
    try:
        raw = repo.run_raw("show", f":{number}:{path}", literal=True)
    except GitxError:
        return None
    return raw.decode("utf-8", "replace")


def _label_of_theirs(repo: Repo) -> str:
    for ref in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        found = repo.attempt("rev-parse", "--short", "--verify", "-q", ref)
        if found:
            return found.strip()
    return "theirs"


def conflict(repo: Repo, path: str) -> ConflictFile:
    """The three versions of a file that did not merge, and the file with its markers."""
    staged = repo.run("ls-files", "-u", "-z", "--", path, literal=True)
    if not staged.strip("\0"):
        raise GitxError("not_conflicted", f"{path} has no conflict", status=404)
    target = Path(repo.path) / path
    raw = target.read_bytes() if target.is_file() else b""
    binary = b"\0" in raw[:8000]
    return ConflictFile(
        path=path,
        base=None if binary else _stage(repo, 1, path),
        ours=None if binary else _stage(repo, 2, path),
        theirs=None if binary else _stage(repo, 3, path),
        merged=None if binary else raw.decode("utf-8", "replace"),
        binary=binary,
        ours_label=(repo.attempt("branch", "--show-current") or "").strip() or "HEAD",
        theirs_label=_label_of_theirs(repo),
    )


def resolve(repo: Repo, path: str, content: str) -> None:
    """Saves the resolved file and marks it as resolved."""
    target = Path(repo.path) / path
    with repo.write():
        target.write_bytes(content.encode("utf-8"))
        repo.run("add", "--", path, literal=True)


def take(repo: Repo, path: str, side: Side) -> None:
    """Resolves a file by taking one side whole (a file that side deleted is deleted)."""
    with repo.write():
        try:
            repo.run("checkout", f"--{side}", "--", path, literal=True)
            repo.run("add", "--", path, literal=True)
        except GitxError:  # that side deleted it
            repo.run("rm", "-q", "--", path, literal=True)


def conflict_paths(repo: Repo) -> list[str]:
    return [f.path for f in read.status(repo).conflicts]


__all__ = [
    "ConflictFile",
    "OpResult",
    "TodoItem",
    "cherry_pick",
    "conflict",
    "conflict_paths",
    "merge",
    "plan",
    "proceed",
    "rebase",
    "rebase_interactive",
    "reset",
    "resolve",
    "revert",
    "take",
]
