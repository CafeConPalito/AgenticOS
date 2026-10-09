from pathlib import Path

from agentic_os.config import Settings


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.data_dir.name in {"AgenticOS", ".agentic-os"}


def test_env_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENTIC_OS_PORT", "9999")
    monkeypatch.setenv("AGENTIC_OS_DATA_DIR", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.port == 9999
    assert settings.data_dir == tmp_path
