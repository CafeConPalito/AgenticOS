"""Reading a repository's state: status, history, branches, blame (phase 12, ADR 0017).

Everything here only reads. Output is machine-formatted (`--porcelain=v2 -z`, `%x1f`
separators), never the text git prints for people.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from agentic_os.schemas.git import (
    BlameGroup,
    BranchInfo,
    CommitDetail,
    CommitInfo,
    CommitPage,
    FileKind,
    Operation,
    RepoStatus,
    StatusFile,
)
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

FIELD = "\x1f"
RECORD = "\x1e"
# What `git log` prints per commit. %D: the refs that point at it, «HEAD -> main, origin/main».
LOG_FORMAT = f"%H{FIELD}%P{FIELD}%an{FIELD}%ae{FIELD}%at{FIELD}%s{FIELD}%D{RECORD}"
PAGE = 200
# The refs the app keeps for itself (snapshots, backups) are not history.
OWN_REFS = "refs/agentic-os/*"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _when(seconds: str | int) -> datetime:
    return datetime.fromtimestamp(int(seconds), UTC)


# ------------------------------------------------------------------------------- status
def git_dir(repo: Repo) -> Path:
    raw = repo.run("rev-parse", "--git-dir", timeout=10).strip()
    path = Path(raw)
    return path if path.is_absolute() else Path(repo.path) / path


def git_common(repo: Repo) -> Path:
    """The repository's shared git folder (the same for it and all its worktrees)."""
    raw = repo.run("rev-parse", "--git-common-dir", timeout=10).strip()
    path = Path(raw)
    return path if path.is_absolute() else Path(repo.path) / path


