"""What a run or a task changed: file lists and diffs between snapshots (phase 11, ADR 0015).

Diffs are never stored: git computes them when asked. Only the +/- summary of a run is kept
(`Run.changes_*`), to fill lists without recomputing diffs.

A `Range` is the pair of commits a diff goes between. Where each end comes from:
- a run: its start and end snapshots (a live run: the folder right now);
- a worktree task: the commit its branch started from and the end of its last run (or, when that
  snapshot is gone, the tip of its branch);
- a direct-folder task: the start of its first run and the end of its last one.
"""

from __future__ import annotations

import fnmatch
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    ACTIVE_STATUSES,
    Project,
    ProjectRepo,
    Run,
    RunRepo,
    RunStatus,
    Stage,
    Task,
    TaskRepo,
    WorkspaceMode,
)
from agentic_os.schemas.changes import (
    Changes,
    ChangesRunRef,
    ChangesState,
    ChangesTotals,
    DiffLine,
    FileChange,
    FileDiff,
    FileLines,
    Hunk,
    RefLabel,
    RepoChanges,
)
from agentic_os.services import git, repos, runrepos, snapshots
from agentic_os.services.gitx.runner import Repo

log = structlog.get_logger()

# `--ignore-cr-at-eol`: a file that only changes between CRLF and LF is not a change.
DIFF_FLAGS = ("--ignore-cr-at-eol", "-M")
TIMEOUT = 60
MAX_FILES = 500  # files listed; the rest are counted in `truncated_files`
MAX_DIFF_LINES = 20_000  # a file diff with more lines than this has no content
MAX_CONTEXT_LINES = 500  # lines per «Mostrar más»
# Folded by default (shown as «generated»): lockfiles, build output and minified files.
GENERATED_NAMES = ("*.lock", "package-lock.json", "pnpm-lock.yaml", "npm-shrinkwrap.json")
GENERATED_FOLDERS = ("dist", "build")
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map")
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
STATUS_NAMES = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "C": "added"}


@dataclass(frozen=True)
class Totals:
    files: int = 0
    additions: int = 0
    deletions: int = 0


@dataclass
class Range:
    """The two commits a diff compares in one repository, run by git in `repo` (the project's
    own repository: objects and refs are shared with its worktrees, which may already be
    gone)."""

    state: ChangesState
    repo: str = ""
    old: str | None = None
    new: str | None = None
    from_ref: RefLabel | None = None
    to_ref: RefLabel | None = None
    live: bool = False
    partial: bool = False
    direct_folder: bool = False
    skipped_large: int = 0
    runs: list[ChangesRunRef] = field(default_factory=list)
    key: str = ""  # which repository (its id), to pick one range out of several
    name: str = ""
    # "commits": old → new. "staged": HEAD → index. "unstaged": index → work tree (the Git tab).
    mode: str = "commits"

    @property
    def usable(self) -> bool:
        if self.state != "ok":
            return False
        return self.mode != "commits" or bool(self.old and self.new)

    def ends(self) -> list[str]:
        """The arguments after `git diff <flags>` that pick the two sides."""
        if self.mode == "staged":
            return ["--cached"]
        if self.mode == "unstaged":
            return []
        return [self.old or "", self.new or ""]


# ---------------------------------------------------------------------- ranges
def _git_dir(db: Session, repo_id: str | None, fallback: str) -> str:
    """The folder git commands run in: the project's repository (its objects and refs are shared
    with its worktrees, which may already be gone), else the folder the snapshots were taken in."""
    repo = db.get(ProjectRepo, repo_id) if repo_id else None
    if repo is not None and Path(repo.path).is_dir():
        return repo.path
    return fallback if fallback and Path(fallback).is_dir() else ""


def _empty_state(repo: str) -> ChangesState:
    """Why a folder with no snapshots has no diff."""
    return "no_snapshots" if repo and snapshots.is_repo(repo) else "no_git"


