import logging
from pathlib import Path

import structlog

from agentic_os.logging_setup import configure_logging


def test_structlog_and_stdlib_logs_reach_the_log_file(tmp_path: Path):
    log_file = tmp_path / "logs" / "backend.log"
    configure_logging("INFO", json=True, log_file=log_file)
    try:
        structlog.get_logger("test").info("from structlog", answer=42)
        logging.getLogger("uvicorn.error").info("from uvicorn")
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = log_file.read_text(encoding="utf-8")
        assert '"event": "from structlog"' in content
        assert '"answer": 42' in content
        assert '"event": "from uvicorn"' in content
    finally:
        configure_logging("INFO")


def test_reconfiguring_replaces_handlers(tmp_path: Path):
    configure_logging("INFO", log_file=tmp_path / "a.log")
    configure_logging("INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert not any(isinstance(h, logging.FileHandler) for h in root.handlers)
