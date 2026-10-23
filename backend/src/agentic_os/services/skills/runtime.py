"""Skills in a run (phase 17, block 3): what it is offered when it starts (kept in `run_skills`, so
the context is the same on every `get_context`), the «Skills» section of its instructions, the
files on disk its scripts run from, and the MCP tools `use_skill` and `read_skill_file`."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.models import (
    Agent,
    LoadedVia,
    OfferKind,
    Pipeline,
    Run,
    RunSkill,
    Skill,
    SkillModeValue,
    SkillVersion,
    Stage,
    Task,
    Team,
)
from agentic_os.services.knowledge.tokens import estimate_tokens
from agentic_os.services.skills import config as skills_config
from agentic_os.services.skills import selection as sel
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import SKILL_MD, parse_skill_md
from agentic_os.services.skills.library import SkillLibrary

HEADER = """\
## Skills
Las skills son instrucciones probadas para tareas concretas. Antes de empezar, si alguna de la \
lista encaja con lo que tienes que hacer, cárgala con `use_skill` (por su nombre) y síguela; sus \
ficheros de apoyo se leen con `read_skill_file` y sus scripts están en la carpeta que te indica. \
`use_skill` sin nombre lista todas las que tienes."""
FILE_CHARS = 60_000  # more than this of one file: the agent reads it on disk


@dataclass
class Ranker:
    """How to rank skills for a task: the meaning model in use (if any)."""

    embed_query: Callable[[str], np.ndarray | None] | None = None
    model: str | None = None
    floor: float = 0.0


def skills_dir(runs_dir: Path, run_id: str) -> Path:
    return Path(runs_dir) / run_id / "skills"


def clean_run(runs_dir: Path, run_id: str) -> None:
    shutil.rmtree(skills_dir(runs_dir, run_id), ignore_errors=True)


def agent_ids(db: Session, run: Run) -> list[str]:
    """The agents whose skills the run sees: its own and, for a subagent, its parent's."""
    parent = db.get(Run, run.parent_run_id) if run.parent_run_id else None
    return [a for a in (run.agent_id, parent.agent_id if parent else None) if a]


def query_for(db: Session, run: Run, agent: Agent | None, task: Task | None) -> str:
    stage = db.get(Stage, run.stage_id) if run.stage_id else None
    role = agent.role if agent else ""
    if task is not None and not run.parent_run_id:
        return sel.task_query(task.title, task.description, stage.name if stage else "", role)
    return sel.task_query(run.prompt[:2_000], "", stage.name if stage else "", role)


def _copies(db: Session, run: Run, agent: Agent | None) -> dict:
    """Names kept with each row, so the statistics survive deletions (CA21)."""
    stage = db.get(Stage, run.stage_id) if run.stage_id else None
    pipeline = db.get(Pipeline, stage.pipeline_id) if stage else None
    team = db.get(Team, agent.team_id) if agent and agent.team_id else None
    return {
        "stage_name": stage.name if stage else "",
        "pipeline_id": pipeline.id if pipeline else None,
        "pipeline_name": pipeline.name if pipeline else "",
        "team_id": team.id if team else None,
        "team_name": team.name if team else "",
    }


def _materialize(
    lib: SkillLibrary, runs_dir: Path, run_id: str, name: str, version: SkillVersion
) -> Path:
    folder = skills_dir(runs_dir, run_id) / name
    if not folder.exists():
        lib.store.materialize(version.manifest, folder)
    return folder


