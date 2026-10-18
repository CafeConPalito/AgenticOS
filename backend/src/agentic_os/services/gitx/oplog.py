"""The operations of the app that can be undone (phase 12, ADR 0017).

Before an operation that moves branches, the branches and HEAD are noted (and, if it can throw
uncommitted files away, a copy of the work tree). «Deshacer» puts every branch back, but only if
nothing touched it since: undoing must never overwrite work that came afterwards.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.models import GitOperation, ProjectRepo
from agentic_os.services.gitx import backup, read
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

HEADS = "refs/heads/"


def heads(repo: Repo) -> dict[str, str]:
    """Every local branch and where it points."""
    out = repo.run("for-each-ref", "--format=%(refname)\t%(objectname)", "refs/heads")
    pairs = (line.split("\t") for line in out.splitlines() if "\t" in line)
    return {ref: sha for ref, sha in pairs}


def head_state(repo: Repo) -> str | None:
    """`branch:<name>`, `sha:<sha>` (detached) or None (no commits yet)."""
    name = (repo.attempt("branch", "--show-current") or "").strip()
    if name:
        return f"branch:{name}"
    sha = (repo.attempt("rev-parse", "--verify", "-q", "HEAD") or "").strip()
    return f"sha:{sha}" if sha else None


def begin(
    db: Session,
    row: ProjectRepo,
    repo: Repo,
    kind: str,
    label: str,
    *,
    worktree: bool = False,
    group_id: str | None = None,
) -> GitOperation:
    """Notes how the repository is before the operation. `worktree`: it can lose uncommitted
    files, so a copy of them is kept too."""
    operation = GitOperation(
        repo_id=row.id,
        group_id=group_id,
        kind=kind,
        label=label,
        refs_before=heads(repo),
        head_before=head_state(repo),
        backup_ref=backup.worktree(repo, kind) if worktree else None,
    )
    db.add(operation)
    db.flush()
    return operation


def finish(operation: GitOperation, repo: Repo) -> None:
    operation.refs_after = heads(repo)


def drop_if_unchanged(db: Session, operation: GitOperation, repo: Repo) -> bool:
    """An operation that failed before touching anything is not worth an undo entry."""
    finish(operation, repo)
    if operation.refs_after == operation.refs_before and operation.backup_ref is None:
        db.delete(operation)
        return True
    return False


def recent(db: Session, repo_id: str, limit: int = 20) -> list[GitOperation]:
    return list(
        db.scalars(
            select(GitOperation)
            .where(GitOperation.repo_id == repo_id)
            .order_by(GitOperation.at.desc(), GitOperation.id)
            .limit(limit)
        )
    )


def last_undoable(db: Session, repo_id: str) -> GitOperation | None:
    """The newest operation of the repository that is over and has not been undone."""
    for operation in recent(db, repo_id, 50):
        if operation.undone_at is None and operation.refs_after is not None:
            return operation
    return None


def open_operation(db: Session, repo_id: str) -> GitOperation | None:
    """The operation that stopped half done (conflicts), waiting to be continued or aborted."""
    for operation in recent(db, repo_id, 5):
        if operation.undone_at is None and operation.refs_after is None:
            return operation
    return None


def blocker(operation: GitOperation, repo: Repo, now: dict[str, str] | None = None) -> str | None:
    """Why the operation cannot be undone now (None: it can)."""
    if operation.undone_at is not None:
        return "already_undone"
    if operation.refs_after is None or read.operation_in_progress(repo) is not None:
        return "operation_in_progress"
    now = heads(repo) if now is None else now
    after = operation.refs_after or {}
    for ref in set(operation.refs_before) | set(after):
        before_sha, after_sha = operation.refs_before.get(ref), after.get(ref)
        if before_sha != after_sha and now.get(ref) != after_sha:
            return "moved_since"  # something else moved this branch afterwards
    return None


def undo(operation: GitOperation, repo: Repo) -> None:
    """Puts every branch the operation moved back where it was, and brings back the files it
    threw away. Refuses (with the reason as the error code) when that is not safe."""
    reason = blocker(operation, repo)
    if reason is not None:
        raise GitxError(reason, f"this operation cannot be undone now ({reason})")
    after = operation.refs_after or {}
    with repo.write():
        current = (repo.attempt("branch", "--show-current") or "").strip()
        for ref in sorted(set(operation.refs_before) | set(after)):
            before_sha, after_sha = operation.refs_before.get(ref), after.get(ref)
            if before_sha == after_sha:
                continue
            name = ref.removeprefix(HEADS)
            if name == current and before_sha:
                # The branch is checked out: the files have to follow it.
                repo.run("reset", "--keep", before_sha)
            elif before_sha is None:
                repo.run("update-ref", "-d", ref, after_sha or "")
            else:
                repo.run("update-ref", ref, before_sha, after_sha or "")
        wanted = operation.head_before or ""
        if wanted.startswith("branch:") and wanted.removeprefix("branch:") != current:
            repo.run("switch", wanted.removeprefix("branch:"))
        if operation.backup_ref:
            # The files that were thrown away come back over the clean ones.
            repo.run("restore", f"--source={operation.backup_ref}", "--worktree", "--", ".")
    operation.undone_at = utcnow()
