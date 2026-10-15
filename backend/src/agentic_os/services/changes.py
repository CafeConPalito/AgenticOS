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
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import NotFound
from agentic_os.models import ACTIVE_STATUSES, Project, Run, RunStatus, Stage, Task, WorkspaceMode
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
)
from agentic_os.services import git, snapshots

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
    """The two commits a diff compares, run by git in `repo` (the project's own repository:
    objects and refs are shared with its worktrees, which may already be gone)."""

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

    @property
    def usable(self) -> bool:
        return self.state == "ok" and bool(self.old and self.new)


# ---------------------------------------------------------------------- ranges
def _repo_of(project: Project | None, fallback: str) -> str:
    if project is not None and Path(project.path).is_dir():
        return project.path
    return fallback if Path(fallback).is_dir() else ""


def _empty_state(repo: str) -> ChangesState:
    """Why a folder with no snapshots has no diff."""
    return "no_snapshots" if repo and snapshots.is_repo(repo) else "no_git"


def run_range(db: Session, run: Run) -> Range:
    project = db.get(Project, run.project_id) if run.project_id else None
    repo = _repo_of(project, run.cwd)
    if not repo or not run.snapshot_start:
        state = _empty_state(repo)
        # Purged with its logs (or by hand): the diff existed and is gone.
        return Range("snapshot_missing" if state == "no_snapshots" and _had_diff(run) else state)
    if not snapshots.exists(repo, run.snapshot_start):
        return Range("snapshot_missing")
    live = run.status in ACTIVE_STATUSES
    if live:
        end = snapshots.take(run.cwd) if Path(run.cwd).is_dir() else None
        new = end.sha if end else None
    else:
        new = run.snapshot_end
    if not new:
        return Range("no_snapshots")
    if not live and not snapshots.exists(repo, new):
        return Range("snapshot_missing")
    return Range(
        "ok",
        repo,
        run.snapshot_start,
        new,
        RefLabel(kind="run_start"),
        RefLabel(kind="now" if live else "run_end"),
        live=live,
        partial=run.status == RunStatus.INTERRUPTED,
        skipped_large=run.snapshot_skipped,
    )


def _had_diff(run: Run) -> bool:
    """A run that has no snapshots now but had them: its +/- summary (or its purge) says so."""
    return run.log_purged or run.changes_files is not None


def _task_runs(db: Session, task: Task) -> list[Run]:
    return list(
        db.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.created_at, Run.id))
    )


def task_range(db: Session, task: Task) -> Range:
    project = db.get(Project, task.project_id)
    if project is None:
        return Range("no_git")
    repo = _repo_of(project, task.worktree_path or "")
    runs = _task_runs(db, task)
    refs = _run_refs(db, runs)
    if not repo:
        return Range("no_git", runs=refs)
    if project.workspace_mode == WorkspaceMode.WORKTREE and task.branch:
        result = _worktree_range(task, project, repo, runs)
    else:
        result = _direct_range(repo, runs)
    result.runs = refs
    return result


def _worktree_range(task: Task, project: Project, repo: str, runs: list[Run]) -> Range:
    branch = task.branch or ""
    old = task.base_commit
    if not old:  # a task from before the phase: where its branch left the base branch
        base = project.base_branch or ""
        old = _merge_base(repo, base, branch) if base else None
    if not old or not snapshots.exists(repo, old):
        return Range(_empty_state(repo))
    live = next((r for r in runs if r.status in ACTIVE_STATUSES), None)
    new: str | None = None
    to_ref = RefLabel(kind="branch", name=branch)
    if live is not None and Path(live.cwd).is_dir():
        snap = snapshots.take(live.cwd)
        new, to_ref = (snap.sha if snap else None), RefLabel(kind="now")
    if new is None:
        ended = next((r.snapshot_end for r in reversed(runs) if r.snapshot_end), None)
        new = ended if ended and snapshots.exists(repo, ended) else _branch_tip(repo, branch)
    if not new:
        return Range("snapshot_missing")
    skipped = max((r.snapshot_skipped for r in runs), default=0)
    return Range(
        "ok",
        repo,
        old,
        new,
        RefLabel(kind="base", name=project.base_branch or ""),
        to_ref,
        live=live is not None,
        skipped_large=skipped,
    )


