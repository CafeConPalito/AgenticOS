"""The built-in themes (phase 22): the backend knows the same ids as the frontend."""

import json
from pathlib import Path

from agentic_os.schemas.appearance import BUILTIN_THEMES

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "frontend" / "src" / "generated" / "builtin-themes.json"


def test_the_backend_knows_the_built_in_themes_of_the_frontend():
    ids = json.loads(LIST.read_text(encoding="utf-8"))["ids"]
    assert list(BUILTIN_THEMES) == ids
    assert len(ids) >= 25
