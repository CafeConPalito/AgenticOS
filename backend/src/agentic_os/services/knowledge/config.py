"""The knowledge library's limits and switches, kept in `app_state` (JSON)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy.orm import Session

from agentic_os.models import KNOWLEDGE, AppState


@dataclass
class KnowledgeSettings:
    max_file_mb: int = 100  # bigger originals are refused when added
    context_budget: int = 8_000  # tokens of documents that may go whole into a run's context
    small_doc_tokens: int = 2_000  # an «auto» document up to this size goes whole into the context
    concurrency: int = 1  # documents processed at the same time
    threads: int = 0  # CPU threads for OCR and embeddings; 0: half of the cores
    describe_images: bool = False  # describe pictures with AI (a CLI or llama.cpp)
    describer: str = "cli"  # «cli» or «local»
    # The CLI describer: empty means the first CLI with a session, its cheapest model.
    describer_cli: str = ""  # "", "claude" or "agy"
    describer_account: str = ""  # a CLI account id, or "" for the CLI's default
    describer_model: str = ""
    # Knowledge the agents propose (phase 15)
    proposals_enabled: bool = True
    proposals_per_run: int = 3  # most proposals one run may make
    proposals_max_tokens: int = 20_000  # biggest proposal (estimated tokens)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


_LIMITS = {  # (min, max) of the numeric settings
    "max_file_mb": (1, 2_048),
    "context_budget": (500, 200_000),
    "small_doc_tokens": (100, 50_000),
    "concurrency": (1, 4),
    "threads": (0, 64),
    "proposals_per_run": (1, 20),
    "proposals_max_tokens": (500, 100_000),
}


def load(db: Session) -> KnowledgeSettings:
    state = db.get(AppState, KNOWLEDGE)
    try:
        stored = json.loads(state.value) if state and state.value else {}
    except json.JSONDecodeError:
        stored = {}
    return normalized(KnowledgeSettings(), stored if isinstance(stored, dict) else {})


def normalized(base: KnowledgeSettings, values: dict) -> KnowledgeSettings:
    """`base` with the known keys of `values` applied, each one within its limits."""
    result = KnowledgeSettings(**asdict(base))
    for field in fields(result):
        if field.name not in values:
            continue
        value = values[field.name]
        if field.name in _LIMITS and isinstance(value, int) and not isinstance(value, bool):
            low, high = _LIMITS[field.name]
            setattr(result, field.name, max(low, min(high, value)))
        elif field.name in ("describe_images", "proposals_enabled") and isinstance(value, bool):
            setattr(result, field.name, value)
        elif field.name == "describer" and value in ("cli", "local"):
            result.describer = value
        elif field.name == "describer_cli" and value in ("", "claude", "agy"):
            result.describer_cli = value
        elif field.name in ("describer_account", "describer_model") and isinstance(value, str):
            setattr(result, field.name, value.strip()[:80])
    return result


def save(db: Session, values: dict) -> KnowledgeSettings:
    settings = normalized(load(db), values)
    state = db.get(AppState, KNOWLEDGE)
    if state is None:
        state = AppState(key=KNOWLEDGE)
        db.add(state)
    state.value = json.dumps(asdict(settings))
    return settings
