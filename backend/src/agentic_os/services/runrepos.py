"""Where each repository of a project is for one run (phase 12, ADR 0016).

A run of a worktree task sees every repository of the task at its worktree; any other run (a
manual one, or a task in a direct folder) sees the project's repositories where they are on
disk. Linked repositories outside the run's folder are handed to the CLI as extra directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import Project, ProjectRepo, Task, TaskRepo
from agentic_os.services import repos


@dataclass(frozen=True)
class RunTarget:
    repo_id: str
    name: str
    folder: str  # where this repository is for the run
    branch: str | None  # the task's branch here (worktree tasks)
    base: str | None


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def is_within(folder: str, root: str) -> bool:
    folder_key, root_key = _key(folder), _key(root)
    return folder_key == root_key or folder_key.startswith(root_key.rstrip("\\/") + os.sep)


def targets_for(db: Session, project: Project | None, task: Task | None) -> list[RunTarget]:
    """The repositories a run works with, first the one at the run's folder (if any)."""
    if project is None:
        return []
    if task is not None:
        rows = db.scalars(
            select(TaskRepo).where(TaskRepo.task_id == task.id, TaskRepo.worktree_path.is_not(None))
        ).all()
        found = [(row, db.get(ProjectRepo, row.repo_id)) for row in rows]
        worktrees = [
            RunTarget(
                repo.id,
                repo.name,
                row.worktree_path or "",
                row.branch,
                repos.base_of(project, repo),
            )
            for row, repo in found
            if repo is not None
        ]
        if worktrees:
            return sorted(worktrees, key=lambda t: (len(Path(t.folder).parts), t.folder))
    return [
        RunTarget(r.id, r.name, r.path, None, repos.base_of(project, r))
        for r in repos.ensure(db, project)
        if not r.missing
    ]


def extra_dirs(targets: list[RunTarget], cwd: str) -> tuple[str, ...]:
    """Repositories that live outside the run's folder: the CLI must be told about them."""
    return tuple(t.folder for t in targets if not is_within(t.folder, cwd))


def nested_in(folder: str, others: list[str]) -> list[str]:
    """Paths (relative to `folder`, POSIX) of the other repository folders that sit inside it:
    its snapshots must leave them out, or git would take them for submodules."""
    base = Path(folder)
    found: list[str] = []
    for other in others:
        if _key(other) == _key(folder) or not is_within(other, folder):
            continue
        found.append(Path(os.path.abspath(other)).relative_to(os.path.abspath(base)).as_posix())
    return sorted(found)
