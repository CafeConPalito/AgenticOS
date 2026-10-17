"""What the Git tab shows (phase 12)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# What stands in the way: an operation git has left half done.
Operation = Literal["merge", "rebase", "cherry-pick", "revert", "bisect"]
FileKind = Literal["changed", "renamed", "unmerged", "untracked"]


class StatusFile(BaseModel):
    path: str
    orig_path: str | None = None  # renames and copies
    # git's status letters: M modified, A added, D deleted, R renamed, C copied, T type changed,
    # U unmerged, ? untracked. In `staged` the letter is the index's, in `unstaged` the work
    # tree's.
    status: str
    kind: FileKind


class RepoStatus(BaseModel):
    repo_id: str | None = None
    branch: str | None = None  # None while detached
    head: str | None = None  # short sha; None in a repository with no commits
    detached: bool = False
    upstream: str | None = None
    ahead: int = 0  # commits the branch has that its upstream does not
    behind: int = 0
    staged: list[StatusFile] = Field(default_factory=list)
    unstaged: list[StatusFile] = Field(default_factory=list)  # modified and untracked
    conflicts: list[StatusFile] = Field(default_factory=list)
    stashes: int = 0
    operation: Operation | None = None
    last_fetch: datetime | None = None
    clean: bool = True
    empty: bool = False  # no commits yet


class CommitInfo(BaseModel):
    sha: str
    short: str
    parents: list[str]
    author: str
    email: str
    date: datetime
    subject: str
    refs: list[str] = Field(default_factory=list)  # branches and tags that point at it
    # Filled by the API from what the app knows about who made it (agents block).
    agent_name: str | None = None
    task_code: str | None = None
    run_id: str | None = None


class CommitPage(BaseModel):
    commits: list[CommitInfo]
    # More commits after these (the page was full).
    more: bool = False


class CommitDetail(CommitInfo):
    body: str = ""


class BranchInfo(BaseModel):
    name: str  # "feature/x", or "origin/main" for a remote branch
    sha: str
    short: str
    current: bool = False
    remote: bool = False
    upstream: str | None = None
    ahead: int = 0  # against its upstream
    behind: int = 0
    base_ahead: int | None = None  # against the repository's base branch
    base_behind: int | None = None
    last_commit: datetime
    subject: str = ""
    # `agentic/T-n` branches: the task they belong to.
    task_id: str | None = None
    task_code: str | None = None
    task_title: str | None = None
    task_status: str | None = None
    integrated: bool = False  # contained in the base branch


class BlameGroup(BaseModel):
    """Consecutive lines last changed by the same commit."""

    start: int  # first line (1-based) in the file
    lines: int
    sha: str
    short: str
    author: str
    date: datetime
    summary: str
    text: list[str]
    agent_name: str | None = None
    task_code: str | None = None


class RepoOverview(BaseModel):
    repo_id: str
    name: str
    path: str
    rel_path: str | None
    linked: bool
    missing: bool
    base_branch: str | None
    status: RepoStatus | None = None
    error: str | None = None


class JobState(BaseModel):
    id: str
    repo_id: str
    kind: str  # fetch | pull | push | clone | gc …
    status: Literal["running", "succeeded", "failed", "cancelled"]
    phase: str = ""  # «Receiving objects»…
    percent: int | None = None
    message: str = ""
    error_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None


class RemoteInfo(BaseModel):
    name: str
    fetch_url: str
    push_url: str


# ----------------------------------------------------------------------------- requests
class PathsBody(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=5000)


class DiscardBody(PathsBody):
    # The person saw what is lost; without it nothing is thrown away.
    confirm: bool = False


class LineBody(BaseModel):
    kind: Literal["add", "del"]
    no: int = Field(ge=1)


class ApplyBody(BaseModel):
    action: Literal["stage", "unstage", "discard"]
    path: str = Field(min_length=1, max_length=1000)
    hunks: list[tuple[int, int]] = Field(default_factory=list, max_length=2000)  # (old, new) start
    lines: list[LineBody] = Field(default_factory=list, max_length=20000)
    confirm: bool = False


class CommitBody(BaseModel):
    message: str = Field(default="", max_length=100_000)
    amend: bool = False
    no_verify: bool = False


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start: str | None = Field(default=None, max_length=200)
    switch: bool = False


class SwitchBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RenameBody(BaseModel):
    old: str = Field(min_length=1, max_length=200)
    new: str = Field(min_length=1, max_length=200)


class DeleteBranches(BaseModel):
    names: list[str] = Field(min_length=1, max_length=500)
    force: bool = False
    confirm: bool = False  # `force` loses commits no other branch has


class UpstreamBody(BaseModel):
    branch: str = Field(min_length=1, max_length=200)
    upstream: str | None = Field(default=None, max_length=200)


class FetchBody(BaseModel):
    remote: str | None = None
    prune: bool = True


class PullBody(BaseModel):
    mode: Literal["ff_only", "merge", "rebase"] | None = None  # the repository's own by default
    remote: str | None = None
    branch: str | None = None


class PushBody(BaseModel):
    remote: str | None = None
    branch: str | None = None
    set_upstream: bool = False


class BatchBody(BaseModel):
    action: Literal["fetch", "pull", "push", "switch", "create_branch", "commit"]
    repo_ids: list[str] = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=200)  # switch, create_branch
    message: str | None = Field(default=None, max_length=100_000)  # commit


class BatchItem(BaseModel):
    repo_id: str
    ok: bool
    job: JobState | None = None  # fetch, pull and push start a job
    sha: str | None = None  # commit
    error_code: str | None = None
    error: str | None = None


# ----------------------------------------------------------------------------- integration
class MergeBody(BaseModel):
    ref: str = Field(min_length=1, max_length=200)
    mode: Literal["no_ff", "ff", "squash"] = "no_ff"
    message: str | None = Field(default=None, max_length=10_000)


class RebaseBody(BaseModel):
    onto: str = Field(min_length=1, max_length=200)


class PicksBody(BaseModel):
    shas: list[str] = Field(min_length=1, max_length=200)


class ResetBody(BaseModel):
    ref: str = Field(min_length=1, max_length=200)
    mode: Literal["soft", "mixed", "hard"] = "mixed"
    confirm: bool = False  # `hard` loses uncommitted work


class TodoLine(BaseModel):
    action: Literal["pick", "reword", "squash", "fixup", "edit", "drop"]
    sha: str = Field(min_length=7, max_length=64)
    message: str | None = Field(default=None, max_length=100_000)


class InteractiveBody(BaseModel):
    base: str = Field(min_length=1, max_length=200)
    items: list[TodoLine] = Field(min_length=1, max_length=2000)


class ResolveBody(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=20_000_000)


class TakeBody(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    side: Literal["ours", "theirs"]


class OperationRead(BaseModel):
    id: str
    kind: str
    label: str
    at: datetime
    group_id: str | None = None
    undone: bool = False
    in_progress: bool = False
    # Why it cannot be undone now (None: it can).
    blocked_by: str | None = None
    lost_files: bool = False  # it threw away uncommitted files, which undoing brings back
