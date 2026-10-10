from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["engine"] = engine
    return config


def upgrade_to_head(engine: Engine) -> None:
    """Applies pending migrations. Safe to call on every start."""
    command.upgrade(alembic_config(engine), "head")
