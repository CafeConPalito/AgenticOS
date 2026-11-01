"""Migrations 0024 and 0025 (phase 24): the project photo, stage exits, where a task ended and
its working mode, and the two new task event kinds; both go back down cleanly."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from test_migration_0023 import _insert

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_phase_24_columns_and_event_kinds_come_and_go(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0023")
    with engine.begin() as db:
        _insert(
            db,
            engine,
            "projects",
            id="pr1",
            workspace_id="default",
            name="Web",
            workspace_mode="direct",
            integration_mode="merge",
            on_approve="none",
        )
        _insert(db, engine, "pipelines", id="p1", project_id="pr1", max_rejections=3)
        _insert(db, engine, "stages", id="s1", pipeline_id="p1", name="Requisitos")
        _insert(
            db,
            engine,
            "tasks",
            id="t1",
            workspace_id="default",
            project_id="pr1",
            number=1,
            title="Requisitos del login",
            status="done",
            priority="normal",
        )

    command.upgrade(config, "0025")
    assert "avatar" in _columns(engine, "projects")
    assert {"exit_condition", "exit_x", "exit_y"} <= _columns(engine, "stages")
    assert {"exit_stage_id", "work_mode", "work_mode_reason", "spec_path"} <= _columns(
        engine, "tasks"
    )
    with engine.begin() as db:
        db.execute(text("UPDATE stages SET exit_condition = 'Solo requisitos' WHERE id = 's1'"))
        db.execute(text("UPDATE tasks SET exit_stage_id = 's1', work_mode = 'sdd' WHERE id = 't1'"))
        for kind in ("exited", "work_mode"):
            _insert(db, engine, "task_events", id=f"e-{kind}", task_id="t1", seq=1, kind=kind)
    with pytest.raises(IntegrityError), engine.begin() as db:
        _insert(db, engine, "task_events", id="bad", task_id="t1", seq=2, kind="nonsense")
    with engine.connect() as db:
        assert db.execute(text("SELECT title FROM tasks WHERE id = 't1'")).scalar() is not None

    command.downgrade(config, "0023")
    assert "avatar" not in _columns(engine, "projects")
    assert "exit_condition" not in _columns(engine, "stages")
    assert "work_mode" not in _columns(engine, "tasks")
    with engine.connect() as db:
        kinds = db.execute(text("SELECT kind FROM task_events")).scalars().all()
        assert kinds == []
        assert db.execute(text("SELECT count(*) FROM tasks")).scalar() == 1