def _state_without_rows(db: Session, project: Project | None) -> ChangesState:
    """A run or task with no repository rows: its project has repositories (so it predates the
    snapshots or lost them) or it has none."""
    if project is not None and any(not r.missing for r in repos.ensure(db, project)):
        return "no_snapshots"
    return "no_git"


LIVE_TTL = 4.0  # seconds a live snapshot is reused
_LIVE: dict[str, tuple[float, str | None]] = {}
_LIVE_LOCK = threading.Lock()


def _live_snapshot(folder: str, exclude: Sequence[str] = ()) -> str | None:
    """The folder as it is now, for a run that is going. Reused for a few seconds, so the file
    list, a file's diff and its context lines (separate requests) compare the same state and the
    5 s polling does not hash the whole folder each time."""
    with _LIVE_LOCK:
        hit = _LIVE.get(folder)
        if hit and time.monotonic() - hit[0] < LIVE_TTL:
            return hit[1]
    snapshot = snapshots.take(folder, exclude=exclude) if Path(folder).is_dir() else None
    sha = snapshot.sha if snapshot else None
    with _LIVE_LOCK:
        _LIVE[folder] = (time.monotonic(), sha)
        while len(_LIVE) > 64:
            _LIVE.pop(next(iter(_LIVE)))
    return sha


def run_totals(run: Run) -> ChangesTotals | None:
    """The +/- summary stored on a run (all its repositories); None when it has no data."""
    if run.changes_files is None:
        return None
    return ChangesTotals(
        files=run.changes_files,
        additions=run.changes_added or 0,
        deletions=run.changes_deleted or 0,
    )


def _run_rows(db: Session, run_ids: Sequence[str]) -> list[RunRepo]:
    if not run_ids:
        return []
    query = select(RunRepo).where(RunRepo.run_id.in_(run_ids)).order_by(RunRepo.path)
    return list(db.scalars(query))


def _key(row: RunRepo) -> str:
    return row.repo_id or f"row:{row.id}"


def _nested(folder: str, rows: Sequence[RunRepo]) -> list[str]:
    return runrepos.nested_in(folder, [r.path for r in rows])


def run_ranges(db: Session, run: Run) -> list[Range]:
    """One range per repository the run worked in."""
    project = db.get(Project, run.project_id) if run.project_id else None
    rows = _run_rows(db, [run.id])
    if not rows:
        state = _state_without_rows(db, project)
        # Purged with its logs (or by hand): the diff existed and is gone.
        return [Range("snapshot_missing" if state == "no_snapshots" and _had_diff(run) else state)]
    return [_run_range(db, run, row, rows) for row in rows]


def run_range(db: Session, run: Run) -> Range:
    """The first repository's range (a project with one repository has no other)."""
    return run_ranges(db, run)[0]


def _run_range(db: Session, run: Run, row: RunRepo, siblings: Sequence[RunRepo]) -> Range:
    repo = _git_dir(db, row.repo_id, row.path)
    key, name = _key(row), row.repo_name
    if not repo or not row.snapshot_start:
        state = _empty_state(repo)
        had = state == "no_snapshots" and _had_diff(run)
        return Range("snapshot_missing" if had else state, key=key, name=name)
    if not snapshots.exists(repo, row.snapshot_start):
        return Range("snapshot_missing", key=key, name=name)
    live = run.status in ACTIVE_STATUSES
    new = _live_snapshot(row.path, _nested(row.path, siblings)) if live else row.snapshot_end
    if not new:
        return Range("no_snapshots", key=key, name=name)
    if not live and not snapshots.exists(repo, new):
        return Range("snapshot_missing", key=key, name=name)
    return Range(
        "ok",
        repo,
        row.snapshot_start,
        new,
        RefLabel(kind="run_start"),
        RefLabel(kind="now" if live else "run_end"),
        live=live,
        partial=run.status == RunStatus.INTERRUPTED,
        skipped_large=row.snapshot_skipped,
        key=key,
        name=name,
    )


def _had_diff(run: Run) -> bool:
    """A run that has no snapshots now but had them: its +/- summary (or its purge) says so."""
    return run.log_purged or run.changes_files is not None


