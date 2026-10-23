"""The skill library's budgets and switches, kept in `app_state` (JSON), like the knowledge
settings. Registries and proposals add theirs in later blocks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy.orm import Session

from agentic_os.models import SKILLS, AppState


@dataclass
class SkillSettings:
    candidates: int = 5  # skills offered per run besides the «always» ones
    index_tokens: int = 600  # budget of the list of candidates in the context
    always_tokens: int = 6_000  # budget of the «always» skills written whole in the context
    # Share of the best BM25 a query could get from which a skill is offered without a model
    # (spike S4b: holds for libraries of 5 to 80 skills).
    words_floor: float = 0.15


_LIMITS = {
    "candidates": (0, 20),
    "index_tokens": (100, 5_000),
    "always_tokens": (0, 50_000),
}
_FLOAT_LIMITS = {"words_floor": (0.0, 1.0)}


def load(db: Session) -> SkillSettings:
    state = db.get(AppState, SKILLS)
    try:
        stored = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        stored = {}
    return normalized(SkillSettings(), stored if isinstance(stored, dict) else {})


def normalized(base: SkillSettings, values: dict) -> SkillSettings:
    result = SkillSettings(**asdict(base))
    for field in fields(result):
        value = values.get(field.name)
        if value is None or isinstance(value, bool):
            continue
        if field.name in _LIMITS and isinstance(value, int):
            low, high = _LIMITS[field.name]
            setattr(result, field.name, max(low, min(high, value)))
        elif field.name in _FLOAT_LIMITS and isinstance(value, (int, float)):
            low, high = _FLOAT_LIMITS[field.name]
            setattr(result, field.name, max(low, min(high, float(value))))
    return result


def save(db: Session, values: dict) -> SkillSettings:
    settings = normalized(load(db), values)
    state = db.get(AppState, SKILLS)
    if state is None:
        state = AppState(key=SKILLS)
        db.add(state)
    state.value = json.dumps(asdict(settings))
    return settings
