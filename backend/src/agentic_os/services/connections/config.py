"""The connections' timeouts and switches, kept in `app_state` (JSON), like the skills' ones.
The registries' switches are added in block 8."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from sqlalchemy.orm import Session

from agentic_os.models import CONNECTIONS, AppState


@dataclass
class ConnectionSettings:
    probe_timeout: int = 60  # seconds a test waits for a server (the first `npx` downloads it)
    startup_timeout: int = 60  # MCP_TIMEOUT for Claude: seconds it waits for a server to start
    agy_grace: int = 5  # seconds agy gets to connect the servers before the prompt is typed
    oauth_port: int = 53682  # where the login comes back to (a pasted client id needs it exact)
    # Public registries (block 8): source id → on/off (missing: the source's default).
    registries: dict = field(default_factory=dict)


_LIMITS = {
    "probe_timeout": (5, 600),
    "startup_timeout": (5, 600),
    "agy_grace": (0, 120),
    "oauth_port": (1024, 65535),
}


def load(db: Session) -> ConnectionSettings:
    state = db.get(AppState, CONNECTIONS)
    try:
        stored = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        stored = {}
    return normalized(ConnectionSettings(), stored if isinstance(stored, dict) else {})


def normalized(base: ConnectionSettings, values: dict) -> ConnectionSettings:
    result = ConnectionSettings(**asdict(base))
    for item in fields(result):
        value = values.get(item.name)
        if item.name == "registries":
            if isinstance(value, dict):
                merged = dict(result.registries)
                merged.update({str(k): v for k, v in value.items() if isinstance(v, bool)})
                result.registries = merged
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        low, high = _LIMITS[item.name]
        setattr(result, item.name, max(low, min(high, value)))
    return result


def save(db: Session, values: dict) -> ConnectionSettings:
    settings = normalized(load(db), values)
    state = db.get(AppState, CONNECTIONS)
    if state is None:
        state = AppState(key=CONNECTIONS)
        db.add(state)
    state.value = json.dumps(asdict(settings))
    return settings
