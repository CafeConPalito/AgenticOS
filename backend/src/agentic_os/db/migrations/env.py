from alembic import context

from agentic_os import models  # noqa: F401 - registers every table on Base.metadata
from agentic_os.db.base import Base

config = context.config
engine = config.attributes["engine"]

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
