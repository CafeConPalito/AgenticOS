from alembic import context

from agentic_os import models  # noqa: F401 - registers every table on Base.metadata
from agentic_os.db.base import Base, UTCDateTime

config = context.config
engine = config.attributes["engine"]


def render_item(type_, obj, autogen_context):
    """Migrations must not import app types: render UTCDateTime as its plain column type."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


with engine.connect() as connection:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Batch mode rebuilds a table with DROP TABLE: with foreign keys on, that would run the
        # ON DELETE actions of every referencing row (deleting run events, nulling run
        # projects…). The pragma is a no-op inside a transaction, so it goes before.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=sqlite,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
    if sqlite:
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        if broken:
            raise RuntimeError(f"migration left broken foreign keys: {broken[:5]}")
