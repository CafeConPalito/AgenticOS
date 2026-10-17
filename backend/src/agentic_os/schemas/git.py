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
