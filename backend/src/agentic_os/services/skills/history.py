"""Differences between two versions of a skill (phase 17, CA12), in the format of the change viewer
of phase 11 (`FileChange` + `FileDiff`), computed with difflib: skills need no git."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from agentic_os.schemas.changes import DiffLine, FileChange, FileDiff, Hunk
from agentic_os.services.skills.store import Manifest, SkillStore

CONTEXT = 3
MAX_LINES = 5_000  # more than this in one file: no content, like the change viewer


@dataclass
class FilePair:
    change: FileChange
    diff: FileDiff


def _text(data: bytes | None) -> list[str] | None:
    """The lines of a file, or None when it is binary."""
    if data is None:
        return []
    if b"\0" in data[:8_000]:
        return None
    try:
        return data.decode("utf-8").replace("\r\n", "\n").split("\n")
    except UnicodeDecodeError:
        return None


def _hunks(old: list[str], new: list[str]) -> list[Hunk]:
    hunks: list[Hunk] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for group in matcher.get_grouped_opcodes(CONTEXT):
        lines: list[DiffLine] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines += [
                    DiffLine(kind="context", old_no=i + 1, new_no=j + 1, text=old[i])
                    for i, j in zip(range(i1, i2), range(j1, j2), strict=True)
                ]
                continue
            lines += [DiffLine(kind="del", old_no=i + 1, text=old[i]) for i in range(i1, i2)]
            lines += [DiffLine(kind="add", new_no=j + 1, text=new[j]) for j in range(j1, j2)]
        first, last = group[0], group[-1]
        hunks.append(
            Hunk(
                old_start=first[1] + 1 if last[2] > first[1] else first[1],
                old_lines=last[2] - first[1],
                new_start=first[3] + 1 if last[4] > first[3] else first[3],
                new_lines=last[4] - first[3],
                lines=lines,
            )
        )
    return hunks


def _pair(path: str, old: bytes | None, new: bytes | None, old_path: str | None = None) -> FilePair:
    status = "added" if old is None else "deleted" if new is None else "modified"
    if old_path:
        status = "renamed"
    old_lines, new_lines = _text(old), _text(new)
    if old_lines is None or new_lines is None:
        change = FileChange(
            path=path,
            old_path=old_path,
            status=status,
            binary=True,
            old_size=len(old) if old is not None else None,
            new_size=len(new) if new is not None else None,
        )
        return FilePair(change, FileDiff(path=path, binary=True))
    if old is None:
        old_lines = []
    if new is None:
        new_lines = []
    if max(len(old_lines), len(new_lines)) > MAX_LINES:
        change = FileChange(path=path, old_path=old_path, status=status)
        return FilePair(change, FileDiff(path=path, too_large=True))
    hunks = _hunks(old_lines, new_lines)
    adds = sum(1 for h in hunks for line in h.lines if line.kind == "add")
    dels = sum(1 for h in hunks for line in h.lines if line.kind == "del")
    change = FileChange(path=path, old_path=old_path, status=status, additions=adds, deletions=dels)
    return FilePair(change, FileDiff(path=path, hunks=hunks))


def diff(store: SkillStore, old: Manifest, new: Manifest) -> list[FilePair]:
    """What changed from `old` to `new`, SKILL.md first and then by path. A file that moved
    without changing (same content, another path) is a rename."""
    removed = {p: e for p, e in old.items() if p not in new}
    added = {p: e for p, e in new.items() if p not in old}
    renames: dict[str, str] = {}
    by_hash = {e["sha256"]: p for p, e in removed.items()}
    for path, entry in added.items():
        source = by_hash.pop(entry["sha256"], None)
        if source is not None:
            renames[path] = source
    pairs: list[FilePair] = []
    for path in sorted(set(old) | set(new), key=lambda p: (p != "SKILL.md", p)):
        if path in renames.values():
            continue
        if path in renames:
            change = FileChange(path=path, old_path=renames[path], status="renamed")
            pairs.append(FilePair(change, FileDiff(path=path)))
            continue
        a, b = old.get(path), new.get(path)
        if a and b and a["sha256"] == b["sha256"]:
            continue
        pairs.append(
            _pair(
                path, store.get(a["sha256"]) if a else None, store.get(b["sha256"]) if b else None
            )
        )
    return pairs


def summary(pairs: list[FilePair]) -> str:
    """One line for the version list: «+12 -3 en SKILL.md · nuevo scripts/x.py»."""
    parts: list[str] = []
    for pair in pairs:
        change = pair.change
        if change.status == "added":
            parts.append(f"nuevo {change.path}")
        elif change.status == "deleted":
            parts.append(f"quitado {change.path}")
        elif change.status == "renamed":
            parts.append(f"{change.old_path} → {change.path}")
        elif change.binary:
            parts.append(f"cambiado {change.path}")
        else:
            parts.append(f"+{change.additions} -{change.deletions} en {change.path}")
    if len(parts) > 4:
        parts = [*parts[:4], f"y {len(parts) - 4} más"]
    return " · ".join(parts) or "sin cambios en los ficheros"
