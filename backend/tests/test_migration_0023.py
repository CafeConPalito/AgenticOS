"""Migration 0023 (phase 21): a branch marked «always» loses its unused condition, since a branch
without one is now always taken."""

from pathlib import Path

from alembic import command
from sqlalchemy import inspect, text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url


def _insert(db, engine, table: str, **values) -> None:
    """A row with `values` and a filler in every other required column."""
    for column in inspect(engine).get_columns(table):
        if column["name"] in values or column["nullable"] or column.get("default") is not None:
            continue
        kind = str(column["type"]).upper()
        values[column["name"]] = (
            0
            if any(k in kind for k in ("INT", "BOOL"))
            else "2026-10-29 21:00:00"
            if "DATE" in kind
            else "{}"
            if "JSON" in kind
            else ""
        )
    names = ", ".join(values)
    db.execute(
        text(f"INSERT INTO {table} ({names}) VALUES ({', '.join(':' + n for n in values)})"), values
    )


def test_an_always_branch_drops_its_condition_and_the_others_keep_theirs(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0022")
    with engine.begin() as db:
        _insert(
            db,
            engine,
            "projects",
            id="pr1",
            workspace_id="default",
            name="Web",
            workspace_mode="direct",
        )
        _insert(db, engine, "pipelines", id="p1", project_id="pr1", max_rejections=3)
        for stage in ("s1", "s2", "s3"):
            _insert(db, engine, "stages", id=stage, pipeline_id="p1", name=stage)
        _insert(
            db,
            engine,
            "stage_links",
            id="l1",
            from_stage_id="s1",
            to_stage_id="s2",
            pipeline_id="p1",
            condition="toca la API",
            always=1,
        )
        _insert(
            db,
            engine,
            "stage_links",
            id="l2",
            from_stage_id="s1",
            to_stage_id="s3",
            pipeline_id="p1",
            condition="toca los datos",
            always=0,
        )
    command.upgrade(config, "0023")
    with engine.connect() as db:
        rows = dict(db.execute(text("SELECT id, condition FROM stage_links ORDER BY id")).all())
    assert rows == {"l1": "", "l2": "toca los datos"}
    command.downgrade(config, "0022")
