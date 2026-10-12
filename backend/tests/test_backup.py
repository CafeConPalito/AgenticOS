"""Copy of the database before migrating (phase 08)."""

import os
import sqlite3
from pathlib import Path

from alembic import command
from sqlalchemy import text

from agentic_os.config import Settings
from agentic_os.db.backup import backup_before_migrating, revisions
from agentic_os.db.migrate import alembic_config, upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url


def make_engine(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    return create_db_engine(database_url(settings))


def test_a_new_database_is_not_copied(settings: Settings):
    engine = make_engine(settings)
    assert backup_before_migrating(engine, Path(settings.data_dir)) is None
    assert not (Path(settings.data_dir) / "backups").exists()


def test_an_up_to_date_database_is_not_copied(settings: Settings):
    engine = make_engine(settings)
    upgrade_to_head(engine)
    assert backup_before_migrating(engine, Path(settings.data_dir)) is None


def test_pending_migrations_copy_the_database_first(settings: Settings):
    engine = make_engine(settings)
    command.upgrade(alembic_config(engine), "0005")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE marker (name TEXT)"))
        conn.execute(text("INSERT INTO marker VALUES ('Dev')"))
    assert revisions(engine)[0] == "0005"

    copy = backup_before_migrating(engine, Path(settings.data_dir))

    assert copy is not None and copy.parent == Path(settings.data_dir) / "backups"
    assert "-0005-" in copy.name
    with sqlite3.connect(copy) as db:
        assert db.execute("SELECT name FROM marker").fetchall() == [("Dev",)]
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0005",)
    engine.dispose()


def test_only_the_newest_copies_are_kept(settings: Settings):
    engine = make_engine(settings)
    command.upgrade(alembic_config(engine), "0005")
    folder = Path(settings.data_dir) / "backups"
    folder.mkdir()
    for n in range(4):
        old = folder / f"old-{n}.db"
        old.write_bytes(b"")
        os.utime(old, ns=(n * 10**9, n * 10**9))

    copy = backup_before_migrating(engine, Path(settings.data_dir), keep=3)

    assert sorted(p.name for p in folder.iterdir()) == sorted([copy.name, "old-3.db", "old-2.db"])
    engine.dispose()