def prepare_run(
    db: Session,
    lib: SkillLibrary,
    runs_dir: Path,
    run: Run,
    agent: Agent | None,
    task: Task | None,
    ranker: Ranker,
) -> sel.Selection:
    """Chooses the run's skills once, records them and writes their folders."""
    skills = sel.visible(db, run.project_id, agent_ids(db, run))
    settings = skills_config.load(db)
    selection = sel.select_skills(
        skills,
        sel.modes(db, skills, run.agent_id, run.stage_id),
        query_for(db, run, agent, task),
        limit=settings.candidates,
        embed_query=ranker.embed_query,
        model=ranker.model,
        floor=ranker.floor,
        words_floor=settings.words_floor,
    )
    copies = _copies(db, run, agent)
    now = utcnow()
    for offer in selection.offered:
        always = offer.kind == OfferKind.ALWAYS
        db.add(
            RunSkill(
                run_id=run.id,
                skill_id=offer.skill.id,
                version_id=offer.skill.current_version_id,
                skill_name=offer.skill.name,
                offered=offer.kind,
                rank=offer.rank,
                score=offer.score,
                loaded_via=LoadedVia.CONTEXT if always else None,
                loaded_at=now if always else None,
                **copies,
            )
        )
        version = db.get(SkillVersion, offer.skill.current_version_id)
        _materialize(lib, runs_dir, run.id, offer.skill.name, version)
    db.flush()
    return selection


def _rows(db: Session, run_id: str) -> list[tuple[RunSkill, Skill]]:
    return list(
        db.execute(
            select(RunSkill, Skill)
            .join(Skill, Skill.id == RunSkill.skill_id)
            .where(RunSkill.run_id == run_id)
            .order_by(RunSkill.offered, RunSkill.rank, RunSkill.skill_name)
        ).tuples()
    )


