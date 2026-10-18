"""What a run did with git, and undoing it (phase 12, ADR 0019).

When a run starts the references of each of its repositories are noted. When it ends they are
compared with how they are then, and the reflog of the run's own folder says which commits it
made: that is how commits, branches, tags and pushes are told apart from what other tasks did in
the same repository at the same time (a worktree has its own `HEAD` reflog).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentic_os.models import CommitAttribution, GitOperation, ProjectRepo, Run
from agentic_os.services.gitx import oplog, trees
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

HEADS, TAGS, REMOTES = "refs/heads/", "refs/tags/", "refs/remotes/"
# Reflog subjects of `HEAD` that mean «a commit was made here».
COMMIT_KINDS = re.compile(
    r"^(commit( \((amend|merge|initial)\))?|rebase \((pick|continue)\)|cherry-pick|merge)"
)
WHEN = re.compile(r"\{(\d+)\}")


class BranchMove(BaseModel):
    name: str
    start: str | None  # where it was when the run started (None: it did not exist)
    end: str | None  # where it ended (None: the run deleted it)


class Push(BaseModel):
    remote: str
    branch: str
    start: str | None
    end: str
    forced: bool


class RunCommit(BaseModel):
    sha: str
    subject: str
    kind: str  # commit | amend | merge | rebase | cherry-pick


class Activity(BaseModel):
    commits: list[RunCommit] = Field(default_factory=list)
    branches: list[BranchMove] = Field(default_factory=list)
    tags: list[BranchMove] = Field(default_factory=list)
    pushes: list[Push] = Field(default_factory=list)
    head_start: str | None = None
    head_end: str | None = None
    # Set when the person undid it.
    undone: bool = False

    @property
    def empty(self) -> bool:
        return not (self.commits or self.branches or self.tags or self.pushes)


# ------------------------------------------------------------------------------ before and after
def snapshot(repo: Repo) -> dict[str, Any]:
    """Every branch, tag and remote branch with where it points, and where HEAD is."""
    refs: dict[str, str] = {}
    out = repo.run(
        "for-each-ref",
        "--format=%(refname)\t%(objectname)",
        "refs/heads",
        "refs/tags",
        "refs/remotes",
    )
    for line in out.splitlines():
        ref, _, sha = line.partition("\t")
        if sha:
            refs[ref] = sha
    return {"refs": refs, "head": oplog.head_state(repo), "reflog": _reflog_size(repo)}


def _reflog_size(repo: Repo) -> int:
    return len((repo.attempt("reflog", "show", "--format=%H", "HEAD") or "").split())


def _started(refs: dict[str, str], prefix: str) -> dict[str, str]:
    return {k.removeprefix(prefix): v for k, v in refs.items() if k.startswith(prefix)}


def _commits(repo: Repo, before: int | None, since: int, until: int) -> list[RunCommit]:
    """The commits made in this folder since the snapshot, oldest first, from its HEAD reflog.
    The reflog is counted, not timed (`before`: how many entries it had); the clock (`since`,
    `until`) is only for a snapshot that did not count them."""
    out = repo.attempt("reflog", "show", "--date=unix", "--format=%H	%gd	%gs", "HEAD") or ""
    lines = out.splitlines()  # newest first
    fresh = lines[: max(len(lines) - before, 0)] if before is not None else lines
    found: list[RunCommit] = []
    for line in fresh:
        sha, _, rest = line.partition("	")
        selector, _, subject = rest.partition("	")
        match = WHEN.search(selector)
        if not match or not COMMIT_KINDS.match(subject):
            continue
        if before is None and not since <= int(match[1]) <= until:
            continue
        kind = subject.split(":", 1)[0]
        label = (
            "amend"
            if "amend" in kind
            else "merge"
            if kind.startswith(("commit (merge)", "merge"))
            else "rebase"
            if kind.startswith("rebase")
            else "cherry-pick"
            if kind.startswith("cherry-pick")
            else "commit"
        )
        title = repo.attempt("log", "-1", "--format=%s", sha) or ""
        found.append(RunCommit(sha=sha, subject=title.strip(), kind=label))
    found.reverse()
    return found


def _moves(start: dict[str, str], end: dict[str, str]) -> list[BranchMove]:
    names = sorted(set(start) | set(end))
    return [
        BranchMove(name=n, start=start.get(n), end=end.get(n))
        for n in names
        if start.get(n) != end.get(n)
    ]


def _is_ancestor(repo: Repo, old: str, new: str) -> bool:
    """Exit code 1 of `merge-base --is-ancestor` is the answer «no», not a failure."""
    try:
        repo.run("merge-base", "--is-ancestor", old, new)
    except GitxError:
        return False
    return True


def collect(repo: Repo, before: dict[str, Any], since: datetime, until: datetime) -> Activity:
    """What changed in the repository between the snapshot and now, as far as this run did it.
    `repo` is the run's own folder."""
    now = snapshot(repo)
    start_refs, end_refs = before.get("refs", {}), now["refs"]
    commits = _commits(
        repo, before.get("reflog"), int(since.timestamp()) - 1, int(until.timestamp()) + 2
    )
    made = {c.sha for c in commits}
    current = (repo.attempt("branch", "--show-current") or "").strip()

    heads_start, heads_end = _started(start_refs, HEADS), _started(end_refs, HEADS)
    head_at_start = (before.get("head") or "").removeprefix("branch:")
    branches = []
    for move in _moves(heads_start, heads_end):
        mine = (
            move.end is None  # nobody else can delete a branch that is checked out elsewhere
            or move.end in made
            or move.name in (current, head_at_start)
            or (
                move.start is None and move.end == (repo.attempt("rev-parse", "HEAD") or "").strip()
            )
        )
        if mine:
            branches.append(move)

    tags = _moves(_started(start_refs, TAGS), _started(end_refs, TAGS))

    pushes: list[Push] = []
    for move in _moves(_started(start_refs, REMOTES), _started(end_refs, REMOTES)):
        remote, _, branch = move.name.partition("/")
        if move.end is None or branch in ("", "HEAD"):
            continue
        ours = move.end in made or any(_is_ancestor(repo, sha, move.end) for sha in made)
        if not ours:
            continue
        forced = bool(move.start) and not _is_ancestor(repo, move.start or "", move.end)
        pushes.append(
            Push(remote=remote, branch=branch, start=move.start, end=move.end, forced=forced)
        )

    return Activity(
        commits=commits,
        branches=branches,
        tags=tags,
        pushes=pushes,
        head_start=before.get("head"),
        head_end=now["head"],
    )


