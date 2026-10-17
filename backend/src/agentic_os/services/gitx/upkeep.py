"""Cleaning and checking a repository: `clean`, `gc`, `fsck` (phase 12, ADR 0017)."""

from __future__ import annotations

from pydantic import BaseModel

from agentic_os.services.gitx.runner import Repo


class CleanPreview(BaseModel):
    files: list[str]  # what `clean` would delete
    folders: list[str]


def clean_preview(repo: Repo, folders: bool = True, ignored: bool = False) -> CleanPreview:
    """What `git clean` would delete, without deleting anything."""
    args = ["clean", "-n"]
    if folders:
        args.append("-d")
    if ignored:
        args.append("-x")
    files: list[str] = []
    dirs: list[str] = []
    for line in repo.run(*args).splitlines():
        name = line.removeprefix("Would remove ").strip()
        if not name or name == line.strip():
            continue
        (dirs if name.endswith("/") else files).append(name)
    return CleanPreview(files=files, folders=dirs)


def clean(repo: Repo, paths: list[str], folders: bool = True, ignored: bool = False) -> None:
    """Deletes untracked files (and folders, and ignored files if asked). Ignored files are not
    in the work-tree copies, so they cannot be brought back."""
    args = ["clean", "-f", "-q"]
    if folders:
        args.append("-d")
    if ignored:
        args.append("-x")
    with repo.write():
        repo.run(*args, "--", *paths, literal=True)


def gc_args() -> list[str]:
    return ["gc", "--prune=now", "--quiet"]


class Verification(BaseModel):
    ok: bool
    problems: list[str]


def verify(repo: Repo) -> Verification:
    """`git fsck`: is the object database consistent?"""
    try:
        out = repo.run("fsck", "--no-progress", timeout=600)
    except Exception as error:  # a broken repository makes fsck exit non-zero
        text = getattr(error, "output", "") or str(error)
        return Verification(
            ok=False, problems=[line for line in text.splitlines() if line.strip()][:50]
        )
    problems = [
        line for line in out.splitlines() if line.strip() and not line.startswith("Checking")
    ]
    return Verification(ok=not problems, problems=problems[:50])


class Size(BaseModel):
    loose: str
    packed: str
    garbage: str


def size(repo: Repo) -> Size:
    values: dict[str, str] = {}
    for line in repo.run("count-objects", "-vH").splitlines():
        key, _, value = line.partition(": ")
        values[key] = value
    return Size(
        loose=values.get("size", "0"),
        packed=values.get("size-pack", "0"),
        garbage=values.get("size-garbage", "0"),
    )