def operation_in_progress(repo: Repo) -> Operation | None:
    folder = git_dir(repo)
    for marker, name in (
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("MERGE_HEAD", "merge"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
        ("BISECT_LOG", "bisect"),
    ):
        if (folder / marker).exists():
            return name  # type: ignore[return-value]
    return None


def last_fetch(repo: Repo) -> datetime | None:
    try:
        return datetime.fromtimestamp((git_common(repo) / "FETCH_HEAD").stat().st_mtime, UTC)
    except OSError:
        return None


def status(repo: Repo, repo_id: str | None = None) -> RepoStatus:
    out = repo.run("status", "--porcelain=v2", "-z", "--branch", "--show-stash", "-uall")
    result = RepoStatus(repo_id=repo_id)
    head_name = ""
    tokens = out.split("\0")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if token.startswith("# "):
            key, _, value = token[2:].partition(" ")
            if key == "branch.oid":
                result.empty = value == "(initial)"
                result.head = None if result.empty else value[:7]
            elif key == "branch.head":
                head_name = value
            elif key == "branch.upstream":
                result.upstream = value
            elif key == "branch.ab":
                ahead, behind = value.split()
                result.ahead, result.behind = int(ahead[1:]), int(behind[1:])
            elif key == "stash":
                result.stashes = int(value)
            continue
        kind = token[0]
        if kind == "?":
            result.unstaged.append(StatusFile(path=token[2:], status="?", kind="untracked"))
        elif kind == "1":
            fields = token.split(" ", 8)
            _add(result, fields[1], fields[8], None, "changed")
        elif kind == "2":
            fields = token.split(" ", 9)
            original = tokens[index]
            index += 1
            _add(result, fields[1], fields[9], original, "renamed")
        elif kind == "u":
            fields = token.split(" ", 10)
            result.conflicts.append(
                StatusFile(
                    path=fields[10], status=fields[1].replace(".", "") or "U", kind="unmerged"
                )
            )
    result.detached = head_name == "(detached)"
    result.branch = None if result.detached or not head_name else head_name
    result.operation = operation_in_progress(repo)
    result.last_fetch = last_fetch(repo)
    result.clean = not (result.staged or result.unstaged or result.conflicts)
    return result


def _add(result: RepoStatus, xy: str, path: str, original: str | None, kind: FileKind) -> None:
    staged, worktree = xy[0], xy[1]
    if staged != ".":
        result.staged.append(StatusFile(path=path, orig_path=original, status=staged, kind=kind))
    if worktree != ".":
        result.unstaged.append(
            StatusFile(path=path, orig_path=original, status=worktree, kind=kind)
        )


# ------------------------------------------------------------------------------- history
def _commit(record: str) -> CommitInfo:
    sha, parents, author, email, at, subject, refs = record.split(FIELD)
    return CommitInfo(
        sha=sha,
        short=sha[:7],
        parents=parents.split(),
        author=author,
        email=email,
        date=_when(at),
        subject=subject,
        refs=[r.strip() for r in refs.split(",") if r.strip()],
    )


def _commits(output: str) -> list[CommitInfo]:
    return [_commit(rec.strip("\n")) for rec in output.split(RECORD) if rec.strip("\n")]


def log(
    repo: Repo,
    *,
    skip: int = 0,
    limit: int = PAGE,
    ref: str | None = None,
    all_refs: bool = False,
    author: str | None = None,
    grep: str | None = None,
    search: str | None = None,
    path: str | None = None,
    follow: bool = False,
) -> CommitPage:
    """A page of the history, newest first, in topological order (what a graph needs).
    `all_refs`: every branch and tag, not just `ref` (the current branch by default)."""
    args = ["log", "--topo-order", f"--skip={skip}", f"-n{limit + 1}", f"--format={LOG_FORMAT}"]
    if author:
        args += [f"--author={author}", "-i"]
    if grep:
        args += [f"--grep={grep}", "-i"]
    if search:
        args.append(f"-S{search}")
    if follow and path:
        args.append("--follow")
    if all_refs:
        args += [f"--exclude={OWN_REFS}", "--branches", "--tags", "--remotes", "HEAD"]
    else:
        args.append(ref or "HEAD")
    if path:
        args += ["--", path]
    try:
        out = repo.run(*args, literal=True)
    except GitxError as error:
        # A repository with no commits yet has no history, which is not an error.
        if error.code == "unknown_ref" or "does not have any commits" in error.output:
            return CommitPage(commits=[])
        raise
    commits = _commits(out)
    return CommitPage(commits=commits[:limit], more=len(commits) > limit)


def commit_detail(repo: Repo, sha: str) -> CommitDetail:
    out = repo.run("show", "-s", f"--format={LOG_FORMAT}%B", sha)
    head, _, message = out.partition(RECORD)
    info = _commit(head)
    _subject, _, body = message.strip().partition("\n")  # %B repeats the subject
    return CommitDetail(**info.model_dump(), body=body.strip())


def parent_or_empty(commit: CommitInfo | CommitDetail) -> str:
    """What a commit's diff starts from: its first parent (the empty tree for a root commit)."""
    return commit.parents[0] if commit.parents else EMPTY_TREE


# ------------------------------------------------------------------------------- branches
TRACK = re.compile(r"ahead (\d+)|behind (\d+)")


def branches(repo: Repo, base: str | None = None) -> list[BranchInfo]:
    """Local and remote branches, with how far each is from its upstream and from `base`."""
    use_base = bool(base) and repo.attempt("rev-parse", "--verify", "-q", base or "") is not None
    fields = [
        "%(HEAD)",
        "%(refname)",
        "%(objectname)",
        "%(upstream:short)",
        "%(upstream:track,nobracket)",
        "%(committerdate:iso-strict)",
        "%(subject)",
    ]
    if use_base:
        fields.append(f"%(ahead-behind:{base})")
    out = repo.run(
        "for-each-ref",
        f"--format={FIELD.join(fields)}{RECORD}",
        "refs/heads",
        "refs/remotes",
        timeout=30,
    )
    result: list[BranchInfo] = []
    for record in out.split(RECORD):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(FIELD)
        head, refname, sha, upstream, track, date, subject = parts[:7]
        remote = refname.startswith("refs/remotes/")
        name = refname.removeprefix("refs/remotes/" if remote else "refs/heads/")
        if remote and name.endswith("/HEAD"):
            continue
        ahead = behind = 0
        for match in TRACK.finditer(track):
            if match.group(1):
                ahead = int(match.group(1))
            if match.group(2):
                behind = int(match.group(2))
        base_ahead = base_behind = None
        if use_base and len(parts) > 7 and parts[7].strip():
            base_ahead, base_behind = (int(x) for x in parts[7].split())
        result.append(
            BranchInfo(
                name=name,
                sha=sha,
                short=sha[:7],
                current=head == "*",
                remote=remote,
                upstream=upstream or None,
                ahead=ahead,
                behind=behind,
                base_ahead=base_ahead,
                base_behind=base_behind,
                last_commit=datetime.fromisoformat(date),
                subject=subject,
                integrated=base_ahead == 0 and not remote if base_ahead is not None else False,
            )
        )
    return sorted(result, key=lambda b: (b.remote, not b.current, b.name.lower()))


# ------------------------------------------------------------------------------- blame
def blame(repo: Repo, path: str, rev: str | None = None) -> list[BlameGroup]:
    """Who last changed each line of a file, in groups of consecutive lines."""
    args = ["blame", "--porcelain"]
    if rev:
        args.append(rev)
    out = repo.run(*args, "--", path, literal=True, timeout=120)
    meta: dict[str, dict[str, str]] = {}
    current = ""
    lines: list[tuple[int, str, str]] = []  # (line number, sha, text)
    final_line = 0
    for line in out.split("\n"):
        if line.startswith("\t"):
            lines.append((final_line, current, line[1:].rstrip("\r")))
            continue
        head = line.split(" ")
        if len(head[0]) == 40 and all(c in "0123456789abcdef" for c in head[0]) and len(head) >= 3:
            current, final_line = head[0], int(head[2])
            meta.setdefault(current, {})
        elif current and " " in line:
            key, _, value = line.partition(" ")
            meta[current].setdefault(key, value)
    groups: list[BlameGroup] = []
    for number, sha, text in lines:
        if groups and groups[-1].sha == sha and groups[-1].start + groups[-1].lines == number:
            groups[-1].lines += 1
            groups[-1].text.append(text)
            continue
        info = meta.get(sha, {})
        groups.append(
            BlameGroup(
                start=number,
                lines=1,
                sha=sha,
                short=sha[:7],
                author=info.get("author", ""),
                date=_when(info.get("author-time", "0")),
                summary=info.get("summary", ""),
                text=[text],
            )
        )
    return groups
