"""Copy of the SQLite database before applying new migrations (phase 08, ADR 0012).

Installing a new version over an old one migrates the user's data on the first start. If a
migration goes wrong, the copy taken just before it is the way back.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import structlog
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from agentic_os.db.migrate import alembic_config

log = structlog.get_logger(__name__)

BACKUP_DIR = "backups"
KEEP = 3


def revisions(engine: Engine) -> tuple[str | None, str | None]:
    """(revision of the database, head of the migrations). None: a database never migrated."""
    head = ScriptDirectory.from_config(alembic_config(engine)).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, head


def backup_before_migrating(engine: Engine, data_dir: Path, keep: int = KEEP) -> Path | None:
    """Copies the database to <data_dir>/backups/ when migrations are pending, keeping the
    newest `keep` copies. Does nothing for a new database, an up-to-date one or a non-SQLite
    one (server mode)."""
    if engine.dialect.name != "sqlite" or not engine.url.database:
        return None
    current, head = revisions(engine)
    if current is None or current == head:
        return None
    folder = data_dir / BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"{Path(engine.url.database).stem}-{current}-{stamp}.db"
    # The backup API copies a consistent snapshot, WAL included (a file copy could miss it).
    source = sqlite3.connect(engine.url.database)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    log.info("database_backed_up", path=str(target), revision=current, head=head)
    for old in sorted(folder.glob("*.db"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[keep:]:
        old.unlink(missing_ok=True)
    return target
