import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

POINTER_FILE = "location.json"


def home_dir() -> Path:
    """Fixed folder of the app: the data by default, and always the pointer to the data."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "AgenticOS"
    return Path.home() / ".agentic-os"


def read_pointer(home: Path | None = None) -> dict:
    """`location.json` (phase 08): {"data_dir", "pending_move": {"from", "to"}, "last_error"}.
    Missing or broken: the data is in the home folder."""
    try:
        data = json.loads(((home or home_dir()) / POINTER_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def default_data_dir() -> Path:
    """Where the data is: the pointer's folder (the user moved it) or the home folder.
    AGENTIC_OS_DATA_DIR overrides both (tests, development)."""
    moved = read_pointer().get("data_dir")
    return Path(moved) if isinstance(moved, str) and moved else home_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIC_OS_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = Field(default_factory=default_data_dir)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ]
    log_level: str = "INFO"
    log_json: bool = False
    log_file: Path | None = None
    # Overrides the SQLite file in data_dir (e.g. postgresql+psycopg://… in server mode).
    database_url: str | None = None
    # argv prefix replacing a CLI executable, e.g. {"claude": ["python", "fake_cli.py"]} (tests).
    cli_command_overrides: dict[str, list[str]] = {}
    # The CLIs' global config files whose folder-trust entries are cleaned when a task worktree
    # is removed (None: the real ones; tests point them elsewhere).
    claude_config_file: Path | None = None
    agy_settings_file: Path | None = None
    # Debugging: appends every hook payload received (JSON lines) to this file.
    hook_log: Path | None = None
    # Asks each CLI at startup whether its accounts are logged in (phase 10). Tests turn it off:
    # it would run the real CLIs.
    check_sessions_at_startup: bool = True
    # Where the knowledge library converts documents (phase 14): "subprocess" (a low-priority
    # worker process), "inline" (inside the backend) or "off" (nothing runs by itself: tests).
    knowledge_processing: str = "subprocess"


@lru_cache
def get_settings() -> Settings:
    return Settings()
