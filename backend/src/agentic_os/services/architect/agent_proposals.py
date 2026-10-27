"""`propose_agent` (phase 19, plan §5, spec G): an agent that sees during a task that a role is
missing proposes a new agent. Only agents with «Puede proponer agentes», once per run, with
the same rules as the Architect's sheet; a role the team already has is not proposed again.
The result is a draft with its origin and reason, waiting in the Inbox."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.models import Agent, Proposal, ProposalOrigin, Run
from agentic_os.services import proposals
from agentic_os.services.architect import sheet as sheets
from agentic_os.services.skills.library import SkillLibrary

PER_RUN = 1
# What an agent may set: never accounts, teams, skills written by it or the right to propose.
ALLOWED = (
    "name",
    "role",
    "description",
    "color",
    "cli",
    "model",
    "permission_mode",
    "allowed_tools",
    "max_concurrency",
    "can_spawn_subagents",
    "can_create_tasks",
    "instructions",
    "skills",
    "knowledge",
    "connections",
)


def propose(
    db: Session,
    lib: SkillLibrary,
    catalog: sheets.Catalog,
    run: Run,
    agent: Agent,
    sheet: Mapping,
    reason: str,
) -> tuple[str, str]:
    """(answer for the agent, detail for the run's events)."""
    if not agent.can_propose_agents:
        return "No tienes permiso para proponer agentes.", "sin permiso"
    if not reason.strip():
        return "Explica en `reason` por qué hace falta ese agente.", "sin motivo"
    made = db.scalar(
        select(func.count()).select_from(Proposal).where(Proposal.source_run_id == run.id)
    )
    if (made or 0) >= PER_RUN:
        return (
            "Ya has propuesto un agente en esta ejecución: espera a que la persona lo revise.",
            "límite por ejecución",
        )
    patch = {key: value for key, value in dict(sheet).items() if key in ALLOWED}
    ignored = sorted(set(sheet) - set(ALLOWED))
    result = sheets.apply_patch(catalog, {}, patch)
    values = result.sheet["agents"][sheets.MAIN]
    problems = [f"{path.split('.')[-1]}: {why}" for path, why in result.refused.items()]
    issues = sheets.agent_issues(catalog, values)
    problems += [i.message for i in issues if i.level == "error"]
    if problems:
        return "No se ha registrado la propuesta. Corrige esto:\n- " + "\n- ".join(
            problems
        ), "ficha inválida"
    repeated = [i.message for i in issues if i.code == "duplicate_role"]
    if repeated:
        return f"No se ha registrado la propuesta: {repeated[0]}. Usa ese agente.", "rol repetido"
    by = proposals.ProposedBy(
        ProposalOrigin.AGENT, run=run, agent=agent, task_id=run.task_id, reason=reason.strip()
    )
    proposal = proposals.create_new_agent(db, lib, catalog, result.sheet, by)
    db.commit()
    note = f" (no se usan: {', '.join(ignored)})" if ignored else ""
    name = values.get("name", "")
    return (
        f"Propuesta registrada: el agente «{name}» espera la revisión de la persona{note}. "
        "Sigue con tu tarea.",
        f"{name} ({proposal.id})",
    )
