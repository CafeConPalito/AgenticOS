"""Changing a repository: staging by file, hunk or line, committing, branches
(phase 12, ADR 0017).

Nothing here forces anything: an operation that would lose work is refused by git, and the ones
that do (discarding) are guarded by the caller (`confirm`) and take a backup first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentic_os.services.gitx import read
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

Action = Literal["stage", "unstage", "discard"]


# ----------------------------------------------------------------------------- by file
def stage(repo: Repo, paths: list[str]) -> None:
    """`git add` of these paths (new, changed and deleted ones alike)."""
    if not paths:
        return
    with repo.write():
        repo.run("add", "-A", "--", *paths, literal=True)


def unstage(repo: Repo, paths: list[str]) -> None:
    if not paths:
        return
    with repo.write():
        # `reset -- paths` works with and without a first commit.
        repo.run("reset", "-q", "--", *paths, literal=True)


def discard(repo: Repo, paths: list[str], untracked: list[str]) -> None:
    """Throws away the changes of tracked files and deletes the untracked ones. The caller
    has confirmed and backed up."""
    with repo.write():
        if paths:
            repo.run(
                "restore", "--source=HEAD", "--staged", "--worktree", "--", *paths, literal=True
            )
        if untracked:
            repo.run("clean", "-f", "-q", "--", *untracked, literal=True)


# ----------------------------------------------------------------------------- by hunk and line
HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass
class RawHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    tail: bytes  # what follows the closing @@ (the enclosing function)
    body: list[bytes] = field(default_factory=list)  # lines with their ' ', '+', '-' or '\\'


def split_diff(raw: bytes) -> tuple[list[bytes], list[RawHunk]]:
    """A one-file diff as its header lines and its hunks, byte for byte."""
    header: list[bytes] = []
    hunks: list[RawHunk] = []
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for line in lines:
        match = HUNK.match(line)
        if match:
            old_start, old_lines, new_start, new_lines, tail = match.groups()
            hunks.append(
                RawHunk(
                    int(old_start),
                    int(old_lines) if old_lines is not None else 1,
                    int(new_start),
                    int(new_lines) if new_lines is not None else 1,
                    tail,
                )
            )
        elif hunks:
            hunks[-1].body.append(line)
        else:
            header.append(line)
    return header, hunks


@dataclass(frozen=True)
class LineRef:
    """A changed line the person picked: an added one by its number in the new file, a deleted
    one by its number in the old file."""

    kind: Literal["add", "del"]
    no: int


def numbered(hunk: RawHunk) -> list[tuple[bytes, str, int | None]]:
    """Each body line with its kind (`ctx`, `add`, `del`, `mark`) and its line number."""
    old_no, new_no = hunk.old_start, hunk.new_start
    result: list[tuple[bytes, str, int | None]] = []
    for line in hunk.body:
        mark = line[:1]
        if mark == b"+":
            result.append((line, "add", new_no))
            new_no += 1
        elif mark == b"-":
            result.append((line, "del", old_no))
            old_no += 1
        elif mark == b"\\":
            result.append((line, "mark", None))
        else:
            result.append((line, "ctx", None))
            old_no += 1
            new_no += 1
    return result


def build_patch(
    header: list[bytes],
    hunks: list[RawHunk],
    action: Action,
    whole_hunks: set[tuple[int, int]],
    lines: set[LineRef],
) -> bytes | None:
    """The patch that applies only what was picked. None when nothing picked is in the diff.

    Applied forwards (`stage`) the target is the old side: a change that was not picked must
    leave it as it is, so an unpicked deletion becomes context and an unpicked addition goes.
    Applied backwards (`unstage`, `discard`) the target is the new side and it is the other way
    round."""
    forward = action == "stage"
    matched: set[LineRef] = set()
    out: list[bytes] = []
    delta = 0
    for hunk in hunks:
        whole = (hunk.old_start, hunk.new_start) in whole_hunks
        body: list[bytes] = []
        picked = False
        previous_kept = False
        for line, kind, number in numbered(hunk):
            if kind == "ctx":
                body.append(line)
                previous_kept = True
            elif kind == "mark":
                if previous_kept:
                    body.append(line)
                    if not whole:
                        # «\ No newline at end of file» ties a line to the end of the file: a
                        # partial pick would leave the patch contradicting itself.
                        raise GitxError(
                            "selection_unsupported",
                            "the end of this file has no final newline: pick the whole hunk",
                            status=422,
                        )
                continue
            else:
                ref = LineRef(kind, number or 0)  # type: ignore[arg-type]
                if ref in lines:
                    matched.add(ref)
                if whole or ref in lines:
                    body.append(line)
                    picked = True
                    previous_kept = True
                elif (kind == "del") == forward:
                    body.append(b" " + line[1:])  # stays on both sides
                    previous_kept = True
                else:
                    previous_kept = False  # not part of the patch at all
        if not picked:
            continue
        old_len = sum(1 for b in body if b[:1] in (b" ", b"-"))
        new_len = sum(1 for b in body if b[:1] in (b" ", b"+"))
        new_start = hunk.old_start + delta if forward else hunk.new_start
        old_start = hunk.old_start if forward else hunk.new_start - delta
        out.append(f"@@ -{old_start},{old_len} +{new_start},{new_len} @@".encode() + hunk.tail)
        out.extend(body)
        delta += new_len - old_len
    if not out or lines - matched:
        return None  # nothing picked is there, or a picked line is not in the diff any more
    return b"\n".join([*header, *out]) + b"\n"


def apply_selection(
    repo: Repo,
    action: Action,
    path: str,
    hunks: list[tuple[int, int]],
    lines: list[LineRef],
) -> None:
    """Stages, unstages or discards some hunks or lines of one file.

    The diff is read again now, so the picked lines are looked up in what is true now. If they
    are not there any more the file changed under the person (`stale_diff`): nothing is applied.
    """
    with repo.write():
        args = ["diff", "-U3", "--no-color", "--no-ext-diff"]
        if action == "unstage":
            args.append("--cached")
        raw = repo.run_raw(*args, "--", path, literal=True)
        if not raw.strip():
            raise GitxError("stale_diff", "the file has no changes of that kind any more")
        header, parsed = split_diff(raw)
        text = b"\n".join(header)
        if (
            not parsed
            or b"Binary files" in text
            or b"GIT binary patch" in raw
            or b"rename from" in text
            or b"deleted file mode" in text
            or b"new file mode" in text
        ):
            raise GitxError(
                "selection_unsupported",
                "hunks and lines can only be picked in files that exist on both sides, as text",
                status=422,
            )
        if not hunks and not lines:
            raise GitxError("nothing_selected", "pick at least one hunk or line", status=422)
        available = {(h.old_start, h.new_start) for h in parsed}
        picked_hunks = set(hunks)
        if not picked_hunks <= available:
            raise GitxError("stale_diff", "the file changed since it was shown")
        patch = build_patch(header, parsed, action, picked_hunks, set(lines))
        if patch is None:
            raise GitxError("stale_diff", "the file changed since it was shown")
        flags = ["apply", "--recount", "--whitespace=nowarn"]
        if action == "stage":
            flags.append("--cached")
        elif action == "unstage":
            flags += ["--cached", "-R"]
        else:
            flags.append("-R")
        try:
            repo.run_raw(*flags, "-", input=patch)
        except GitxError as error:
            if error.code in ("patch_failed", "git_failed"):
                raise GitxError(
                    "stale_diff", "the file changed since it was shown", error.output
                ) from error
            raise


# ----------------------------------------------------------------------------- commit
def commit(repo: Repo, message: str, *, amend: bool = False, no_verify: bool = False) -> str:
    """Commits what is staged (the whole message goes in through stdin, so line breaks stay).
    With `amend` and no message, the last one is kept. Returns the new commit's sha."""
    args = ["commit", "--cleanup=whitespace"]
    if amend:
        args.append("--amend")
    if no_verify:
        args.append("--no-verify")
    text = message.strip()
    if text:
        args += ["-F", "-"]
    elif amend:
        args.append("--no-edit")
    else:
        raise GitxError("empty_message", "write a commit message", status=422)
    with repo.write():
        try:
            repo.run(*args, input=text + "\n" if text else None, timeout=300)
        except GitxError as error:
            # A refusing hook prints only its own output: nothing says it was a hook.
            if error.code == "git_failed" and _has_commit_hooks(repo):
                raise GitxError("hook_failed", error.message, error.output) from error
            raise
        return repo.run("rev-parse", "HEAD").strip()