def attribute(
    db: Session, repo_id: str, run: Run, commits: list[RunCommit], task_code: str | None
) -> int:
    """Records who made the commits (the ones already known are kept)."""
    known = {
        sha
        for (sha,) in db.query(CommitAttribution.sha).filter(
            CommitAttribution.repo_id == repo_id,
            CommitAttribution.sha.in_([c.sha for c in commits]),
        )
    }
    added = 0
    for commit in commits:
        if commit.sha in known:
            continue
        db.add(
            CommitAttribution(
                repo_id=repo_id,
                sha=commit.sha,
                run_id=run.id,
                task_id=run.task_id,
                agent_id=run.agent_id,
                agent_name=run.agent_name,
                task_code=task_code,
            )
        )
        added += 1
    return added


def attributions(db: Session, repo_id: str, shas: list[str]) -> dict[str, CommitAttribution]:
    if not shas:
        return {}
    rows = db.query(CommitAttribution).filter(
        CommitAttribution.repo_id == repo_id, CommitAttribution.sha.in_(shas)
    )
    return {row.sha: row for row in rows}


# ------------------------------------------------------------------------------ undoing
class UndoItem(BaseModel):
    branch: str
    # reverted | deleted | skipped
    result: str
    reason: str | None = None


class UndoResult(BaseModel):
    items: list[UndoItem]
    operation_id: str | None = None


def pushed(activity: Activity) -> bool:
    return bool(activity.pushes)


def undo(db: Session, row: ProjectRepo, repo: Repo, activity: Activity) -> UndoResult:
    """Puts the local branches the run moved back where they were (the ones it created are
    deleted). A branch that moved after the run, or that is checked out with changes, is left
    alone and reported. What was pushed is not touched. Recorded as an operation, so it can be
    undone too."""
    items: list[UndoItem] = []
    operation: GitOperation | None = None
    checked_out = {t.branch: t.path for t in trees.worktrees(repo) if t.branch}
    with repo.write():
        for move in activity.branches:
            current = (
                repo.attempt("rev-parse", "--verify", "-q", f"{HEADS}{move.name}") or ""
            ).strip()
            if (current or None) != move.end:
                items.append(UndoItem(branch=move.name, result="skipped", reason="moved_since"))
                continue
            if operation is None:
                operation = oplog.begin(
                    db, row, repo, "undo_run", "Deshacer lo que hizo una ejecución", worktree=True
                )
            where = checked_out.get(move.name)
            try:
                if move.start is None:
                    if where:
                        items.append(
                            UndoItem(branch=move.name, result="skipped", reason="checked_out")
                        )
                        continue
                    repo.run("branch", "-D", move.name)
                    items.append(UndoItem(branch=move.name, result="deleted"))
                elif where:
                    Repo(where).run("reset", "--keep", move.start)
                    items.append(UndoItem(branch=move.name, result="reverted"))
                else:
                    repo.run("update-ref", f"{HEADS}{move.name}", move.start, move.end or "")
                    items.append(UndoItem(branch=move.name, result="reverted"))
            except GitxError as error:
                items.append(UndoItem(branch=move.name, result="skipped", reason=error.code))
    if operation is not None:
        oplog.finish(operation, repo)
    return UndoResult(items=items, operation_id=operation.id if operation else None)
