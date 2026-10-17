"""The Git tab: state, history, branches, staging, commits, fetch/pull/push (phase 12)."""

from __future__ import annotations

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from agentic_os.api.projects import get_project_or_404
from agentic_os.api.repos import get_repo_or_404
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Project, ProjectRepo
from agentic_os.schemas.changes import Changes, FileDiff, FileLines
from agentic_os.schemas.git import (
    ApplyBody,
    BatchBody,
    BatchItem,
    BlameGroup,
    BranchCreate,
    BranchInfo,
    CommitBody,
    CommitDetail,
    CommitPage,
    DeleteBranches,
    DiscardBody,
    FetchBody,
    JobState,
    PathsBody,
    PullBody,
    PushBody,
    RemoteInfo,
    RenameBody,
    RepoOverview,
    RepoStatus,
    SwitchBody,
    UpstreamBody,
)
from agentic_os.services import changes as change_ops
from agentic_os.services import repos as repo_ops
from agentic_os.services.gitx import backup, read, remote, tasks, write
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.events import GitEvents
from agentic_os.services.gitx.jobs import JobManager
from agentic_os.services.gitx.runner import Repo
from agentic_os.services.gitx.write import LineRef

router = APIRouter(tags=["git"])
DbSession = Annotated[Session, Depends(get_session)]
Rev = Annotated[str, Query(min_length=1, max_length=200)]
FilePath = Annotated[str, Query(min_length=1, max_length=1000)]


# ----------------------------------------------------------------------------- plumbing
def _jobs(request: Request) -> JobManager:
    return request.app.state.git_jobs


def _events(request: Request) -> GitEvents:
    return request.app.state.git_events


def _open(db: Session, repo_id: str) -> tuple[ProjectRepo, Repo]:
    row = get_repo_or_404(db, repo_id)
    if row.missing or not Path(row.path).is_dir():
        raise ApiError(409, "repo_missing", "the repository folder is gone", "repo_id")
    return row, Repo(row.path)


def _confirm(confirmed: bool, what: str) -> None:
    if not confirmed:
        raise ApiError(428, "confirmation_required", what)


# ----------------------------------------------------------------------------- state
def _overview(row: ProjectRepo) -> RepoOverview:
    item = RepoOverview(
        repo_id=row.id,
        name=row.name,
        path=row.path,
        rel_path=row.rel_path,
        linked=row.linked,
        missing=row.missing,
        base_branch=row.base_branch,
    )
    if row.missing or not Path(row.path).is_dir():
        return item
    try:
        item.status = read.status(Repo(row.path), row.id)
    except GitxError as error:
        item.error = error.code
    return item


@router.get("/projects/{project_id}/git/overview")
def overview(project_id: str, db: DbSession) -> list[RepoOverview]:
    """Every repository of the project with its state: the Git tab's first view."""
    project = get_project_or_404(db, project_id)
    rows = repo_ops.ensure(db, project)
    db.commit()
    if len(rows) <= 1:
        return [_overview(r) for r in rows]
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
        return list(pool.map(_overview, rows))


@router.get("/repos/{repo_id}/status")
def repo_status(repo_id: str, db: DbSession) -> RepoStatus:
    row, repo = _open(db, repo_id)
    return read.status(repo, row.id)


@router.get("/repos/{repo_id}/branches")
def list_branches(repo_id: str, db: DbSession) -> list[BranchInfo]:
    row, repo = _open(db, repo_id)
    project = db.get(Project, row.project_id)
    base = repo_ops.base_of(project, row) if project else row.base_branch
    return tasks.annotate(db, row, read.branches(repo, base))


@router.get("/repos/{repo_id}/remotes")
def list_remotes(repo_id: str, db: DbSession) -> list[RemoteInfo]:
    return remote.remotes(_open(db, repo_id)[1])


@router.get("/repos/{repo_id}/log")
def history(
    repo_id: str,
    db: DbSession,
    skip: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = read.PAGE,
    ref: Annotated[str | None, Query(max_length=200)] = None,
    all_refs: bool = False,
    author: Annotated[str | None, Query(max_length=200)] = None,
    grep: Annotated[str | None, Query(max_length=500)] = None,
    search: Annotated[str | None, Query(max_length=500)] = None,
    path: Annotated[str | None, Query(max_length=1000)] = None,
    follow: bool = False,
) -> CommitPage:
    _row, repo = _open(db, repo_id)
    return read.log(
        repo,
        skip=skip,
        limit=limit,
        ref=ref,
        all_refs=all_refs,
        author=author,
        grep=grep,
        search=search,
        path=path,
        follow=follow,
    )


