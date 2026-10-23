"""Which downloaded model is used for each job (embeddings, OCR, picture description, dictation).

Stored in `app_state` (JSON). Until the user chooses, the catalog's default is the choice; a choice
only takes effect once that model is downloaded.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from agentic_os.models import AppState
from agentic_os.services.localmodels import catalog, store
from agentic_os.services.localmodels.catalog import CatalogEntry

KEY = "local_models"
CHOOSABLE = (catalog.EMBEDDING, catalog.OCR, catalog.VISION, catalog.SPEECH)


def stored(db: Session) -> dict[str, str]:
    state = db.get(AppState, KEY)
    try:
        value = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        value = {}
    return {k: v for k, v in value.items() if k in CHOOSABLE and isinstance(v, str)}


def chosen(db: Session) -> dict[str, str | None]:
    """The id chosen for each job: the user's pick, else the default (even if not downloaded)."""
    picks = stored(db)
    result: dict[str, str | None] = {}
    for kind in CHOOSABLE:
        pick = catalog.entry(picks.get(kind, ""))
        default = catalog.default_of(kind)
        result[kind] = pick.id if pick and pick.kind == kind else (default.id if default else None)
    return result


def choose(db: Session, kind: str, entry_id: str | None) -> None:
    """Picks `entry_id` for the job `kind` (None: back to the default). ValueError if it is not
    a model of that kind."""
    if kind not in CHOOSABLE:
        raise ValueError(f"unknown job {kind!r}")
    picks = stored(db)
    if entry_id is None:
        picks.pop(kind, None)
    else:
        found = catalog.entry(entry_id)
        if found is None or found.kind != kind:
            raise ValueError(f"{entry_id!r} is not a {kind} model")
        picks[kind] = entry_id
    state = db.get(AppState, KEY)
    if state is None:
        state = AppState(key=KEY)
        db.add(state)
    state.value = json.dumps(picks)


def active(db: Session, data_dir: Path, kind: str) -> CatalogEntry | None:
    """The model to use for `kind` right now: the chosen one if it is downloaded, else None."""
    entry_id = chosen(db).get(kind)
    found = catalog.entry(entry_id) if entry_id else None
    return found if found is not None and store.is_installed(data_dir, found) else None