def _task_runs(db: Session, task: Task) -> list[Run]:
    return list(
        db.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.created_at, Run.id))
    )


def task_ranges(db: Session, task: Task) -> list[Range]:
    """One range per repository the task changed."""
    project = db.get(Project, task.project_id)
    runs = _task_runs(db, task)
    refs = _run_refs(db, runs)
    if project is None:
        return [Range("no_git", runs=refs)]
    rows = _run_rows(db, [r.id for r in runs])
    task_rows = list(db.scalars(select(TaskRepo).where(TaskRepo.task_id == task.id)))
    if project.workspace_mode == WorkspaceMode.WORKTREE and task_rows:
        result = [_worktree_range(db, project, tr, runs, rows) for tr in task_rows]
    else:
        result = _direct_ranges(db, project, runs, rows)
    for rng in result:
        rng.runs = refs
    return result


def task_range(db: Session, task: Task) -> Range:
    """The first repository's range (a project with one repository has no other)."""
    return task_ranges(db, task)[0]


def _worktree_range(
    db: Session, project: Project, task_repo: TaskRepo, runs: list[Run], rows: list[RunRepo]
) -> Range:
    repo_row = db.get(ProjectRepo, task_repo.repo_id)
    name = repo_row.name if repo_row else ""
    key = task_repo.repo_id
    repo = _git_dir(db, task_repo.repo_id, task_repo.worktree_path or "")
    branch = task_repo.branch
    base = (repos.base_of(project, repo_row) if repo_row else project.base_branch) or ""
    if not repo:
        return Range("no_git", key=key, name=name)
    old = task_repo.base_commit
    if not old:  # a branch whose origin was not kept: where it left the base branch
        old = git.merge_base(repo, base, branch) if base else None
    if not old or not snapshots.exists(repo, old):
        return Range(_empty_state(repo), key=key, name=name)
    mine = [r for r in rows if r.repo_id == task_repo.repo_id]
    by_run = {r.run_id: r for r in mine}
    live = next((r for r in runs if r.status in ACTIVE_STATUSES and r.id in by_run), None)
    new: str | None = None
    to_ref = RefLabel(kind="branch", name=branch)
    if live is not None:
        row = by_run[live.id]
        new, to_ref = _live_snapshot(row.path, _nested(row.path, rows)), RefLabel(kind="now")
    if new is None:
        # The end of the task's last run; if that run left none (it crashed), the branch itself,
        # never an older run's end that would pass for the whole task.
        last = by_run.get(runs[-1].id) if runs else None
        ended = last.snapshot_end if last else None
        new = ended if ended and snapshots.exists(repo, ended) else _branch_tip(repo, branch)
    if not new:
        return Range("snapshot_missing", key=key, name=name)
    return Range(
        "ok",
        repo,
        old,
        new,
        RefLabel(kind="base", name=base),
        to_ref,
        live=live is not None,
        skipped_large=max((r.snapshot_skipped for r in mine), default=0),
        key=key,
        name=name,
    )


def _direct_ranges(
    db: Session, project: Project, runs: list[Run], rows: list[RunRepo]
) -> list[Range]:
    if not rows:
        return [Range(_state_without_rows(db, project))]
    order = {run.id: index for index, run in enumerate(runs)}
    groups: dict[str, list[RunRepo]] = {}
    for row in sorted(rows, key=lambda r: order.get(r.run_id, 0)):
        groups.setdefault(_key(row), []).append(row)
    return [_direct_range(db, runs, order, group, rows) for _name, group in sorted(groups.items())]


