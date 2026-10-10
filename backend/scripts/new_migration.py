"""Generates the next Alembic revision from the model changes.

Usage: uv run --project backend python backend/scripts/new_migration.py "describe the change"

A throwaway SQLite database is first upgraded to head, so autogenerate only emits the
difference between the current migrations and the models. Review the file before committing.
"""

import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.script import ScriptDirectory

from agentic_os.db.migrate import alembic_config, upgrade_to_head
from agentic_os.db.session import create_db_engine


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_db_engine(f"sqlite:///{Path(tmp, 'migr.db').as_posix()}")
        upgrade_to_head(engine)
        config = alembic_config(engine)
        head = ScriptDirectory.from_config(config).get_current_head() or "0000"
        next_id = f"{int(head) + 1:04d}"
        command.revision(config, message=sys.argv[1], autogenerate=True, rev_id=next_id)
        engine.dispose()


if __name__ == "__main__":
    main()