def _has_commit_hooks(repo: Repo) -> bool:
    configured = (repo.attempt("config", "--get", "core.hooksPath") or "").strip()
    folder = Path(configured) if configured else Path(read.git_common(repo)) / "hooks"
    if configured and not folder.is_absolute():
        folder = Path(repo.path) / folder
    return any(
        (folder / name).is_file() for name in ("pre-commit", "commit-msg", "pre-merge-commit")
    )


# ----------------------------------------------------------------------------- branches
def check_branch_name(repo: Repo, name: str) -> str:
    clean = name.strip()
    if not clean or repo.attempt("check-ref-format", "--branch", clean) is None:
        raise GitxError("invalid_ref", f"{name!r} is not a valid branch name", status=422)
    return clean


def create_branch(repo: Repo, name: str, start: str | None = None, switch: bool = False) -> None:
    name = check_branch_name(repo, name)
    with repo.write():
        if switch:
            repo.run("switch", "-c", name, *([start] if start else []))
        else:
            repo.run("branch", name, *([start] if start else []))


def switch_branch(repo: Repo, name: str) -> None:
    """Changes branch. A remote branch gets a local one that follows it. Never forced: changes
    that would be lost make git refuse (`dirty_worktree`)."""
    with repo.write():
        remote = repo.attempt("rev-parse", "--verify", "-q", f"refs/remotes/{name}")
        local = repo.attempt("rev-parse", "--verify", "-q", f"refs/heads/{name}")
        if remote and not local:
            repo.run("switch", "--track", name)
        else:
            repo.run("switch", name)


def rename_branch(repo: Repo, old: str, new: str) -> None:
    new = check_branch_name(repo, new)
    with repo.write():
        repo.run("branch", "-m", old, new)


def delete_branch(repo: Repo, name: str, force: bool = False) -> None:
    with repo.write():
        repo.run("branch", "-D" if force else "-d", name)


def set_upstream(repo: Repo, branch: str, upstream: str | None) -> None:
    with repo.write():
        if upstream:
            repo.run("branch", f"--set-upstream-to={upstream}", branch)
        else:
            repo.run("branch", "--unset-upstream", branch)
