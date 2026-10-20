"""The Hugging Face token, for the models that ask for an account (none of today's do).

The app keeps no secret of its own (ADR 0018): the token is read from where the person already
has it (environment, the `huggingface_hub` file, git's credential helper) and, if they paste
one in Settings, saved in git's credential helper like the code hosts' tokens.
"""

from __future__ import annotations

import os
from pathlib import Path

from agentic_os.services.gitx import credentials

HOST = "huggingface.co"
ENVIRONMENT = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def _file() -> Path:
    home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    return Path(home) / "token"


def find() -> tuple[str | None, str | None]:
    """(token, where it came from: «env», «file» or «git») — or (None, None)."""
    for name in ENVIRONMENT:
        if os.environ.get(name, "").strip():
            return os.environ[name].strip(), "env"
    try:
        token = _file().read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if token:
        return token, "file"
    stored = credentials.token_for(HOST)
    return (stored, "git") if stored else (None, None)


def token() -> str | None:
    return find()[0]


def save(value: str) -> None:
    credentials.store(HOST, value)


def forget() -> None:
    credentials.forget(HOST)
