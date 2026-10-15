"""What a run or a task changed: file lists and diffs between snapshots (phase 11, ADR 0015).

Diffs are never stored: they are computed by git when asked. Only the +/- summary of a run is
kept (`Run.changes_*`), to fill lists without recomputing diffs.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_os.services import git

# `--ignore-cr-at-eol`: a file that only changes between CRLF and LF is not a change.
DIFF_FLAGS = ("--ignore-cr-at-eol", "-M")
TIMEOUT = 60


@dataclass(frozen=True)
class Totals:
    files: int = 0
    additions: int = 0
    deletions: int = 0


def totals(folder: str, old: str, new: str) -> Totals:
    """Files, added and deleted lines between two commits (a binary file counts as one file with
    no lines)."""
    out = git.run(folder, "diff", "--numstat", "-z", *DIFF_FLAGS, old, new, timeout=TIMEOUT)
    files = additions = deletions = 0
    for added, deleted, _path, _old_path in numstat_entries(out):
        files += 1
        additions += added or 0
        deletions += deleted or 0
    return Totals(files, additions, deletions)


def numstat_entries(output: str) -> list[tuple[int | None, int | None, str, str | None]]:
    """Parses `git diff --numstat -z`: (added, deleted, path, old path), with None counts for
    binary files and an old path only for renames."""
    parts = output.split("\0")
    entries: list[tuple[int | None, int | None, str, str | None]] = []
    index = 0
    while index < len(parts):
        head = parts[index]
        index += 1
        if not head:
            continue
        added, deleted, path = head.split("\t", 2)
        old_path = None
        if path == "":  # a rename: the next two entries are the old and the new path
            old_path, path = parts[index], parts[index + 1]
            index += 2
        entries.append(
            (
                None if added == "-" else int(added),
                None if deleted == "-" else int(deleted),
                path,
                old_path,
            )
        )
    return entries
