"""Appearance settings (phases 20 and 22), kept as one JSON document in `app_state`."""

import json

import structlog
from pydantic import ValidationError
from sqlalchemy.orm import Session

from agentic_os.models import APPEARANCE, AppState
from agentic_os.schemas.appearance import Appearance, StoredAppearance

log = structlog.get_logger(__name__)


def load(db: Session) -> StoredAppearance:
    """What is stored, or the defaults when nothing is (or what is stored no longer validates)."""
    state = db.get(AppState, APPEARANCE)
    if state is None or not state.value:
        return StoredAppearance()
    try:
        return StoredAppearance.from_stored(json.loads(state.value))
    except (json.JSONDecodeError, ValidationError):
        log.warning("appearance_settings_unreadable")
        return StoredAppearance()


def save(db: Session, appearance: Appearance) -> StoredAppearance:
    state = db.get(AppState, APPEARANCE)
    if state is None:
        state = AppState(key=APPEARANCE)
        db.add(state)
    state.value = appearance.model_dump_json()
    return StoredAppearance.model_validate(appearance.model_dump())
