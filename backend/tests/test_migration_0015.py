"""Migration 0015 (phase 13): a linear pipeline becomes a chain of links."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url


def _old_pipeline(engine) -> None:
    now = "2026-10-18 10:00:00.000000"
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO projects (id, workspace_id, name, color, description, path, path_key,"
                " workspace_mode, base_branch, created_at, updated_at) VALUES ('p1', 'default',"
                f" 'P', '#fff', '', 'C:/p', 'c:/p', 'direct', 'main', '{now}', '{now}')"
            )
        )
        db.execute(
            text(
                "INSERT INTO pipelines (id, project_id, name, max_rejections, created_at,"
                f" updated_at) VALUES ('pl1', 'p1', 'Web', 3, '{now}', '{now}')"
            )
        )
        for position, stage in enumerate(["s1", "s2", "s3"]):
            db.execute(
                text(
                    "INSERT INTO stages (id, pipeline_id, position, name, requires_review)"
                    f" VALUES ('{stage}', 'pl1', {position}, 'E{position}', 0)"
                )
            )


def _upgraded(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0014")
    _old_pipeline(engine)
    command.upgrade(config, "0015")
    return engine, config


def test_a_linear_pipeline_becomes_a_chain_and_comes_back(settings: Settings):
    engine, config = _upgraded(settings)
    with engine.connect() as db:
        links = db.execute(
            text("SELECT from_stage_id, to_stage_id, always FROM stage_links ORDER BY 1")
        ).all()
        stages = db.execute(
            text("SELECT x, y, confirm_decision, reject_extra_ids FROM stages ORDER BY position")
        ).all()
    assert [(a, b) for a, b, _ in links] == [("s1", "s2"), ("s2", "s3")]
    assert not any(always for *_, always in links)
    assert [(x, y, c) for x, y, c, _ in stages] == [(0, 0, 0), (280, 0, 0), (560, 0, 0)]
    assert {c["name"] for c in inspect(engine).get_columns("pipelines")} >= {
        "decider_cli",
        "decider_account_id",
        "decider_model",
    }

    command.downgrade(config, "0014")
    assert "stage_links" not in inspect(engine).get_table_names()
    assert "x" not in {c["name"] for c in inspect(engine).get_columns("stages")}
    engine.dispose()


def test_it_does_not_go_back_while_a_pipeline_forks(settings: Settings):
    engine, config = _upgraded(settings)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO stage_links (id, pipeline_id, from_stage_id, to_stage_id, name,"
                " condition, always, position) VALUES ('l9', 'pl1', 's1', 's3', 'x', 'y', 0, 1)"
            )
        )
    with pytest.raises(RuntimeError, match="fork"):
        command.downgrade(config, "0014")
    engine.dispose()