@router.get("/repos/{repo_id}/commits/{sha}")
def commit_detail(repo_id: str, sha: str, db: DbSession) -> CommitDetail:
    repo = _open(db, repo_id)[1]
    return read.commit_detail(repo, _full_sha(repo, sha))


@router.get("/repos/{repo_id}/blame")
def blame(repo_id: str, db: DbSession, path: FilePath, rev: str | None = None) -> list[BlameGroup]:
    return read.blame(_open(db, repo_id)[1], path, rev)


def _full_sha(repo: Repo, rev: str) -> str:
    found = repo.attempt("rev-parse", "--verify", "-q", f"{rev}^{{commit}}")
    if not found:
        raise GitxError("unknown_ref", f"{rev!r} is not a commit", status=404)
    return found.strip()


# ----------------------------------------------------------------------------- diffs
def _range(
    repo: Repo,
    kind: str,
    staged: bool,
    sha: str | None,
    old: str | None,
    new: str | None,
    merge_base: bool,
) -> change_ops.Range:
    if kind == "worktree":
        return change_ops.worktree_range(repo.path, staged)
    if kind == "commit" and sha:
        full = _full_sha(repo, sha)
        return change_ops.commit_range(
            repo.path, full, read.parent_or_empty(read.commit_detail(repo, full))
        )
    if kind == "compare" and old and new:
        return change_ops.compare_range(
            repo.path, _full_sha(repo, old), _full_sha(repo, new), merge_base
        )
    raise ApiError(422, "bad_diff_request", "say what to compare", "kind")


class DiffQuery:
    """What a diff is of: the work tree, one commit or two refs."""

    def __init__(
        self,
        kind: Annotated[str, Query(pattern="^(worktree|commit|compare)$")] = "worktree",
        staged: bool = False,
        sha: Annotated[str | None, Query(max_length=200)] = None,
        from_ref: Annotated[str | None, Query(alias="from", max_length=200)] = None,
        to: Annotated[str | None, Query(max_length=200)] = None,
        merge_base: bool = False,
    ) -> None:
        self.kind, self.staged, self.sha = kind, staged, sha
        self.old, self.new, self.merge_base = from_ref, to, merge_base


Diff = Annotated[DiffQuery, Depends()]


@router.get("/repos/{repo_id}/diff")
def diff(repo_id: str, db: DbSession, query: Diff) -> Changes:
    row, repo = _open(db, repo_id)
    rng = _range(repo, query.kind, query.staged, query.sha, query.old, query.new, query.merge_base)
    rng.key, rng.name = row.id, row.name
    return change_ops.combine([rng])


@router.get("/repos/{repo_id}/diff/file")
def diff_file(
    repo_id: str,
    db: DbSession,
    query: Diff,
    path: FilePath,
    old_path: Annotated[str | None, Query(max_length=1000)] = None,
) -> FileDiff:
    _row, repo = _open(db, repo_id)
    rng = _range(repo, query.kind, query.staged, query.sha, query.old, query.new, query.merge_base)
    return change_ops.file_diff(rng, path, old_path)


@router.get("/repos/{repo_id}/diff/lines")
def diff_lines(
    repo_id: str,
    db: DbSession,
    query: Diff,
    path: FilePath,
    start: Annotated[int, Query(ge=1, le=10_000_000)],
    end: Annotated[int, Query(ge=1, le=10_000_000)],
) -> FileLines:
    _row, repo = _open(db, repo_id)
    rng = _range(repo, query.kind, query.staged, query.sha, query.old, query.new, query.merge_base)
    return change_ops.file_lines(rng, path, start, end)


# ----------------------------------------------------------------------------- staging
def _clean_paths(paths: list[str]) -> list[str]:
    """Paths from a client: relative, inside the repository, with no `..`."""
    for path in paths:
        parts = path.replace("\\", "/").split("/")
        if (
            not path
            or "\0" in path
            or path.startswith(("/", "\\"))
            or ".." in parts
            or ":" in parts[0]
        ):
            raise NotFound("file")
    return paths


