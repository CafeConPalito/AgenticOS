"""What a crash or a forced close leaves behind, cleaned at startup (phase 08).

`RunManager.recover` already removes the agy plugin of every run that was active. This goes
further, for what an older crash (or a failed cleanup) may have left:
- agy workspace plugins of runs that are no longer alive, in the projects' folders and in
  the tasks' worktrees (before the scheduler starts: it could write a new one there);
- worktrees of tasks already done or cancelled;
- the CLIs' folder-trust entries still pending (TrustCleaner);
- the terminal logs older than the retention.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.models import ACTIVE_STATUSES, Project, Run, Task, TaskStatus
from agentic_os.services import avatars, maintenance
from agentic_os.services.adapters.agy import RUN_MARKER, plugin_dir, remove_plugin

log = structlog.get_logger(__name__)

Release = Callable[[Session, Task, Project], None]


def stale_agy_plugins(sessions: sessionmaker[Session]) -> int:
    """Removes our agy plugins whose run is not alive. Call before the scheduler starts."""
    with sessions() as db:
        folders = {Path(p) for p in db.scalars(select(Project.path))}
        folders |= {
            Path(p)
            for p in db.scalars(select(Task.worktree_path).where(Task.worktree_path.is_not(None)))
        }
        alive = set(
            db.scalars(select(Run.id).where(Run.status.in_([s.value for s in ACTIVE_STATUSES])))
        )
    removed = 0
    for folder in folders:
        try:
            data = json.loads((plugin_dir(folder) / "plugin.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        run_id = data.get(RUN_MARKER) if isinstance(data, dict) else None
        if isinstance(run_id, str) and run_id not in alive and remove_plugin(folder, run_id):
            removed += 1
            log.info("stale_agy_plugin_removed", folder=str(folder), run_id=run_id)
    return removed


def closed_task_worktrees(sessions: sessionmaker[Session], release: Release) -> int:
    """Releases the worktrees still recorded on tasks that are done or cancelled."""
    released = 0
    with sessions() as db:
        tasks = list(
            db.scalars(
                select(Task).where(
                    Task.worktree_path.is_not(None),
                    Task.status.in_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                )
            )
        )
        for task in tasks:
            project = db.get(Project, task.project_id)
            if project is None:
                continue
            release(db, task, project)
            db.commit()
            released += task.worktree_path is None
    if released:
        log.info("closed_task_worktrees_released", count=released)
    return released


def run_at_startup(
    sessions: sessionmaker[Session],
    runs_dir: Path,
    release: Release,
    flush_trust: Callable[[], object],
) -> None:
    """The slow part (git, deleting logs): in a thread after the backend is serving."""
    steps: list[tuple[str, Callable[[], object]]] = [
        ("worktrees", lambda: closed_task_worktrees(sessions, release)),
        ("trust", flush_trust),
        ("logs", lambda: _purge_logs(sessions, runs_dir)),
        ("avatars", lambda: _unused_avatars(sessions, runs_dir.parent)),
    ]
    for name, step in steps:
        try:
            step()
        except Exception:  # one failing step must not stop the others
            log.exception("startup cleanup step failed", step=name)


def _unused_avatars(sessions: sessionmaker[Session], data_dir: Path) -> int:
    """Photos of agents and templates that no longer use them (phase 20)."""
    with sessions() as db:
        return avatars.remove_unused(db, data_dir)


def _purge_logs(sessions: sessionmaker[Session], runs_dir: Path) -> tuple[int, int]:
    with sessions() as db:
        return maintenance.purge_logs(db, runs_dir, maintenance.retention_days(db))
