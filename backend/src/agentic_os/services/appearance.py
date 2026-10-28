"""Appearance settings (phase 20), kept as one JSON document in `app_state`."""

import json

import structlog
from pydantic import ValidationError
from sqlalchemy.orm import Session

from agentic_os.models import APPEARANCE, AppState
from agentic_os.schemas.appearance import Appearance

log = structlog.get_logger(__name__)


def load(db: Session) -> Appearance:
    """What is stored, or the defaults when nothing is (or what is stored no longer validates)."""
    state = db.get(AppState, APPEARANCE)
    if state is None or not state.value:
        return Appearance()
    try:
        return Appearance.model_validate(json.loads(state.value))
    except (json.JSONDecodeError, ValidationError):
        log.warning("appearance_settings_unreadable")
        return Appearance()


def save(db: Session, appearance: Appearance) -> Appearance:
    state = db.get(AppState, APPEARANCE)
    if state is None:
        state = AppState(key=APPEARANCE)
        db.add(state)
    state.value = appearance.model_dump_json()
    return appearance