@router.post("/repos/{repo_id}/stage", status_code=status.HTTP_204_NO_CONTENT)
def stage(repo_id: str, body: PathsBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.stage(repo, _clean_paths(body.paths))
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/unstage", status_code=status.HTTP_204_NO_CONTENT)
def unstage(repo_id: str, body: PathsBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.unstage(repo, _clean_paths(body.paths))
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
def discard(repo_id: str, body: DiscardBody, db: DbSession, request: Request) -> None:
    """Throws away changes. A copy of the work tree is kept first (`refs/agentic-os/backup/`)."""
    row, repo = _open(db, repo_id)
    _confirm(body.confirm, "discarding loses uncommitted work")
    paths = _clean_paths(body.paths)
    current = read.status(repo)
    untracked = {f.path for f in current.unstaged if f.kind == "untracked"}
    backup.worktree(repo, "discard")
    write.discard(
        repo, [p for p in paths if p not in untracked], [p for p in paths if p in untracked]
    )
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/apply", status_code=status.HTTP_204_NO_CONTENT)
def apply(repo_id: str, body: ApplyBody, db: DbSession, request: Request) -> None:
    """Stages, unstages or discards some hunks or lines of one file."""
    row, repo = _open(db, repo_id)
    _clean_paths([body.path])
    if body.action == "discard":
        _confirm(body.confirm, "discarding loses uncommitted work")
        backup.worktree(repo, "discard")
    write.apply_selection(
        repo,
        body.action,
        body.path,
        [tuple(h) for h in body.hunks],  # type: ignore[misc]
        [LineRef(line.kind, line.no) for line in body.lines],
    )
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/commit")
def commit(repo_id: str, body: CommitBody, db: DbSession, request: Request) -> CommitDetail:
    row, repo = _open(db, repo_id)
    sha = write.commit(repo, body.message, amend=body.amend, no_verify=body.no_verify)
    _events(request).changed(row.id)
    return read.commit_detail(repo, sha)


# ----------------------------------------------------------------------------- branches
@router.post("/repos/{repo_id}/branches", status_code=status.HTTP_204_NO_CONTENT)
def create_branch(repo_id: str, body: BranchCreate, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.create_branch(repo, body.name, body.start, body.switch)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/switch", status_code=status.HTTP_204_NO_CONTENT)
def switch(repo_id: str, body: SwitchBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.switch_branch(repo, body.name)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/branches/rename", status_code=status.HTTP_204_NO_CONTENT)
def rename_branch(repo_id: str, body: RenameBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.rename_branch(repo, body.old, body.new)
    _events(request).changed(row.id)


@router.post("/repos/{repo_id}/branches/delete")
def delete_branches(
    repo_id: str, body: DeleteBranches, db: DbSession, request: Request
) -> dict[str, dict[str, str]]:
    """Deletes local branches; those git refuses are returned with the reason. `force` (`-D`)
    loses commits nothing else has, so it needs `confirm`."""
    row, repo = _open(db, repo_id)
    if body.force:
        _confirm(body.confirm, "forcing the delete loses commits that are on no other branch")
    failed: dict[str, str] = {}
    for name in body.names:
        try:
            write.delete_branch(repo, name, body.force)
        except GitxError as error:
            failed[name] = error.code
    _events(request).changed(row.id)
    return {"failed": failed}


@router.post("/repos/{repo_id}/branches/upstream", status_code=status.HTTP_204_NO_CONTENT)
def set_upstream(repo_id: str, body: UpstreamBody, db: DbSession, request: Request) -> None:
    row, repo = _open(db, repo_id)
    write.set_upstream(repo, body.branch, body.upstream)
    _events(request).changed(row.id)


# ----------------------------------------------------------------------------- network jobs
def _start_fetch(request: Request, row: ProjectRepo, repo: Repo, body: FetchBody) -> JobState:
    args = remote.fetch_args(body.remote, body.prune)
    return _jobs(request).start(repo, row.id, "fetch", args)


def _start_pull(request: Request, row: ProjectRepo, repo: Repo, body: PullBody) -> JobState:
    args = remote.pull_args(body.mode or row.pull_mode, body.remote, body.branch)  # type: ignore[arg-type]
    return _jobs(request).start(repo, row.id, "pull", args, exclusive=True)


def _start_push(request: Request, row: ProjectRepo, repo: Repo, body: PushBody) -> JobState:
    args = remote.push_args(repo, body.remote, body.branch, body.set_upstream)
    return _jobs(request).start(repo, row.id, "push", args)


@router.post("/repos/{repo_id}/fetch", status_code=status.HTTP_202_ACCEPTED)
def fetch(repo_id: str, body: FetchBody, db: DbSession, request: Request) -> JobState:
    row, repo = _open(db, repo_id)
    return _start_fetch(request, row, repo, body)


@router.post("/repos/{repo_id}/pull", status_code=status.HTTP_202_ACCEPTED)
def pull(repo_id: str, body: PullBody, db: DbSession, request: Request) -> JobState:
    row, repo = _open(db, repo_id)
    return _start_pull(request, row, repo, body)


@router.post("/repos/{repo_id}/push", status_code=status.HTTP_202_ACCEPTED)
def push(repo_id: str, body: PushBody, db: DbSession, request: Request) -> JobState:
    row, repo = _open(db, repo_id)
    return _start_push(request, row, repo, body)


@router.get("/git/jobs/{job_id}")
def job(job_id: str, request: Request) -> JobState:
    state = _jobs(request).get(job_id)
    if state is None:
        raise NotFound("job")
    return state


@router.delete("/git/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(job_id: str, request: Request) -> None:
    if not _jobs(request).cancel(job_id):
        raise NotFound("job")


@router.get("/repos/{repo_id}/jobs")
def active_jobs(repo_id: str, db: DbSession, request: Request) -> list[JobState]:
    return _jobs(request).active(get_repo_or_404(db, repo_id).id)


# ----------------------------------------------------------------------------- several repos
@router.post("/projects/{project_id}/git/batch")
def batch(project_id: str, body: BatchBody, db: DbSession, request: Request) -> list[BatchItem]:
    """The same action in several repositories of a project. Each one succeeds or fails on its
    own; the others still run."""
    project = get_project_or_404(db, project_id)
    known = {r.id: r for r in repo_ops.ensure(db, project)}
    results: list[BatchItem] = []
    for repo_id in body.repo_ids:
        row = known.get(repo_id)
        if row is None:
            results.append(BatchItem(repo_id=repo_id, ok=False, error_code="repo_not_found"))
            continue
        try:
            results.append(_batch_one(request, row, body))
        except GitxError as error:
            results.append(
                BatchItem(repo_id=repo_id, ok=False, error_code=error.code, error=error.message)
            )
        except ApiError as error:
            results.append(
                BatchItem(repo_id=repo_id, ok=False, error_code=error.code, error=error.message)
            )
    return results


def _batch_one(request: Request, row: ProjectRepo, body: BatchBody) -> BatchItem:
    if row.missing or not Path(row.path).is_dir():
        raise ApiError(409, "repo_missing", "the repository folder is gone")
    repo = Repo(row.path)
    if body.action == "fetch":
        return BatchItem(repo_id=row.id, ok=True, job=_start_fetch(request, row, repo, FetchBody()))
    if body.action == "pull":
        return BatchItem(repo_id=row.id, ok=True, job=_start_pull(request, row, repo, PullBody()))
    if body.action == "push":
        return BatchItem(repo_id=row.id, ok=True, job=_start_push(request, row, repo, PushBody()))
    if body.action == "switch" and body.name:
        write.switch_branch(repo, body.name)
    elif body.action == "create_branch" and body.name:
        write.create_branch(repo, body.name, None, switch=True)
    elif body.action == "commit":
        sha = write.commit(repo, body.message or "")
        _events(request).changed(row.id)
        return BatchItem(repo_id=row.id, ok=True, sha=sha)
    else:
        raise ApiError(422, "bad_batch", "the action needs a name", "name")
    _events(request).changed(row.id)
    return BatchItem(repo_id=row.id, ok=True)


# ----------------------------------------------------------------------------- live events
@router.websocket("/git/events")
async def events(websocket: WebSocket) -> None:
    """`{"type": "job", "job": …}` while a fetch/pull/push runs, and `{"type": "repo_changed",
    "repo_id": …}` when a repository's state may have changed."""
    await websocket.accept()
    hub: GitEvents = websocket.app.state.git_events
    queue = hub.subscribe()
    listening = asyncio.ensure_future(websocket.receive_text())  # only to notice the client leaving
    try:
        while True:
            getting = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getting, listening}, return_when=asyncio.FIRST_COMPLETED)
            if listening in done:
                getting.cancel()
                listening.result()  # raises WebSocketDisconnect when the client left
                listening = asyncio.ensure_future(websocket.receive_text())
                continue
            await websocket.send_json(getting.result())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        listening.cancel()
        with contextlib.suppress(Exception):
            await websocket.close()