def _one_line(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


@dataclass
class Item:
    """One offered skill as the section shows it."""

    kind: OfferKind
    name: str
    description: str
    version_id: str | None


def section(db: Session, lib: SkillLibrary, runs_dir: Path, run_id: str) -> str:
    """The «Skills» block of the instructions, from what the run was offered (CA3)."""
    items = [
        Item(OfferKind(row.offered), row.skill_name, skill.description, row.version_id)
        for row, skill in _rows(db, run_id)
    ]
    return render(db, lib, items, lambda name: str(skills_dir(runs_dir, run_id) / name))


def render(db: Session, lib: SkillLibrary, items: list[Item], folder: Callable[[str], str]) -> str:
    """The section for `items` («always» first, then the candidates in order), within the
    budgets of the settings. An «always» skill that does not fit goes to the list."""
    if not items:
        return ""
    settings = skills_config.load(db)
    lines = [HEADER]
    listed: list[str] = []
    fixed: list[str] = []
    budget_list, budget_fixed = settings.index_tokens, settings.always_tokens
    for item in items:
        if item.kind == OfferKind.ALWAYS and item.version_id:
            version = db.get(SkillVersion, item.version_id)
            parsed = parse_skill_md(lib.store.read(version.manifest, SKILL_MD).decode("utf-8"))
            text = (
                f"### Skill fijada: {item.name}\nCarpeta: {folder(item.name)}\n\n"
                f"{parsed.body.strip()}"
            )
            cost = estimate_tokens(text)
            if cost <= budget_fixed:
                fixed.append(text)
                budget_fixed -= cost
                continue
            line = f"- {item.name} (fijada; cárgala con `use_skill`): {_one_line(item.description)}"
        elif item.kind == OfferKind.CANDIDATE:
            line = f"- {item.name}: {_one_line(item.description)}"
        else:
            continue
        cost = estimate_tokens(line)
        if cost > budget_list:
            break
        listed.append(line)
        budget_list -= cost
    if listed:
        lines += ["Las que encajan con esta tarea:", *listed]
    return "\n".join(lines + ([""] if fixed else []) + fixed)


# ---------------------------------------------------------------------- MCP tools
def _visible_now(db: Session, run: Run) -> list[Skill]:
    skills = sel.visible(db, run.project_id, agent_ids(db, run))
    current = sel.modes(db, skills, run.agent_id, run.stage_id)
    return [s for s in skills if current[s.id][0] != SkillModeValue.NEVER]


def _find(skills: list[Skill], name: str) -> Skill | None:
    wanted = name.strip().split(":")[-1].strip()  # «aos:revision» from the CLI's own list
    return next((s for s in skills if s.name == wanted), None)


def _row(db: Session, run: Run, skill: Skill) -> RunSkill:
    row = db.scalar(
        select(RunSkill).where(RunSkill.run_id == run.id, RunSkill.skill_id == skill.id)
    )
    if row is None:
        agent = db.get(Agent, run.agent_id) if run.agent_id else None
        row = RunSkill(
            run_id=run.id,
            skill_id=skill.id,
            version_id=skill.current_version_id,
            skill_name=skill.name,
            offered=OfferKind.REQUESTED,
            **_copies(db, run, agent),
        )
        db.add(row)
        db.flush()
    return row


def mark_loaded(row: RunSkill, via: LoadedVia) -> None:
    """The first way the skill reached the agent is the one recorded."""
    if row.loaded_via is None:
        row.loaded_via, row.loaded_at = via, utcnow()


def use_skill(
    db: Session, lib: SkillLibrary, runs_dir: Path, run: Run, name: str
) -> tuple[str, str]:
    """(answer for the agent, detail for the run's log)."""
    skills = _visible_now(db, run)
    if not name.strip():
        if not skills:
            return "No tienes skills disponibles.", "lista (0)"
        lines = [f"- {s.name}: {_one_line(s.description)}" for s in skills]
        return "Skills disponibles (cárgalas con use_skill):\n" + "\n".join(lines), (
            f"lista ({len(skills)})"
        )
    skill = _find(skills, name)
    if skill is None:
        names = ", ".join(s.name for s in skills[:20]) or "ninguna"
        return f"No tienes ninguna skill llamada «{name}». Las que tienes: {names}.", (
            f"{name}: no existe"
        )
    row = _row(db, run, skill)
    version = db.get(SkillVersion, row.version_id) if row.version_id else None
    if version is None:  # its version was deleted with a rejected proposal: use the current
        row.version_id = skill.current_version_id
        version = db.get(SkillVersion, row.version_id)
    folder = _materialize(lib, runs_dir, run.id, skill.name, version)
    text = lib.store.read(version.manifest, SKILL_MD).decode("utf-8")
    files = [
        f"- {path}{' (ejecutable)' if entry.get('executable') else ''}"
        for path, entry in sorted(version.manifest.items())
        if path != SKILL_MD
    ]
    mark_loaded(row, LoadedVia.TOOL)
    answer = [f"# Skill «{skill.name}» (versión {version.number})", f"Carpeta: {folder}"]
    if files:
        answer += ["Ficheros de apoyo (léelos con read_skill_file o desde la carpeta):", *files]
    answer += ["", text.strip()]
    return "\n".join(answer) + "\n", f"{skill.name} v{version.number}"


def read_skill_file(
    db: Session, lib: SkillLibrary, runs_dir: Path, run: Run, name: str, path: str
) -> tuple[str, str]:
    skill = _find(_visible_now(db, run), name)
    if skill is None:
        return f"No tienes ninguna skill llamada «{name}».", f"{name}: no existe"
    row = _row(db, run, skill)
    version = db.get(SkillVersion, row.version_id or skill.current_version_id)
    try:
        data = lib.store.read(version.manifest, path)
    except SkillError as error:
        return error.message, f"{skill.name}/{path}: ruta no válida"
    if data is None:
        available = ", ".join(sorted(p for p in version.manifest if p != SKILL_MD)) or "ninguno"
        return f"La skill «{skill.name}» no tiene el fichero «{path}». Tiene: {available}.", (
            f"{skill.name}/{path}: no existe"
        )
    folder = _materialize(lib, runs_dir, run.id, skill.name, version)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"«{path}» no es texto ({len(data)} bytes). Está en {folder / path}.",
            f"{skill.name}/{path}: binario",
        )
    if len(text) > FILE_CHARS:
        text = f"{text[:FILE_CHARS]}\n\n[… recortado: el fichero entero está en {folder / path}]"
    return text, f"{skill.name}/{path}"
