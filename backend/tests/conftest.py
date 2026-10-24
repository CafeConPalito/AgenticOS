from collections.abc import Iterator
from pathlib import Path

import pytest
from dictation_helpers import speech  # noqa: F401 - a fixture for the dictation tests
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.services.connections import secrets as connection_secrets


@pytest.fixture(autouse=True)
def credential_store() -> Iterator[connection_secrets.MemoryStore]:
    """Never the person's own credential manager: the secrets of the tests live in memory."""
    store = connection_secrets.MemoryStore()
    previous = connection_secrets.use(store)
    yield store
    connection_secrets.use(previous)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        # Never the user's real CLI configs (trust cleanup of task worktrees).
        claude_config_file=tmp_path / "claude.json",
        agy_settings_file=tmp_path / "agy-settings.json",
        agy_mcp_config_file=tmp_path / "agy-mcp.json",
        check_sessions_at_startup=False,  # never run the real CLIs
        knowledge_processing="off",  # the knowledge tests run the queue themselves
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