def _direct_range(
    db: Session,
    runs: list[Run],
    order: dict[str, int],
    group: list[RunRepo],
    all_rows: list[RunRepo],
) -> Range:
    by_id = {run.id: run for run in runs}
    key, name = _key(group[0]), group[0].repo_name
    repo = _git_dir(db, group[0].repo_id, group[0].path)
    first_index = next((order[r.run_id] for r in group if r.snapshot_start), None)
    if first_index is None:
        return Range(_empty_state(repo), key=key, name=name)
    earlier = runs[:first_index]
    if any(r.started_at is not None for r in earlier):
        # Runs that did work before the first snapshot (from before the phase, or purged): where
        # the task started is unknown, so a diff from the first snapshot would look complete.
        state = "snapshot_missing" if any(_had_diff(r) for r in earlier) else "no_snapshots"
        return Range(state, key=key, name=name)
    with_start = [r for r in group if order[r.run_id] >= first_index and r.run_id in by_id]
    first, last = with_start[0], with_start[-1]
    if not repo or not snapshots.exists(repo, first.snapshot_start):
        return Range("snapshot_missing", key=key, name=name)
    last_run = by_id[last.run_id]
    live = last_run.status in ACTIVE_STATUSES
    new = _live_snapshot(last.path, _nested(last.path, all_rows)) if live else last.snapshot_end
    if not new or (not live and not snapshots.exists(repo, new)):
        return Range("no_snapshots" if not new else "snapshot_missing", key=key, name=name)
    return Range(
        "ok",
        repo,
        first.snapshot_start,
        new,
        RefLabel(kind="task_start"),
        RefLabel(kind="now" if live else "run_end"),
        live=live,
        partial=last_run.status == RunStatus.INTERRUPTED,
        direct_folder=True,
        skipped_large=max(r.snapshot_skipped for r in with_start),
        key=key,
        name=name,
    )


def _run_refs(db: Session, runs: list[Run]) -> list[ChangesRunRef]:
    stage_names = {
        stage.id: stage.name
        for stage in db.scalars(
            select(Stage).where(Stage.id.in_({r.stage_id for r in runs if r.stage_id}))
        )
    }
    seen: dict[str | None, int] = {}
    refs = []
    for run in runs:
        seen[run.stage_id] = seen.get(run.stage_id, 0) + 1
        refs.append(
            ChangesRunRef(
                id=run.id,
                stage_name=stage_names.get(run.stage_id) if run.stage_id else None,
                attempt=seen[run.stage_id],
                status=run.status,
                started_at=run.started_at,
                created_at=run.created_at,
                totals=run_totals(run),
            )
        )
    return refs


# ---------------------------------------------------------------------- ranges of the Git tab
def commit_range(repo: str, sha: str, parent: str) -> Range:
    """What one commit changed, against its first parent (the empty tree for a root commit)."""
    return Range(
        "ok",
        repo,
        parent,
        sha,
        RefLabel(kind="commit", name=parent[:7]),
        RefLabel(kind="commit", name=sha[:7]),
    )


def compare_range(repo: str, old: str, new: str, merge_base: bool = False) -> Range:
    """Two refs. With `merge_base`, what `new` changed since it left `old` (like a pull request)."""
    start = git.merge_base(repo, old, new) if merge_base else old
    if not start:
        return Range("no_snapshots")
    return Range(
        "ok", repo, start, new, RefLabel(kind="ref", name=old), RefLabel(kind="ref", name=new)
    )


def worktree_range(repo: str, staged: bool) -> Range:
    """The uncommitted changes: what is staged (HEAD → index) or not (index → work tree)."""
    return Range(
        "ok",
        repo,
        from_ref=RefLabel(kind="head" if staged else "index"),
        to_ref=RefLabel(kind="index" if staged else "worktree"),
        mode="staged" if staged else "unstaged",
    )


