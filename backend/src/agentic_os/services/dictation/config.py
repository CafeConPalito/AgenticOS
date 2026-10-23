"""The dictation settings, kept in `app_state` (JSON). The microphone is not here: its id belongs
to the browser, so the interface remembers it."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields

from sqlalchemy.orm import Session

from agentic_os.models import DICTATION, AppState

DEFAULT_SHORTCUT = "Ctrl+Space"
MAX_TERMS = 200
MAX_TERM_LENGTH = 60
LANGUAGE = re.compile(r"^(auto|[a-z]{2,3})$")


@dataclass
class DictationSettings:
    enabled: bool = True  # off: no microphones are shown
    language: str = "es"  # "auto" or an ISO 639-1 code Whisper knows
    shortcut: str = DEFAULT_SHORTCUT  # hold it to dictate in the focused field
    max_seconds: int = 300  # a dictation is cut here and what was said is transcribed
    vocabulary: list[str] = field(default_factory=list)  # names Whisper should get right


_LIMITS = {"max_seconds": (30, 900)}


def clean_terms(values: object) -> list[str]:
    """The user's terms: trimmed, without blanks or repeats (case aside), within the limits."""
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        term = " ".join(value.split())[:MAX_TERM_LENGTH]
        if term and term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)
    return terms[:MAX_TERMS]


def load(db: Session) -> DictationSettings:
    state = db.get(AppState, DICTATION)
    try:
        stored = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        stored = {}
    return normalized(DictationSettings(), stored if isinstance(stored, dict) else {})


def normalized(base: DictationSettings, values: dict) -> DictationSettings:
    """`base` with the known keys of `values` applied, each one within its limits."""
    result = DictationSettings(**{**asdict(base), "vocabulary": list(base.vocabulary)})
    for item in fields(result):
        if item.name not in values:
            continue
        value = values[item.name]
        if item.name == "enabled" and isinstance(value, bool):
            result.enabled = value
        elif item.name == "language" and isinstance(value, str) and LANGUAGE.match(value):
            result.language = value
        elif item.name == "shortcut" and isinstance(value, str) and value.strip():
            result.shortcut = value.strip()[:40]
        elif item.name == "max_seconds" and isinstance(value, int) and not isinstance(value, bool):
            low, high = _LIMITS["max_seconds"]
            result.max_seconds = max(low, min(high, value))
        elif item.name == "vocabulary":
            result.vocabulary = clean_terms(value)
    return result


def save(db: Session, values: dict) -> DictationSettings:
    settings = normalized(load(db), values)
    state = db.get(AppState, DICTATION)
    if state is None:
        state = AppState(key=DICTATION)
        db.add(state)
    state.value = json.dumps(asdict(settings))
    return settings
