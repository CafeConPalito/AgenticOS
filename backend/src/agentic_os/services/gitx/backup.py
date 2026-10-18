"""A copy of the work tree before something that throws work away (phase 12, ADR 0017).

It is a snapshot of the folder (ADR 0015) pinned under `refs/agentic-os/backup/`, so
`git restore --source=<ref> --worktree -- .` brings it back. The block that adds «Deshacer»
builds on this.
"""

from __future__ import annotations

import time

from agentic_os.services import snapshots
from agentic_os.services.gitx.runner import Repo

BACKUP_REFS = "refs/agentic-os/backup"


def worktree(repo: Repo, label: str) -> str | None:
    """Pins a snapshot of the repository's work tree; returns its ref (None: nothing to keep,
    e.g. a repository with no files yet, or the snapshot could not be taken)."""
    snapshot = snapshots.take(repo.path)
    if snapshot is None:
        return None
    ref = f"{BACKUP_REFS}/{time.time_ns()}-{label}"
    repo.run("update-ref", ref, snapshot.sha)
    return ref
