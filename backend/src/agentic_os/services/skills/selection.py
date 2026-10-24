"""Which skills a run gets (phase 17, block 3): the ones it can see, the mode of each one (the
stage wins over the agent) and the candidates for its task, by the cosine of «name + description»
with the active meaning model, or by words without one (spike S4)."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import (
    KnowledgeScope,
    OfferKind,
    Skill,
    SkillMode,
    SkillModeValue,
    SkillReview,
)
from agentic_os.services.skills.library import vector_text

# Which level wins when two visible skills share a name.
PRECEDENCE = {KnowledgeScope.AGENT: 0, KnowledgeScope.PROJECT: 1, KnowledgeScope.GENERAL: 2}
WORD = re.compile(r"\w+")
STEM = 5
STOP = frozenset(
    [
        "a",
        "al",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "la",
        "las",
        "los",
        "of",
        "on",
        "or",
        "para",
        "por",
        "que",
        "se",
        "the",
        "this",
        "to",
        "un",
        "una",
        "use",
        "used",
        "uses",
        "using",
        "when",
        "with",
        "y",
    ]
)


@dataclass
class Offer:
    skill: Skill
    kind: OfferKind
    rank: int = 0
    score: float | None = None


@dataclass
class Selection:
    always: list[Offer] = field(default_factory=list)
    candidates: list[Offer] = field(default_factory=list)
    # skill → why it is not offered: never_stage · never_agent · manual_only · below_floor
    excluded: list[tuple[Skill, str]] = field(default_factory=list)
    method: str = "none"  # vector · words · none (nothing to rank)

    @property
    def offered(self) -> list[Offer]:
        return [*self.always, *self.candidates]


def visible(db: Session, project_id: str | None, agent_ids: Sequence[str]) -> list[Skill]:
    """The skills a run can use: switched on, approved, of its levels. A name at several levels
    keeps the most specific one (agent > project > general); between two agents' (a subagent and
    its parent), the first in `agent_ids`."""
    levels = [Skill.scope == KnowledgeScope.GENERAL]
    if project_id:
        levels.append((Skill.scope == KnowledgeScope.PROJECT) & (Skill.project_id == project_id))
    if agent_ids:
        levels.append((Skill.scope == KnowledgeScope.AGENT) & Skill.agent_id.in_(agent_ids))
    skills = db.scalars(
        select(Skill).where(
            Skill.workspace_id == DEFAULT_WORKSPACE,
            Skill.enabled.is_(True),
            Skill.review == SkillReview.NONE,
            Skill.current_version_id.is_not(None),
            or_(*levels),
        )
    )
    order = {agent: i for i, agent in enumerate(agent_ids)}
    best: dict[str, Skill] = {}
    for skill in sorted(
        skills,
        key=lambda s: (PRECEDENCE[KnowledgeScope(s.scope)], order.get(s.agent_id or "", 0)),
    ):
        best.setdefault(skill.name, skill)
    return sorted(best.values(), key=lambda s: s.name)


def modes(
    db: Session, skills: Sequence[Skill], agent_id: str | None, stage_id: str | None
) -> dict[str, tuple[SkillModeValue, str]]:
    """skill id → (its mode, who set it: stage · agent · default). The stage wins (CA4)."""
    ids = [s.id for s in skills]
    targets = []
    if agent_id:
        targets.append(SkillMode.agent_id == agent_id)
    if stage_id:
        targets.append(SkillMode.stage_id == stage_id)
    rows = (
        list(db.scalars(select(SkillMode).where(SkillMode.skill_id.in_(ids), or_(*targets))))
        if ids and targets
        else []
    )
    by_stage = {r.skill_id: r.mode for r in rows if r.stage_id}
    by_agent = {r.skill_id: r.mode for r in rows if r.agent_id}
    out: dict[str, tuple[SkillModeValue, str]] = {}
    for skill_id in ids:
        if skill_id in by_stage:
            out[skill_id] = (SkillModeValue(by_stage[skill_id]), "stage")
        elif skill_id in by_agent:
            out[skill_id] = (SkillModeValue(by_agent[skill_id]), "agent")
        else:
            out[skill_id] = (SkillModeValue.AUTO, "default")
    return out


# ------------------------------------------------------------------------ ranking
def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    """Words without accents, cut to a 5-letter stem: «migración» meets «migraciones» (S4b)."""
    words = (w for w in WORD.findall(_plain(text)) if w not in STOP and len(w) > 1)
    return [w[:STEM] for w in words]


def bm25(query: str, docs: Sequence[str], k1: float = 1.2, b: float = 0.75) -> list[float]:
    """BM25 of each doc for `query`, divided by the best score the query could get in this
    library: a share in [0, 1] whose floor holds for 5 skills and for 80 (spike S4b)."""
    bags = [Counter(tokens(d)) for d in docs]
    if not bags:
        return []
    lengths = [sum(bag.values()) for bag in bags]
    average = (sum(lengths) / len(lengths)) or 1.0
    df = Counter(w for bag in bags for w in bag)
    n = len(bags)
    scores = [0.0] * n
    best = 0.0
    for word in set(tokens(query)):
        if word not in df:
            continue
        idf = math.log(1 + (n - df[word] + 0.5) / (df[word] + 0.5))
        best += idf * (k1 + 1)
        for i, bag in enumerate(bags):
            tf = bag.get(word)
            if tf:
                scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[i] / average))
    return [s / best for s in scores] if best else scores


def task_query(title: str, description: str = "", stage: str = "", role: str = "") -> str:
    """What a task is compared with (spike S4): its title and description, its stage and the
    agent's role."""
    parts = [f"{title.strip()}.", description.strip()]
    if stage:
        parts.append(f"Etapa: {stage}.")
    if role:
        parts.append(f"Rol: {role}.")
    return " ".join(p for p in parts if p and p != ".")


