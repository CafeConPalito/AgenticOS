"""Snapshots of a run's folder, to show what each run changed (ADR 0015).

`take()` writes a commit with no branch that holds the folder as it is right now: what is
committed, what is modified and what is new and not ignored. It uses a copy of the folder's
index, so the real index, `HEAD`, the branches and the files are never touched. Copying the index
(instead of starting from an empty one) keeps git's stat cache: `git add -A` only re-reads what
changed, like a `git status`.

The commit is kept alive by a ref under `refs/agentic-os/runs/<run id>/{start,end}`. Those are not
branches or tags, so `git branch`, `git tag` and a plain `git push` ignore them, and they survive
`git gc` and the removal of a task's worktree (worktrees share the repository's refs).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from agentic_os.services import git

log = structlog.get_logger()

REF_ROOT = "refs/agentic-os"
BUDGET = 30.0  # seconds for a whole snapshot; a slow one is dropped, never blocks a run
MAX_NEW_FILE = 5 * 1024 * 1024  # new files above this are left out
# Identity of the snapshot commits: nobody reads it, and the repo may have none.
IDENTITY = ("user.name=Agentic OS", "user.email=agentic-os@localhost", "commit.gpgsign=false")
CHUNK = 50  # paths per command


@dataclass(frozen=True)
class Snapshot:
    sha: str
    skipped_large: int = 0  # new files over MAX_NEW_FILE that are not in it


def ref_name(run_id: str, label: str) -> str:
    return f"{REF_ROOT}/runs/{run_id}/{label}"


class _Budget:
    def __init__(self, seconds: float) -> None:
        self._deadline = time.monotonic() + seconds

    def left(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise git.GitError("snapshot: out of time")
        return remaining


def _index_path(folder: str) -> Path | None:
    raw = git.run(folder, "rev-parse", "--git-path", "index", timeout=10).strip()
    path = Path(raw)
    path = path if path.is_absolute() else Path(folder) / path
    return path if path.is_file() else None


def is_repo(folder: str) -> bool:
    """Cheap check (git.detect also runs a full `git status`)."""
    try:
        inside = git.run(folder, "rev-parse", "--is-inside-work-tree", timeout=10)
    except git.GitError:
        return False
    return inside.strip() == "true"


def take(
    folder: str,
    run_id: str | None = None,
    label: str | None = None,
    scratch: Path | None = None,
) -> Snapshot | None:
    """A snapshot of `folder`, or None when it is not a git repository or it could not be taken.
    With `run_id` and `label` it is also pinned to its ref.

    Never raises: the callers (run start and end) must not fail because of a snapshot. The error
    is logged; the caller records it as a system event of the run when it matters."""
    snapshot, _ = take_checked(folder, run_id, label, scratch)
    return snapshot


def take_checked(
    folder: str,
    run_id: str | None = None,
    label: str | None = None,
    scratch: Path | None = None,
) -> tuple[Snapshot | None, str | None]:
    """Like `take`, plus the reason when it failed (None when it worked or the folder has no
    git)."""
    if not Path(folder).is_dir() or not is_repo(folder):
        return None, None
    temporary: Path | None = None
    try:
        budget = _Budget(BUDGET)
        if scratch is not None:
            scratch.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix="index-", dir=scratch)
        os.close(handle)
        temporary = Path(name)
        real = _index_path(folder)
        if real is not None:
            temporary.write_bytes(real.read_bytes())
        else:
            temporary.unlink()  # git starts an empty index when the file does not exist
        env = {"GIT_INDEX_FILE": str(temporary)}

        def run(*args: str, config: tuple[str, ...] = ()) -> str:
            return git.run(folder, *args, timeout=budget.left(), env=env, config=config)

        big = _large_new_files(folder, budget)
        run("add", "-A")
        for start in range(0, len(big), CHUNK):
            run("rm", "--cached", "-q", "--ignore-unmatch", "--", *big[start : start + CHUNK])
        tree = run("write-tree").strip()
        parent = _head(folder, budget)
        args = ["commit-tree", tree, "-m", f"agentic-os snapshot {run_id or ''} {label or ''}"]
        if parent:
            args[2:2] = ["-p", parent]
        sha = run(*args, config=IDENTITY).strip()
        if run_id and label:
            git.run(
                folder,
                "update-ref",
                ref_name(run_id, label),
                sha,
                timeout=budget.left(),
            )
        return Snapshot(sha, len(big)), None
    except (git.GitError, OSError) as error:
        log.warning("could not take a snapshot", folder=folder, error=str(error))
        return None, str(error)
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink()


def _head(folder: str, budget: _Budget) -> str | None:
    try:
        return git.run(folder, "rev-parse", "--verify", "-q", "HEAD", timeout=budget.left()).strip()
    except git.GitError:  # a repository with no commits yet
        return None


def _large_new_files(folder: str, budget: _Budget) -> list[str]:
    """New (untracked, not ignored) files over MAX_NEW_FILE, as paths relative to `folder`."""
    listing = git.run(folder, "ls-files", "-o", "--exclude-standard", "-z", timeout=budget.left())
    big: list[str] = []
    for relative in filter(None, listing.split("\0")):
        try:
            if (Path(folder) / relative).stat().st_size > MAX_NEW_FILE:
                big.append(relative)
        except OSError:
            continue  # gone since the listing
    return big


def exists(folder: str, sha: str | None) -> bool:
    if not sha:
        return False
    try:
        git.run(folder, "cat-file", "-e", f"{sha}^{{commit}}", timeout=10)
    except git.GitError:
        return False
    return True


def delete_runs(folder: str, run_ids: list[str]) -> int:
    """Drops the refs of these runs (their commits go with the next `git gc`). Returns how many
    refs were removed."""
    refs = [ref_name(run_id, label) for run_id in run_ids for label in ("start", "end")]
    return _delete_refs(folder, refs)


def delete_all(folder: str) -> int:
    if not Path(folder).is_dir() or not is_repo(folder):
        return 0
    return _delete_refs(folder, _list_refs(folder))


def count_runs(folder: str) -> int:
    """How many runs have snapshots in this repository."""
    if not Path(folder).is_dir() or not is_repo(folder):
        return 0
    return len({ref.rsplit("/", 1)[0] for ref in _list_refs(folder)})


def _list_refs(folder: str) -> list[str]:
    try:
        listing = git.run(folder, "for-each-ref", "--format=%(refname)", f"{REF_ROOT}/", timeout=30)
    except git.GitError:
        return []
    return [line for line in listing.splitlines() if line]


def _delete_refs(folder: str, refs: list[str]) -> int:
    if not Path(folder).is_dir() or not is_repo(folder):
        return 0
    present = set(_list_refs(folder))
    refs = [ref for ref in refs if ref in present]
    if not refs:
        return 0
    try:
        git.run(
            folder,
            "update-ref",
            "--stdin",
            "-z",  # NUL-terminated: text mode would turn "\n" into "\r\n" on Windows
            timeout=60,
            input="".join(f"delete {ref}\0\0" for ref in refs),
        )
    except git.GitError as error:
        log.warning("could not delete snapshot refs", folder=folder, error=str(error))
        return 0
    return len(refs)
