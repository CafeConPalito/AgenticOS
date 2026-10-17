"""Migration 0012 (phase 12): the table of operations that can be undone."""

from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url


def test_the_operations_table_comes_and_goes(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0011")
    assert "git_operations" not in inspect(engine).get_table_names()

    command.upgrade(config, "0012")
    columns = {c["name"] for c in inspect(engine).get_columns("git_operations")}
    assert {"repo_id", "group_id", "kind", "refs_before", "refs_after", "backup_ref"} <= columns

    command.downgrade(config, "0011")
    assert "git_operations" not in inspect(engine).get_table_names()
    engine.dispose()