def _direct_range(repo: str, runs: list[Run]) -> Range:
    first_index = next((i for i, r in enumerate(runs) if r.snapshot_start), None)
    if first_index is None:
        return Range(_empty_state(repo))
    earlier = runs[:first_index]
    if any(r.started_at is not None for r in earlier):
        # Runs that did work before the first snapshot (from before the phase, or purged): where
        # the task started is unknown, so a diff from the first snapshot would look complete.
        return Range("snapshot_missing" if any(_had_diff(r) for r in earlier) else "no_snapshots")
    with_start = runs[first_index:]
    first, last = with_start[0], with_start[-1]
    if not snapshots.exists(repo, first.snapshot_start):
        return Range("snapshot_missing")
    live = last.status in ACTIVE_STATUSES
    if live:
        snap = snapshots.take(last.cwd) if Path(last.cwd).is_dir() else None
        new = snap.sha if snap else None
    else:
        new = last.snapshot_end
    if not new or (not live and not snapshots.exists(repo, new)):
        return Range("no_snapshots" if not new else "snapshot_missing")
    return Range(
        "ok",
        repo,
        first.snapshot_start,
        new,
        RefLabel(kind="task_start"),
        RefLabel(kind="now" if live else "run_end"),
        live=live,
        partial=last.status == RunStatus.INTERRUPTED,
        direct_folder=True,
        skipped_large=max(r.snapshot_skipped for r in with_start),
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
        has_data = run.changes_files is not None
        refs.append(
            ChangesRunRef(
                id=run.id,
                stage_name=stage_names.get(run.stage_id) if run.stage_id else None,
                attempt=seen[run.stage_id],
                status=run.status,
                started_at=run.started_at,
                created_at=run.created_at,
                totals=ChangesTotals(
                    files=run.changes_files or 0,
                    additions=run.changes_added or 0,
                    deletions=run.changes_deleted or 0,
                )
                if has_data
                else None,
            )
        )
    return refs


def _merge_base(repo: str, base: str, branch: str) -> str | None:
    try:
        return git.run(repo, "merge-base", base, branch, timeout=10).strip() or None
    except git.GitError:
        return None


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
    numstat = git.run(repo, "diff", "--numstat", "-z", *DIFF_FLAGS, old, new, timeout=TIMEOUT)
    status = _statuses(
        git.run(repo, "diff", "--name-status", "-z", *DIFF_FLAGS, old, new, timeout=TIMEOUT)
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
    for change in files:
        if change.binary:  # a handful at most: one call each
            if change.status != "added":
                change.old_size = _size(repo, old, change.old_path or change.path)
            if change.status != "deleted":
                change.new_size = _size(repo, new, change.path)
    return files


def changes(rng: Range) -> Changes:
    """The header and the file list of a range."""
    result = Changes(
        state=rng.state,
        live=rng.live,
        partial=rng.partial,
        direct_folder=rng.direct_folder,
        from_ref=rng.from_ref,
        to_ref=rng.to_ref,
        skipped_large=rng.skipped_large,
        runs=rng.runs,
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


_TOTALS_CACHE: dict[tuple, ChangesTotals | None] = {}
_TOTALS_CACHE_SIZE = 256


def task_totals(db: Session, task: Task) -> ChangesTotals | None:
    """The task's +/- for the Inbox, which polls it: cached until the task or one of its runs
    changes, so a poll does not run git. None: no data (or a run is still going)."""
    runs = _task_runs(db, task)
    key = (
        task.id,
        task.updated_at,
        task.base_commit,
        tuple((run.id, run.status, run.snapshot_end) for run in runs),
    )
    if key not in _TOTALS_CACHE:
        if len(_TOTALS_CACHE) >= _TOTALS_CACHE_SIZE:
            _TOTALS_CACHE.pop(next(iter(_TOTALS_CACHE)))
        _TOTALS_CACHE[key] = _compute_task_totals(db, task)
    return _TOTALS_CACHE[key]


def _compute_task_totals(db: Session, task: Task) -> ChangesTotals | None:
    rng = task_range(db, task)
    if not rng.usable or rng.live:
        return None
    try:
        summary = totals(rng.repo, rng.old or "", rng.new or "")
    except git.GitError:
        return None
    return ChangesTotals(
        files=summary.files, additions=summary.additions, deletions=summary.deletions
    )


# ---------------------------------------------------------------------- file diffs
def _clean(path: str) -> str:
    """A path from a client: relative, inside the repository, with no `..` or drive."""
    normal = path.replace("\\", "/")
    parts = normal.split("/")
    if not path or "\0" in path or normal.startswith("/") or ".." in parts or ":" in parts[0]:
        raise NotFound("file")
    return path


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
    output = _literal(rng, "diff", "-U3", *DIFF_FLAGS, rng.old or "", rng.new or "", "--", *paths)
    if not output.strip():
        raise NotFound("file")
    return parse_diff(path, output)


def parse_diff(path: str, output: str) -> FileDiff:
    lines = output.splitlines()
    if len(lines) > MAX_DIFF_LINES:
        return FileDiff(path=path, too_large=True)
    hunks: list[Hunk] = []
    current: Hunk | None = None
    old_no = new_no = 0
    for line in lines:
        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            return FileDiff(path=path, binary=True)
        match = HUNK_HEADER.match(line)
        if match:
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
            continue
        if current is None or not line:  # the file header; an empty line is not a diff line
            continue
        mark, text = line[0], line[1:].rstrip("\r")
        if mark == "+":
            current.lines.append(DiffLine(kind="add", new_no=new_no, text=text))
            new_no += 1
        elif mark == "-":
            current.lines.append(DiffLine(kind="del", old_no=old_no, text=text))
            old_no += 1
        elif mark == " ":
            current.lines.append(DiffLine(kind="context", old_no=old_no, new_no=new_no, text=text))
            old_no += 1
            new_no += 1
        # "\ No newline at end of file" is dropped
    return FileDiff(path=path, hunks=hunks)


def file_lines(rng: Range, path: str, start: int, end: int) -> FileLines:
    """Lines `start`..`end` (1-based) of the final version, as context lines. Their old numbers
    are left for the caller, who knows the offset of the hunk next to them."""
    if not rng.usable:
        raise NotFound("changes")
    path = _clean(path)
    start = max(1, start)
    end = min(end, start + MAX_CONTEXT_LINES - 1)
    changed = _literal(
        rng, "diff", "--name-only", *DIFF_FLAGS, rng.old or "", rng.new or "", "--", path
    )
    if not changed.strip():  # only files that changed in the range can be read
        raise NotFound("file")
    try:
        content = _literal(rng, "show", f"{rng.new}:{path}")
    except git.GitError:  # deleted in the range, or never there
        return FileLines(lines=[])
    window = content.splitlines()[start - 1 : end]
    return FileLines(
        lines=[
            DiffLine(kind="context", new_no=start + offset, text=text.rstrip("\r"))
            for offset, text in enumerate(window)
        ]
    )
