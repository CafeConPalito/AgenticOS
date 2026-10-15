from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Why there is no diff: the folder has no git, the run is from before the phase (or its snapshot
# failed), or the snapshot's commit is gone (repository deleted or cloned again, refs purged).
ChangesState = Literal["ok", "no_git", "no_snapshots", "snapshot_missing"]
FileStatus = Literal["added", "modified", "deleted", "renamed"]
# What one end of the comparison is. The UI writes the sentence («rama base `main`», «inicio de
# la ejecución»…): `base` and `branch` carry a branch name.
RefKind = Literal["base", "branch", "run_start", "run_end", "task_start", "now"]


class RefLabel(BaseModel):
    kind: RefKind
    name: str = ""


class ChangesTotals(BaseModel):
    files: int = 0
    additions: int = 0
    deletions: int = 0


class FileChange(BaseModel):
    path: str
    old_path: str | None = None  # renames only
    status: FileStatus
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    old_size: int | None = None  # binary files only, in bytes
    new_size: int | None = None
    generated: bool = False  # lockfiles, dist/, minified: shown folded


class ChangesRunRef(BaseModel):
    """One run of a task, for the selector of its «Cambios» section."""

    id: str
    stage_name: str | None
    attempt: int  # 1 = the first run of that stage
    status: str
    started_at: datetime | None
    created_at: datetime
    totals: ChangesTotals | None  # None: no data for that run


class Changes(BaseModel):
    state: ChangesState
    live: bool = False  # the run is still going: the end is the folder right now
    partial: bool = False  # taken when the app reopened: may include later changes
    direct_folder: bool = False  # the folder is the user's too: everything that changed shows
    from_ref: RefLabel | None = None
    to_ref: RefLabel | None = None
    totals: ChangesTotals = Field(default_factory=ChangesTotals)
    files: list[FileChange] = Field(default_factory=list)
    truncated_files: int = 0  # files over the list limit that are not in `files`
    skipped_large: int = 0  # new files too big to be in the snapshots
    runs: list[ChangesRunRef] = Field(default_factory=list)  # tasks only


class DiffLine(BaseModel):
    kind: Literal["context", "add", "del"]
    old_no: int | None = None
    new_no: int | None = None
    text: str


class Hunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str = ""  # what git prints after the @@ (the enclosing function)
    lines: list[DiffLine]


class FileDiff(BaseModel):
    path: str
    hunks: list[Hunk] = Field(default_factory=list)
    binary: bool = False
    too_large: bool = False  # more lines than the limit: no content


class FileLines(BaseModel):
    """Lines of the final version of a file, to widen the context between hunks."""

    lines: list[DiffLine]


class AgentChangeRun(BaseModel):
    """A run of an agent that changed code, for the agent's «Cambios» tab."""

    run_id: str
    project_id: str | None
    project_name: str
    task_id: str | None
    task_code: str | None
    task_title: str | None
    started_at: datetime | None
    created_at: datetime
    totals: ChangesTotals
