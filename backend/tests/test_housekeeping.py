"""Leftovers of earlier crashes, cleaned at startup (phase 08)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session
from test_scheduler import db_factory, make_agent  # noqa: F401 - pytest fixture

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Project, Run, RunStatus, Task, TaskStatus
from agentic_os.services import housekeeping
from agentic_os.services import tasks as task_ops
from agentic_os.services.adapters.agy import RUN_MARKER, plugin_dir


def project_in(db: Session, folder: Path) -> Project:
    folder.mkdir(parents=True, exist_ok=True)
    project = Project(
        workspace_id=DEFAULT_WORKSPACE, name=folder.name, path=str(folder), path_key=str(folder)
    )
    db.add(project)
    db.flush()
    return project


def plugin(folder: Path, run_id: str) -> Path:
    path = plugin_dir(folder)
    path.mkdir(parents=True)
    (path / "plugin.json").write_text(json.dumps({"name": "agentic-os", RUN_MARKER: run_id}))
    return path


def run(db: Session, run_id: str, status: RunStatus) -> None:
    db.add(
        Run(
            id=run_id,
            workspace_id=DEFAULT_WORKSPACE,
            agent_name="Dev",
            agent_color="#fff",
            project_name="p",
            cli="agy",
            prompt="x",
            cwd=".",
            status=status,
        )
    )


def test_stale_agy_plugins_go_and_live_ones_stay(db_factory, tmp_path: Path):  # noqa: F811
    with db_factory() as db:
        dead = project_in(db, tmp_path / "dead")
        live = project_in(db, tmp_path / "live")
        run(db, "old", RunStatus.INTERRUPTED)
        run(db, "now", RunStatus.RUNNING)
        db.commit()
    stale = plugin(Path(dead.path), "old")
    current = plugin(Path(live.path), "now")

    assert housekeeping.stale_agy_plugins(db_factory) == 1

    assert not stale.exists() and not (Path(dead.path) / ".agents").exists()
    assert current.exists()


def test_the_worktrees_of_closed_tasks_are_released(db_factory, tmp_path: Path):  # noqa: F811
    with db_factory() as db:
        project = project_in(db, tmp_path / "web")
        agent = make_agent(db)
        done = task_ops.create_task(db, project, "hecha", agent_id=agent.id)
        open_task = task_ops.create_task(db, project, "abierta", agent_id=agent.id)
        done.status, done.worktree_path = TaskStatus.DONE, str(tmp_path / "wt" / "T-1")
        open_task.status, open_task.worktree_path = TaskStatus.RUNNING, str(tmp_path / "wt" / "T-2")
        db.commit()
    released: list[str] = []

    def release(db: Session, task: Task, project: Project) -> None:
        released.append(task.code)
        task.worktree_path = None

    assert housekeeping.closed_task_worktrees(db_factory, release) == 1
    assert released == ["T-1"]


def test_a_failing_step_does_not_stop_the_others(db_factory, tmp_path: Path):  # noqa: F811
    calls: list[str] = []

    def broken_release(db, task, project):
        raise AssertionError("not called: no closed task has a worktree")

    def broken_trust():
        calls.append("trust")
        raise OSError("locked")

    housekeeping.run_at_startup(db_factory, tmp_path / "runs", broken_release, broken_trust)
    assert calls == ["trust"]  # and the log purge still ran (nothing to purge)
