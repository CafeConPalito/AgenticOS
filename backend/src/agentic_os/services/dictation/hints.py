"""The hint Whisper gets before it listens: the names it cannot know (S3: the error on invented
names went from 25 % to 9 % with it).

A short sentence in the language of the dictation, built from what the user has in the app, with
the user's own terms first. Whisper reads about 224 tokens of it: the text is cut by characters.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import Agent, Project
from agentic_os.models.pipeline import Stage
from agentic_os.models.team import Team
from agentic_os.services.dictation.config import DictationSettings

BUDGET = 600  # characters
ROWS = 100  # names read per kind: more than the budget can hold

LABELS = {
    "es": ("Términos", "Agentes", "Proyectos", "Equipos", "Etapas"),
    "en": ("Terms", "Agents", "Projects", "Teams", "Stages"),
}


def build(db: Session, settings: DictationSettings) -> str:
    labels = LABELS.get(
        settings.language, LABELS["en"] if settings.language != "auto" else LABELS["es"]
    )
    groups = [
        settings.vocabulary,
        list(db.scalars(select(Agent.name).order_by(Agent.name).limit(ROWS))),
        list(db.scalars(select(Project.name).order_by(Project.name).limit(ROWS))),
        list(db.scalars(select(Team.name).order_by(Team.name).limit(ROWS))),
        list(db.scalars(select(Stage.name).order_by(Stage.name).limit(ROWS))),
    ]
    seen: set[str] = set()
    parts: list[str] = []
    used = 0
    for label, names in zip(labels, groups, strict=True):
        picked: list[str] = []
        for name in names:
            key = name.strip().lower()
            if not key or key in seen:
                continue
            cost = len(name) + 2
            if used + cost + len(label) > BUDGET:
                break
            seen.add(key)
            picked.append(name.strip())
            used += cost
        if picked:
            used += len(label) + 3
            parts.append(f"{label}: {', '.join(picked)}.")
    return " ".join(parts)