def select_skills(
    skills: Sequence[Skill],
    skill_modes: dict[str, tuple[SkillModeValue, str]],
    query: str,
    *,
    limit: int,
    embed_query: Callable[[str], np.ndarray | None] | None = None,
    model: str | None = None,
    floor: float = 0.0,
    words_floor: float = 0.15,
) -> Selection:
    selection = Selection()
    pool: list[Skill] = []
    for skill in skills:
        mode, by = skill_modes.get(skill.id, (SkillModeValue.AUTO, "default"))
        if mode == SkillModeValue.NEVER:
            selection.excluded.append((skill, f"never_{by}"))
        elif mode == SkillModeValue.ALWAYS:
            selection.always.append(Offer(skill, OfferKind.ALWAYS))
        elif not skill.model_invocable:
            selection.excluded.append((skill, "manual_only"))
        else:
            pool.append(skill)
    if not pool or limit <= 0 or not query.strip():
        selection.excluded += [(s, "below_floor") for s in pool]
        return selection
    scored: list[tuple[float, Skill]] = []
    rest: list[Skill] = []
    vector = embed_query(query) if embed_query and model else None
    if vector is not None:
        selection.method = "vector"
        q = vector / (np.linalg.norm(vector) or 1.0)
        for skill in pool:
            if skill.vector is None or skill.vector_model != model:
                rest.append(skill)  # not embedded yet: it can still match by words
                continue
            v = np.frombuffer(skill.vector, dtype=np.float32)
            scored.append((float(q @ (v / (np.linalg.norm(v) or 1.0))), skill))
        scored = [(s, k) for s, k in scored if s >= floor]
    else:
        selection.method = "words"
        rest = pool
    if rest:
        words = bm25(query, [vector_text(s.name, s.description) for s in rest])
        extra = [(w, s) for w, s in zip(words, rest, strict=True) if w >= words_floor]
        # Skills not embedded yet, when the others are: after every one ranked by meaning
        # (their word share is in [0, 1], so -1 + share stays below any kept cosine).
        scored += [(-1 + w, s) for w, s in extra] if vector is not None else extra
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    chosen = scored[:limit]
    selection.candidates = [
        Offer(skill, OfferKind.CANDIDATE, rank, round(score, 4))
        for rank, (score, skill) in enumerate(chosen, 1)
    ]
    picked = {s.id for _, s in chosen}
    selection.excluded += [(s, "below_floor") for s in pool if s.id not in picked]
    return selection
