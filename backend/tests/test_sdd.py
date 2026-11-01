"""SDD working mode (phase 24, block 5; CA5, ADR 0030): the project's SDD format is detected,
the requirements stage marks the mode with `set_work_mode`, every stage gets it in its context,
the spec folder must exist before the first stage ends, and the person can change the mode."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from live_server import LiveServer, live_server
from sqlalchemy import select
from test_lanes import (  # noqa: F401 - fixtures
    db_factory,
    finish_stage,
    launcher,
    new_task,
    scheduler,
    setup_split,
    task_row,
)
from test_mcp_server import call, mcp_url, seed_run

from agentic_os.api.tasks import read_task
from agentic_os.config import Settings
from agentic_os.errors import ApiError
from agentic_os.models import Project, Run, Task, TaskEvent, TaskEventKind, TaskStatus
from agentic_os.services import context, sdd
from agentic_os.services import tasks as task_ops


# ------------------------------------------------------------------------------ detection
@pytest.mark.parametrize(
    ("files", "name"),
    [
        ([".specify/memory/constitution.md", "specs/001-login/spec.md"], "spec-kit"),
        ([".kiro/specs/login/requirements.md"], "Kiro"),
        (["openspec/specs/auth/spec.md"], "OpenSpec"),
        (["docs/phases/01-login/spec.md"], "specs por fase"),
        (["specs/login/spec.md"], "specs"),
    ],
)
def test_the_projects_sdd_format_is_detected(tmp_path: Path, files: list[str], name: str):
    for file in files:
        (tmp_path / file).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / file).write_text("# spec\n", encoding="utf-8")
    found = sdd.detect(tmp_path)
    assert found is not None and found.name == name
    assert name in sdd.describe(found)


def test_a_project_without_sdd_is_told_the_apps_format(tmp_path: Path):
    (tmp_path / "src").mkdir()
    assert sdd.detect(tmp_path) is None
    assert sdd.detect(tmp_path / "missing") is None
    assert "specs/NNN-nombre/" in sdd.describe(None)


# ------------------------------------------------------------------------- the mode itself
def _task(db_factory, number: int = 1) -> Task:
    with db_factory() as db:
        task = db.scalar(select(Task).where(Task.number == number, Task.lane_key == ""))
        db.expunge(task)
        return task


def test_the_requirements_stage_marks_the_mode_on_the_root_task(db_factory, scheduler, launcher):
    setup_split(db_factory)
    new_task(db_factory)
    scheduler.step()
    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        assert task_ops.set_work_mode(db, task, "quizás", "") is not None
        assert "spec_path" in task_ops.set_work_mode(db, task, "sdd", "grande", "")
        assert task_ops.set_work_mode(db, task, "sdd", "grande", "../fuera") is not None
        assert task_ops.set_work_mode(db, task, "sdd", "grande", "C:/specs/x") is not None
        assert (
            task_ops.set_work_mode(db, task, "sdd", "Toca tres capas", "specs\\001-filtro\\")
            is None
        )
        db.commit()
    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        assert (task.work_mode, task.spec_path) == ("sdd", "specs/001-filtro")
        assert task.work_mode_reason == "Toca tres capas"
        detail = db.scalar(
            select(TaskEvent.detail).where(TaskEvent.kind == TaskEventKind.WORK_MODE)
        )
        assert detail == "con SDD (specs/001-filtro): Toca tres capas"
        shown = read_task(db, task)
        assert (shown.work_mode, shown.spec_path) == ("sdd", "specs/001-filtro")


def test_each_stage_gets_the_mode_in_its_context_and_lanes_read_their_roots(
    db_factory, scheduler, launcher, tmp_path: Path
):
    setup_split(db_factory, conditions=False)  # both branches always taken
    with db_factory() as db:  # a project folder with spec-kit
        project = db.scalar(select(Project))
        project.path = str(tmp_path)
        db.commit()
    (tmp_path / ".specify").mkdir()
    new_task(db_factory)
    scheduler.step()
    with db_factory() as db:
        first = task_ops.task_context(db, db.get(Task, _task(db_factory).id))
    text = context.task_section(first)
    assert "## Modo de trabajo: sin decidir" in text and "spec-kit" in text
    assert "set_work_mode" in text

    with db_factory() as db:
        task_ops.set_work_mode(
            db, db.get(Task, _task(db_factory).id), "sdd", "grande", "specs/001-x"
        )
        db.commit()
    (tmp_path / "specs" / "001-x").mkdir(parents=True)
    finish_stage(db_factory, scheduler, launcher, "T-1")
    lane = task_row(db_factory, key="backend")
    with db_factory() as db:
        lane_context = task_ops.task_context(db, db.get(Task, lane.id))
        shown = read_task(db, db.get(Task, lane.id))
    lane_text = context.task_section(lane_context)
    assert "## Modo de trabajo: con SDD" in lane_text and "`specs/001-x`" in lane_text
    assert "sin decidir" not in lane_text  # the hint is only for the first stage
    assert shown.work_mode == "sdd"  # a lane shows its root's mode


def test_a_direct_task_is_told_not_to_write_specs(db_factory, scheduler, launcher):
    setup_split(db_factory)
    new_task(db_factory)
    scheduler.step()
    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        task_ops.set_work_mode(db, task, "direct", "Es una errata")
        text = context.task_section(task_ops.task_context(db, task))
    assert "## Modo de trabajo: sin SDD" in text and "no crees documentos de spec" in text


def test_the_first_stage_cannot_end_without_its_spec_folder(
    db_factory, scheduler, launcher, tmp_path: Path
):
    setup_split(db_factory)
    with db_factory() as db:
        db.scalar(select(Project)).path = str(tmp_path)
        db.commit()
    new_task(db_factory)
    scheduler.step()
    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        task_ops.set_work_mode(db, task, "sdd", "grande", "specs/001-filtro")
        problem = task_ops.spec_problem(db, task)
        assert problem is not None and "specs/001-filtro" in problem
        (tmp_path / "specs" / "001-filtro").mkdir(parents=True)
        assert task_ops.spec_problem(db, task) is None


def test_the_person_changes_the_mode_and_the_requirements_start_again(
    db_factory, scheduler, launcher
):
    ids, _ = setup_split(db_factory, review=("Requisitos",))
    new_task(db_factory)
    scheduler.step()
    with db_factory() as db:
        task_ops.set_work_mode(db, db.get(Task, _task(db_factory).id), "sdd", "grande", "specs/1-x")
        db.commit()
    finish_stage(db_factory, scheduler, launcher, "T-1")  # waits in the requirements review
    assert _task(db_factory).status == TaskStatus.REVIEW

    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        task_ops.change_work_mode(db, task, "direct")
        db.commit()
    scheduler.step()
    back = _task(db_factory)
    assert back.status == TaskStatus.RUNNING and back.stage_id == ids["stages"]["Requisitos"]
    assert (back.work_mode, back.spec_path) == ("direct", None)
    with db_factory() as db:
        text = context.task_section(task_ops.task_context(db, db.get(Task, back.id)))
    assert "lo cambió la persona" in text  # in the history the agent reads


def test_the_mode_cannot_change_once_the_task_forked_or_finished(db_factory, scheduler, launcher):
    setup_split(db_factory, conditions=False)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    with db_factory() as db:
        task = db.get(Task, _task(db_factory).id)
        assert task.status == TaskStatus.FORKED
        with pytest.raises(ApiError) as forked:
            task_ops.change_work_mode(db, task, "sdd")
        assert forked.value.code == "work_mode_forked"
        task.status = TaskStatus.DONE
        lane = db.scalar(select(Task).where(Task.lane_key == "backend"))
        with pytest.raises(ApiError):
            task_ops.change_work_mode(db, lane, "sdd")


# ---------------------------------------------------------------------- MCP and the API
@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def test_set_work_mode_through_the_mcp_and_the_change_through_the_api(
    server: LiveServer, tmp_path: Path
):
    run_id, token = seed_run(server, tmp_path)
    with server.db() as db:
        run = db.get(Run, run_id)
        task = task_ops.create_task(
            db, db.get(Project, run.project_id), "Login con Google", agent_id=run.agent_id
        )
        run.task_id = task.id
        db.commit()
        task_id = task.id
    url = mcp_url(server, token)
    assert "spec_path" in call(url, "set_work_mode", {"mode": "sdd", "reason": "grande"})
    answer = call(
        url, "set_work_mode", {"mode": "sdd", "reason": "grande", "spec_path": "specs/001-login"}
    )
    assert answer == "Modo de trabajo guardado."
    # Not written yet: the stage cannot end.
    refused = call(url, "complete_task", {"summary": "requisitos"})
    assert "specs/001-login" in refused

    import httpx

    api = f"{server.url}/api/tasks/{task_id}"
    shown = httpx.get(api).json()
    assert (shown["work_mode"], shown["spec_path"]) == ("sdd", "specs/001-login")
    changed = httpx.put(f"{api}/work-mode", json={"mode": "direct"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["work_mode"] == "direct"
    assert httpx.put(f"{api}/work-mode", json={"mode": "x"}).status_code == 422
