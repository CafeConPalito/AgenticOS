from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config, upgrade_to_head
from agentic_os.db.session import DB_FILENAME, create_db_engine, database_url


def test_fresh_database_is_created_and_migrated(settings: Settings):
    with TestClient(create_app(settings)):
        pass
    db_file = Path(settings.data_dir) / DB_FILENAME
    assert db_file.exists()
    engine = create_db_engine(database_url(settings))
    tables = set(inspect(engine).get_table_names())
    assert {"agents", "projects", "runs", "alembic_version"} <= tables
    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    head = ScriptDirectory.from_config(alembic_config(engine)).get_current_head()
    assert current == head
    engine.dispose()


def test_upgrade_is_idempotent(settings: Settings):
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    upgrade_to_head(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1
    engine.dispose()


def test_existing_data_survives_restart(settings: Settings):
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/agents", json={"name": "Persistente"}).json()
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/agents/{created['id']}").json()["name"] == "Persistente"
