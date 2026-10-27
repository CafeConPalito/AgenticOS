"""Ajustes › Arquitecto, kept in `app_state` (JSON) like the other settings: the CLI, account
and model it talks through, its base instructions (editable, restorable) and how long a CLI
stays alive (phase 19, plan §4; spikes S1-S3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy.orm import Session

from agentic_os.models import ARCHITECT, AppState, Cli

# Spike S3: Sonnet designs well enough at ~0,25 $ a conversation; Opus does not pay for itself.
DEFAULT_MODEL = {Cli.CLAUDE: "sonnet", Cli.AGY: "gemini-3.8-flash-high"}


@dataclass
class ArchitectSettings:
    cli: str = ""  # empty: Claude if it is installed, else agy
    account_id: str = ""  # empty: the CLI's default account
    model: str = ""  # empty: DEFAULT_MODEL of the CLI
    instructions: str = ""  # empty: the built-in ones (prompts.BASE)
    idle_minutes: int = 15  # a CLI without messages for this long is put to sleep
    max_live: int = 2  # CLIs of the Architect alive at once (and work folders)


_LIMITS = {"idle_minutes": (1, 240), "max_live": (1, 5)}


def load(db: Session) -> ArchitectSettings:
    state = db.get(AppState, ARCHITECT)
    try:
        stored = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        stored = {}
    return normalized(ArchitectSettings(), stored if isinstance(stored, dict) else {})


def normalized(base: ArchitectSettings, values: dict) -> ArchitectSettings:
    result = ArchitectSettings(**asdict(base))
    for item in fields(result):
        value = values.get(item.name)
        if item.name in _LIMITS:
            low, high = _LIMITS[item.name]
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(result, item.name, max(low, min(high, value)))
        elif item.name == "cli":
            if value in ("", *(c.value for c in Cli)):
                result.cli = value
        elif isinstance(value, str):
            setattr(result, item.name, value.strip() if item.name != "instructions" else value)
    return result


def save(db: Session, values: dict) -> ArchitectSettings:
    settings = normalized(load(db), values)
    state = db.get(AppState, ARCHITECT)
    data = json.dumps(asdict(settings), ensure_ascii=False)
    if state is None:
        db.add(AppState(key=ARCHITECT, value=data))
    else:
        state.value = data
    return settings