def _branch_tip(repo: str, branch: str) -> str | None:
    try:
        return git.run(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").strip()
    except git.GitError:
        return None


# ---------------------------------------------------------------------- file lists
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


def _statuses(output: str) -> dict[str, str]:
    """`git diff --name-status -z` as {path: status} (the new path of a rename)."""
    parts = output.split("\0")
    result: dict[str, str] = {}
    index = 0
    while index < len(parts):
        code = parts[index]
        index += 1
        if not code:
            continue
        if code[0] in "RC":
            result[parts[index + 1]] = STATUS_NAMES[code[0]]
            index += 2
        else:
            result[parts[index]] = STATUS_NAMES.get(code[0], "modified")
            index += 1
    return result


def is_generated(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    folders = path.split("/")[:-1]
    return (
        any(fnmatch.fnmatch(name, pattern) for pattern in GENERATED_NAMES)
        or name.endswith(GENERATED_SUFFIXES)
        or any(folder in GENERATED_FOLDERS for folder in folders)
    )


def _size(repo: str, commit: str, path: str) -> int | None:
    try:
        return int(git.run(repo, "cat-file", "-s", f"{commit}:{path}", timeout=10).strip())
    except (git.GitError, ValueError):
        return None


def file_list(rng: Range) -> list[FileChange]:
    old, new, repo = rng.old or "", rng.new or "", rng.repo
    ends = rng.ends()
    numstat = git.run(repo, "diff", "--numstat", "-z", *DIFF_FLAGS, *ends, timeout=TIMEOUT)
    status = _statuses(
        git.run(repo, "diff", "--name-status", "-z", *DIFF_FLAGS, *ends, timeout=TIMEOUT)
    )
    files = []
    for added, deleted, path, old_path in numstat_entries(numstat):
        binary = added is None
        change = FileChange(
            path=path,
            old_path=old_path,
            status=status.get(path, "modified"),
            additions=added or 0,
            deletions=deleted or 0,
            binary=binary,
            generated=is_generated(path),
        )
        files.append(change)
    if rng.mode == "unstaged":  # `git diff` leaves out files git does not track yet
        files += _untracked(repo)
    # One git call per size, so only for the files that are listed (the rest are only counted).
    for change in files[:MAX_FILES] if rng.mode == "commits" else []:
        if change.binary:
            if change.status != "added":
                change.old_size = _size(repo, old, change.old_path or change.path)
            if change.status != "deleted":
                change.new_size = _size(repo, new, change.path)
    return files


def changes(rng: Range) -> RepoChanges:
    """The header and the file list of one repository's range."""
    result = RepoChanges(
        key=rng.key,
        name=rng.name,
        state=rng.state,
        live=rng.live,
        partial=rng.partial,
        direct_folder=rng.direct_folder,
        from_ref=rng.from_ref,
        to_ref=rng.to_ref,
        skipped_large=rng.skipped_large,
    )
    if not rng.usable:
        return result
    try:
        files = file_list(rng)
    except git.GitError as error:  # the repository changed under us
        log.warning("could not list the changes", error=str(error))
        result.state = "snapshot_missing"
        return result
    result.totals = ChangesTotals(
        files=len(files),
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
    )
    result.truncated_files = max(0, len(files) - MAX_FILES)
    result.files = files[:MAX_FILES]
    return result


def combine(ranges: Sequence[Range]) -> Changes:
    """The changes of every repository of a run or a task."""
    parts = [changes(rng) for rng in ranges]
    usable = [p for p in parts if p.state == "ok"]
    state: ChangesState = "ok" if usable else (parts[0].state if parts else "no_git")
    return Changes(
        state=state,
        live=any(p.live for p in parts),
        partial=any(p.partial for p in parts),
        direct_folder=any(p.direct_folder for p in parts),
        totals=ChangesTotals(
            files=sum(p.totals.files for p in usable),
            additions=sum(p.totals.additions for p in usable),
            deletions=sum(p.totals.deletions for p in usable),
        ),
        repos=parts if state == "ok" else [],
        runs=ranges[0].runs if ranges else [],
    )


def run_changes(db: Session, run: Run) -> Changes:
    return combine(run_ranges(db, run))


def task_changes(db: Session, task: Task) -> Changes:
    return combine(task_ranges(db, task))


def pick(ranges: Sequence[Range], key: str | None) -> Range:
    """The repository a file request is about; the only one when `key` is not given."""
    if key:
        for rng in ranges:
            if rng.key == key:
                return rng
        raise NotFound("repo")
    if len(ranges) == 1:
        return ranges[0]
    raise ApiError(422, "repo_required", "this has several repositories: say which", "repo")


_TOTALS_CACHE: dict[tuple, ChangesTotals | None] = {}
_TOTALS_CACHE_SIZE = 256
_TOTALS_LOCK = threading.Lock()  # requests run in a thread pool


def task_totals(db: Session, task: Task) -> ChangesTotals | None:
    """The task's +/- for the Inbox, which polls it: cached until the task or one of its runs
    changes, so a poll does not run git. None: no data (or a run is still going)."""
    runs = _task_runs(db, task)
    task_rows = db.scalars(select(TaskRepo).where(TaskRepo.task_id == task.id)).all()
    key = (
        task.id,
        task.updated_at,
        tuple((row.repo_id, row.base_commit) for row in task_rows),
        tuple(
            (run.id, run.status, run.changes_files, run.changes_added, run.changes_deleted)
            for run in runs
        ),
    )
    with _TOTALS_LOCK:
        if key in _TOTALS_CACHE:
            return _TOTALS_CACHE[key]
    value = _compute_task_totals(db, task)
    with _TOTALS_LOCK:
        while len(_TOTALS_CACHE) >= _TOTALS_CACHE_SIZE:
            _TOTALS_CACHE.pop(next(iter(_TOTALS_CACHE)))
        _TOTALS_CACHE[key] = value
    return value


def _compute_task_totals(db: Session, task: Task) -> ChangesTotals | None:
    ranges = task_ranges(db, task)
    usable = [rng for rng in ranges if rng.usable]
    if not usable or any(rng.live for rng in ranges):
        return None
    total = ChangesTotals()
    for rng in usable:
        try:
            summary = totals(rng.repo, rng.old or "", rng.new or "")
        except git.GitError:
            return None
        total.files += summary.files
        total.additions += summary.additions
        total.deletions += summary.deletions
    return total


# ---------------------------------------------------------------------- file diffs
def _clean(path: str) -> str:
    """A path from a client: relative, inside the repository, with no `..` or drive."""
    normal = path.replace("\\", "/")
    parts = normal.split("/")
    if not path or "\0" in path or normal.startswith("/") or ".." in parts or ":" in parts[0]:
        raise NotFound("file")
    return path


def _is_untracked(repo: str, path: str) -> bool:
    out = git.run(
        repo,
        "ls-files",
        "-o",
        "--exclude-standard",
        "-z",
        "--",
        path,
        timeout=TIMEOUT,
    )
    return path in out.split("\0")


UNTRACKED_READ = 2 * 1024 * 1024  # bigger new files are listed without counting their lines


def _untracked(repo: str) -> list[FileChange]:
    """New files git does not track yet, as added files (their lines counted from the disk)."""
    listing = git.run(repo, "ls-files", "-o", "--exclude-standard", "-z", timeout=TIMEOUT)
    found = []
    for relative in filter(None, listing.split("\0")):
        target = Path(repo) / relative
        try:
            size = target.stat().st_size
            head = target.read_bytes()[:UNTRACKED_READ] if size <= UNTRACKED_READ else b"\0"
        except OSError:
            continue
        binary = b"\0" in head[:8000]
        lines = 0 if binary else head.count(b"\n") + (1 if head and not head.endswith(b"\n") else 0)
        found.append(
            FileChange(
                path=relative,
                status="added",
                additions=lines,
                binary=binary,
                new_size=size if binary else None,
                generated=is_generated(relative),
            )
        )
    return found


def _final_content(rng: Range, path: str) -> str:
    """The newer side of a file: a commit's, the index's or the work tree's."""
    if rng.mode == "unstaged":
        return (Path(rng.repo) / path).read_text("utf-8", errors="replace")
    if rng.mode == "staged":
        return _literal(rng, "show", f":{path}")
    return _literal(rng, "show", f"{rng.new}:{path}")


def _literal(rng: Range, *args: str) -> str:
    """git with literal pathspecs: a path from the client is never a glob or a magic pathspec."""
    return git.run(rng.repo, *args, timeout=TIMEOUT, env={"GIT_LITERAL_PATHSPECS": "1"})


def file_diff(rng: Range, path: str, old_path: str | None = None) -> FileDiff:
    """The hunks of one file. A path with no difference in the range is a 404, so the endpoint
    cannot be used to read files that did not change."""
    if not rng.usable:
        raise NotFound("changes")
    paths = [_clean(path)]
    if old_path and old_path != path:
        paths.insert(0, _clean(old_path))
    output = _literal(rng, "diff", "-U3", *DIFF_FLAGS, *rng.ends(), "--", *paths)
    if not output.strip() and rng.mode == "unstaged" and _is_untracked(rng.repo, paths[-1]):
        # A new file git does not track yet: shown as all added.
        output = Repo(rng.repo).run(
            "diff", "--no-index", "-U3", "--", "/dev/null", paths[-1], ok=(0, 1), timeout=TIMEOUT
        )
    if not output.strip():
        raise NotFound("file")
    return parse_diff(path, output)


def _split_lines(text: str) -> list[str]:
    """Lines split on newlines only: `str.splitlines` also breaks on form feeds, U+2028 and a few
    more characters that can be part of a line of code."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_diff(path: str, output: str) -> FileDiff:
    """The hunks of `git diff` for one file. Each hunk is read by the counts in its header, so a
    blank context line printed with no leading space (`diff.suppressBlankEmpty`) still counts."""
    lines = _split_lines(output)
    if len(lines) > MAX_DIFF_LINES:
        return FileDiff(path=path, too_large=True)
    hunks: list[Hunk] = []
    current: Hunk | None = None
    old_no = new_no = old_left = new_left = 0
    for line in lines:
        if current is None and (
            line.startswith("Binary files ") or line.startswith("GIT binary patch")
        ):
            return FileDiff(path=path, binary=True)
        in_hunk = current is not None and (old_left > 0 or new_left > 0)
        if line.startswith("\\"):  # "\ No newline at end of file"
            continue
        if not in_hunk:
            match = HUNK_HEADER.match(line)
            if not match:  # the file header
                continue
            old_start, old_lines, new_start, new_lines, header = match.groups()
            current = Hunk(
                old_start=int(old_start),
                old_lines=int(old_lines) if old_lines is not None else 1,
                new_start=int(new_start),
                new_lines=int(new_lines) if new_lines is not None else 1,
                header=header,
                lines=[],
            )
            hunks.append(current)
            old_no, new_no = current.old_start, current.new_start
            old_left, new_left = current.old_lines, current.new_lines
            continue
        assert current is not None
        mark, text = (line[0], line[1:]) if line else (" ", "")
        text = text.rstrip("\r")
        if mark == "+":
            current.lines.append(DiffLine(kind="add", new_no=new_no, text=text))
            new_no += 1
            new_left -= 1
        elif mark == "-":
            current.lines.append(DiffLine(kind="del", old_no=old_no, text=text))
            old_no += 1
            old_left -= 1
        else:
            current.lines.append(DiffLine(kind="context", old_no=old_no, new_no=new_no, text=text))
            old_no += 1
            new_no += 1
            old_left -= 1
            new_left -= 1
    return FileDiff(path=path, hunks=hunks)


def file_lines(rng: Range, path: str, start: int, end: int) -> FileLines:
    """Lines `start`..`end` (1-based) of the final version, as context lines. Their old numbers
    are left for the caller, who knows the offset of the hunk next to them."""
    if not rng.usable:
        raise NotFound("changes")
    path = _clean(path)
    start = max(1, start)
    end = min(end, start + MAX_CONTEXT_LINES - 1)
    changed = _literal(rng, "diff", "--name-only", *DIFF_FLAGS, *rng.ends(), "--", path)
    if not changed.strip() and not (rng.mode == "unstaged" and _is_untracked(rng.repo, path)):
        raise NotFound("file")  # only files that changed in the range can be read
    try:
        content = _final_content(rng, path)
    except (git.GitError, OSError):  # deleted in the range, or never there
        return FileLines(lines=[])
    window = _split_lines(content)[start - 1 : end]
    return FileLines(
        lines=[
            DiffLine(kind="context", new_no=start + offset, text=text.rstrip("\r"))
            for offset, text in enumerate(window)
        ]
    )
