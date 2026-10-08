import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "AgenticOS"
    return Path.home() / ".agentic-os"


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
