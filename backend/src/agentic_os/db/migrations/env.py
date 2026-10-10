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
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
