"""What the Architect designs (phase 19, plan §2): the sheet of one or more agents, a team and a
project's pipeline, and the rules every change must pass.

The sheet is plain JSON (it lives in `ArchitectConversation.sheet` and in proposals):

    {"agents": {"main": {<agent fields>}},           # by a short ref the Architect chooses
     "existing_agents": [<agent id>],                 # team mode: agents reused as they are
     "team": {"team_id": ...} | {"name": ..., "description": ...} | {},
     "pipeline": {"project_id": ..., "stages": [...], "links": [...] | null, ...} | null,
     "suggested_connections": [{"ref": ..., "reason": ..., "agent_ref": ...}]}

`apply_patch` stores the fields that pass and refuses the rest with a reason the model can act
on (in Spanish: the model reads it, and so does the person). References are stored by id, with
their name next to it for the UI; the model may send either. The same rules serve the Architect,
`propose_agent` and the import of an agent.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    AgentStatus,
    CliAccount,
    DocStatus,
    KnowledgeDoc,
    KnowledgeScope,
    McpConnection,
    PermissionMode,
    Project,
    Review,
    Skill,
    SkillModeValue,
    SkillReview,
    Team,
    Tool,
)
from agentic_os.models.agent import MAX_CONCURRENCY
from agentic_os.schemas.pipeline import MAX_STAGES, LinkWrite, PipelineWrite, StageWrite
from agentic_os.services import accounts as account_ops
from agentic_os.services import avatars
from agentic_os.services import tasks as task_ops
from agentic_os.services.clis import CliInfo
from agentic_os.services.pipelines import check as check_graph
from agentic_os.services.pipelines import layout_of
from agentic_os.services.skills.format import NAME as SKILL_NAME
from agentic_os.services.skills.format import NAME_MAX as SKILL_NAME_MAX

MAIN = "main"
REF = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
TEXT_FIELDS = {"name": 80, "role": 80, "description": 2000, "instructions": 40000}
AGENT_FIELDS = (
    "name",
    "role",
    "description",
    "color",
    "avatar",
    "team",
    "cli",
    "account",
    "model",
    "permission_mode",
    "allowed_tools",
    "max_concurrency",
    "can_spawn_subagents",
    "can_create_tasks",
    "can_propose_agents",
    "instructions",
    "skills",
    "new_skills",
    "knowledge",
    "connections",
    "template",
)
REQUIRED = ("name", "role", "cli", "instructions")
# What the progress bar of the design counts (lists count once they were decided, even empty).
PROGRESS_FIELDS = (
    "name",
    "role",
    "description",
    "cli",
    "model",
    "permission_mode",
    "allowed_tools",
    "instructions",
    "skills",
    "knowledge",
    "connections",
)
MAX_NEW_SKILLS = 5
MAX_TEAM_AGENTS = 12

GRAPH_MESSAGES = {
    "no_start": "No hay una etapa inicial: alguna etapa no debe tener enlaces de entrada.",
    "many_starts": "Hay varias etapas iniciales: solo una puede no tener enlaces de entrada.",
    "unreachable": "A esta etapa no se llega desde la primera.",
    "cycle": "Los enlaces forman un ciclo: para devolver trabajo usa reject_to, no un enlace.",
    "unstructured": "Las ramas no se unen bien: las que salen de una bifurcación deben volver "
    "a unirse en la misma etapa.",
    "empty_branch": "Una rama va directa a la unión sin pasar por ninguna etapa.",
    "reject_not_backwards": "reject_to debe apuntar a una etapa anterior.",
    "reject_outside_path": "reject_to apunta a una etapa que no está en el camino de esta.",
}


@dataclass(frozen=True)
class Issue:
    """A problem of the sheet. `field` is a path: `main.model`, `team`, `pipeline.stages.2`."""

    field: str
    code: str
    message: str
    level: str = "error"  # «warning» does not block a proposal


@dataclass
class PatchResult:
    sheet: dict
    changed: list[str] = field(default_factory=list)  # field paths
    refused: dict[str, str] = field(default_factory=dict)  # field path → why


# --------------------------------------------------------------------------------- catalog
@dataclass(frozen=True)
class CliView:
    installed: bool
    models: tuple[str, ...]  # empty: unknown (the CLI could not list them), anything goes


@dataclass
class Catalog:
    """What exists in the installation, read once per tool call."""

    clis: dict[str, CliView]
    accounts: list[CliAccount]
    teams: list[Team]
    agents: list[Agent]
    skills: list[Skill]
    docs: list[KnowledgeDoc]
    connections: list[McpConnection]
    projects: list[Project]

    @classmethod
    def load(cls, db: Session, clis: Iterable[CliInfo], workspace_id: str) -> Catalog:
        def rows(model: Any, *where: Any) -> list:
            return list(db.scalars(select(model).where(*where)))

        return cls(
            clis={
                str(info.id): CliView(info.installed, tuple(m.id for m in info.models))
                for info in clis
            },
            accounts=rows(CliAccount),
            teams=rows(Team, Team.workspace_id == workspace_id),
            agents=rows(Agent, Agent.workspace_id == workspace_id, Agent.archived_at.is_(None)),
            skills=rows(
                Skill,
                Skill.workspace_id == workspace_id,
                Skill.enabled.is_(True),
                Skill.review == SkillReview.NONE,
            ),
            docs=rows(
                KnowledgeDoc,
                KnowledgeDoc.workspace_id == workspace_id,
                KnowledgeDoc.review == Review.NONE,
                KnowledgeDoc.status != DocStatus.FAILED,
            ),
            connections=rows(
                McpConnection,
                McpConnection.workspace_id == workspace_id,
                McpConnection.enabled.is_(True),
            ),
            projects=rows(Project, Project.workspace_id == workspace_id),
        )

    # Lookups by id or by name (the model may send either). -------------------------------
    @staticmethod
    def _find(items: Iterable[Any], value: object, *names: str) -> Any | None:
        if not isinstance(value, str) or not value.strip():
            return None
        wanted = value.strip()
        items = list(items)
        for item in items:
            if item.id == wanted:
                return item
        lowered = wanted.casefold()
        for item in items:
            if any(str(getattr(item, n) or "").casefold() == lowered for n in names):
                return item
        return None

    def account(self, value: object, cli: str | None) -> CliAccount | None:
        candidates = [a for a in self.accounts if cli is None or a.cli == cli]
        found = self._find(candidates, value, "label", "email")
        if found is None and isinstance(value, str):
            for account in candidates:
                if account_ops.display_name(account).casefold() == value.strip().casefold():
                    return account
        return found

    def team(self, value: object) -> Team | None:
        return self._find(self.teams, value, "name")

    def agent(self, value: object) -> Agent | None:
        return self._find(self.agents, value, "name")

    def skill(self, value: object) -> Skill | None:
        # Agent-level skills of other agents are theirs: not offered.
        usable = [s for s in self.skills if s.scope != KnowledgeScope.AGENT]
        return self._find(usable, value, "name")

    def doc(self, value: object) -> KnowledgeDoc | None:
        return self._find(self.docs, value, "title")

    def connection(self, value: object) -> McpConnection | None:
        return self._find(self.connections, value, "name")

    def project(self, value: object) -> Project | None:
        return self._find(self.projects, value, "name")


# ----------------------------------------------------------------------- one agent's fields
class Refused(ValueError):
    """A value that cannot go in a field; the message says why, for the model."""


def _text(value: object, limit: int, required: bool) -> str:
    if not isinstance(value, str):
        raise Refused("debe ser un texto")
    value = value.strip()
    if required and not value:
        raise Refused("no puede estar vacío")
    if len(value) > limit:
        raise Refused(f"como mucho {limit} caracteres")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise Refused("debe ser true o false")
    return value


def _list(value: object) -> list:
    if not isinstance(value, list):
        raise Refused("debe ser una lista")
    return value


def _check_cli(catalog: Catalog, value: object) -> str:
    view = catalog.clis.get(value) if isinstance(value, str) else None
    installed = sorted(c for c, v in catalog.clis.items() if v.installed)
    if view is None or not view.installed:
        raise Refused(
            f"CLI no disponible: {value}. Instalados: {', '.join(installed) or 'ninguno'}"
        )
    return str(value)


def _check_model(catalog: Catalog, value: object, cli: str | None) -> str:
    model = _text(value, 80, required=False)
    if not model or cli is None:
        return model  # empty: the CLI's default model
    view = catalog.clis.get(cli)
    if view is not None and view.models and model not in view.models:
        raise Refused(
            f"el modelo {model} no existe en {cli}. Disponibles: {', '.join(view.models)}"
        )
    return model


def _check_account(catalog: Catalog, value: object, cli: str | None) -> str | None:
    if value in (None, ""):
        return None  # the default account of its CLI
    if cli is None:
        raise Refused("elige antes el CLI")
    account = catalog.account(value, cli)
    if account is None:
        names = [account_ops.display_name(a) for a in catalog.accounts if a.cli == cli]
        raise Refused(f"no es una cuenta de {cli}. Cuentas: {', '.join(names) or 'ninguna'}")
    return account.id


def _check_team(catalog: Catalog, value: object) -> str | None:
    if value in (None, ""):
        return None
    team = catalog.team(value)
    if team is None:
        raise Refused(f"el equipo {value} no existe")
    return team.id


def _check_skills(catalog: Catalog, value: object) -> list[dict]:
    chosen, missing = [], []
    for item in _list(value):
        ref = (item.get("skill") or item.get("name")) if isinstance(item, dict) else item
        skill = catalog.skill(ref)
        if skill is None:
            missing.append(str(ref))
            continue
        mode = item.get("mode", SkillModeValue.AUTO) if isinstance(item, dict) else "auto"
        if mode not in {m.value for m in SkillModeValue}:
            raise Refused(f"el modo de {skill.name} debe ser auto, always o never")
        chosen.append({"skill_id": skill.id, "name": skill.name, "mode": mode})
    if missing:
        raise Refused(
            f"skills que no existen: {', '.join(missing)}. Búscalas o escribe una nueva "
            "con draft_skill"
        )
    return list({c["skill_id"]: c for c in chosen}.values())


def _check_new_skills(catalog: Catalog, value: object) -> list[dict]:
    items = _list(value)
    if len(items) > MAX_NEW_SKILLS:
        raise Refused(f"como mucho {MAX_NEW_SKILLS} skills nuevas por agente")
    result, names = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise Refused("cada skill nueva lleva name, description y body")
        name = str(item.get("name") or "").strip()
        if len(name) > SKILL_NAME_MAX or not SKILL_NAME.match(name):
            raise Refused(
                f"el nombre de skill {name!r} debe ir en minúsculas con guiones "
                f"(«revision-de-codigo»), como mucho {SKILL_NAME_MAX} caracteres"
            )
        if name in names or catalog.skill(name) is not None:
            raise Refused(f"ya hay una skill {name}: úsala o elige otro nombre")
        names.add(name)
        description = _text(item.get("description", ""), 1024, required=True)
        body = _text(item.get("body", ""), 40000, required=True)
        result.append({"name": name, "description": description, "body": body})
    return result


def _check_knowledge(catalog: Catalog, value: object) -> list[dict]:
    chosen, missing = [], []
    for item in _list(value):
        ref = (item.get("doc") or item.get("doc_id")) if isinstance(item, dict) else item
        doc = catalog.doc(ref)
        if doc is None:
            missing.append(str(ref))
        else:
            chosen.append({"doc_id": doc.id, "title": doc.title})
    if missing:
        raise Refused(f"documentos que no existen: {', '.join(missing)}")
    return list({c["doc_id"]: c for c in chosen}.values())


def _check_connections(catalog: Catalog, value: object) -> list[dict]:
    chosen, missing = [], []
    for item in _list(value):
        ref = (item.get("connection") or item.get("name")) if isinstance(item, dict) else item
        connection = catalog.connection(ref)
        if connection is None:
            missing.append(str(ref))
            continue
        if isinstance(item, dict) and item.get("tools") is not None:
            # Phase 18: the allowed tools belong to the connection, for every agent using it.
            raise Refused(
                f"las herramientas permitidas de {connection.name} se configuran en la conexión y "
                "valen para todos sus agentes: no se pueden limitar por agente. Asígnala sin "
                "«tools» y, si hace falta, díselo al usuario"
            )
        chosen.append({"connection_id": connection.id, "name": connection.name})
    if missing:
        raise Refused(
            f"conexiones que no existen: {', '.join(missing)}. Si hace falta una, sugiérela "
            "con suggest_connection"
        )
    return list({c["connection_id"]: c for c in chosen}.values())


def check_field(catalog: Catalog, sheet: Mapping, key: str, value: object) -> Any:
    """The value to store in `key`, normalized (ids for references); `Refused` if it cannot."""
    cli = sheet.get("cli")
    if key in TEXT_FIELDS:
        return _text(value, TEXT_FIELDS[key], required=key in ("name", "role"))
    if key == "avatar":
        # Phase 20: only an owl of the gallery (list_owls), or null for the initials.
        if value is None:
            return None
        owl = value[4:] if isinstance(value, str) and value.startswith("owl:") else value
        if owl not in avatars.OWL_IDS:
            raise Refused("debe ser un búho de la galería (list_owls), p. ej. «owl:glasses»")
        return f"owl:{owl}"
    if key == "color":
        if not isinstance(value, str) or not COLOR.match(value):
            raise Refused("debe ser un color #RRGGBB")
        return value
    if key == "cli":
        return _check_cli(catalog, value)
    if key == "model":
        return _check_model(catalog, value, cli)
    if key == "account":
        return _check_account(catalog, value, cli)
    if key == "team":
        return _check_team(catalog, value)
    if key == "permission_mode":
        if value not in {m.value for m in PermissionMode}:
            raise Refused("debe ser autonomous, restricted o ask")
        return value
    if key == "allowed_tools":
        known = [t.value for t in Tool]
        unknown = [t for t in _list(value) if t not in known]
        if unknown:
            raise Refused(f"herramientas desconocidas: {unknown}. Disponibles: {known}")
        return list(dict.fromkeys(value))  # type: ignore[arg-type]
    if key == "max_concurrency":
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 1 <= value <= MAX_CONCURRENCY
        ):
            raise Refused(f"va de 1 a {MAX_CONCURRENCY}")
        return value
    if key in ("can_spawn_subagents", "can_create_tasks", "can_propose_agents"):
        return _bool(value)
    if key == "skills":
        return _check_skills(catalog, value)
    if key == "new_skills":
        return _check_new_skills(catalog, value)
    if key == "knowledge":
        return _check_knowledge(catalog, value)
    if key == "connections":
        return _check_connections(catalog, value)
    if key == "template":
        return None if value in (None, "") else _text(value, 40, required=True)
    raise Refused("campo desconocido")


def apply_patch(
    catalog: Catalog,
    sheet: Mapping,
    patch: Mapping[str, object],
    *,
    ref: str = MAIN,
    locked: Iterable[str] = (),
) -> PatchResult:
    """Applies `patch` to the agent `ref` of `sheet` (a copy). Locked fields (`<ref>.<field>`)
    and values that do not pass are refused one by one; the rest is stored."""
    result = PatchResult(sheet=copy_sheet(sheet))
    if not REF.match(ref):
        result.refused[ref] = "agent_ref debe ser una clave corta en minúsculas («redactor»)"
        return result
    agents = result.sheet["agents"]
    if ref not in agents and len(agents) >= MAX_TEAM_AGENTS:
        result.refused[ref] = f"como mucho {MAX_TEAM_AGENTS} agentes nuevos"
        return result
    agent = dict(agents.get(ref, {}))
    locked = set(locked)
    # The CLI first: the model and the account are checked against the new one.
    for key in sorted(patch, key=lambda k: k != "cli"):
        path = f"{ref}.{key}"
        if key not in AGENT_FIELDS:
            result.refused[path] = "campo desconocido"
            continue
        if path in locked:
            result.refused[path] = (
                "campo fijado por el usuario: pide que lo suelte con request_unlock"
            )
            continue
        try:
            agent[key] = check_field(catalog, agent, key, patch[key])
        except (Refused, ValidationError) as error:
            result.refused[path] = str(error)
            continue
        result.changed.append(path)
    # A new CLI leaves the old one's account and model behind (unless they came along).
    if "cli" in patch and f"{ref}.cli" in result.changed:
        for dependent in ("account", "model"):
            if dependent not in agent:
                continue
            if dependent not in patch or f"{ref}.{dependent}" in result.refused:
                try:
                    check_field(catalog, agent, dependent, agent.get(dependent))
                except Refused:
                    agent.pop(dependent, None)
                    result.changed.append(f"{ref}.{dependent}")
    agents[ref] = agent
    return result


def copy_sheet(sheet: Mapping | None) -> dict:
    sheet = dict(sheet or {})
    return {
        "agents": {k: dict(v) for k, v in (sheet.get("agents") or {}).items()},
        "existing_agents": list(sheet.get("existing_agents") or []),
        "team": dict(sheet.get("team") or {}),
        "pipeline": dict(sheet["pipeline"]) if sheet.get("pipeline") else None,
        "suggested_connections": list(sheet.get("suggested_connections") or []),
        # What an improvement starts from (the agent, team or pipeline as it was): kept apart,
        # never edited, the base of the proposal of changes.
        "base": copy.deepcopy(sheet.get("base")) if sheet.get("base") else None,
    }


def agent_issues(catalog: Catalog, agent: Mapping, ref: str = MAIN) -> list[Issue]:
    """What still blocks this agent's sheet: required fields, and stored references that no
    longer pass (the catalog may have changed since they were checked)."""
    issues = [
        Issue(f"{ref}.{key}", "required", f"Falta {key}") for key in REQUIRED if not agent.get(key)
    ]
    for key in ("cli", "model", "account", "team"):
        if agent.get(key) not in (None, ""):
            try:
                check_field(catalog, agent, key, agent[key])
            except Refused as error:
                issues.append(Issue(f"{ref}.{key}", "invalid", str(error)))
    references = {
        "skills": ("skill_id", catalog.skill),
        "knowledge": ("doc_id", catalog.doc),
        "connections": ("connection_id", catalog.connection),
    }
    for key, (id_key, find) in references.items():
        gone = [
            i.get("name") or i.get("title") for i in agent.get(key) or [] if find(i[id_key]) is None
        ]
        if gone:
            issues.append(
                Issue(f"{ref}.{key}", "gone", f"Ya no existen: {', '.join(map(str, gone))}")
            )
    # An existing agent being improved carries its id: it does not repeat its own role.
    role = str(agent.get("role") or "").casefold()
    same = [
        a.name
        for a in catalog.agents
        if role and a.role.casefold() == role and a.id != agent.get("id")
    ]
    if same:
        issues.append(
            Issue(
                f"{ref}.role",
                "duplicate_role",
                f"Ya hay un agente con ese rol: {', '.join(same)}",
                level="warning",
            )
        )
    return issues


def progress(agent: Mapping) -> int:
    """Percentage of the sheet that is filled (the bar of the design)."""
    done = sum(1 for key in PROGRESS_FIELDS if key in agent and agent[key] not in (None, ""))
    return round(100 * done / len(PROGRESS_FIELDS))


def ready(catalog: Catalog, sheet: Mapping) -> bool:
    """Whether a proposal can be made: every new agent has what it needs and, if there is a
    pipeline, it is valid. Warnings do not block."""
    return not [i for i in sheet_issues(catalog, sheet) if i.level == "error"]


# ------------------------------------------------------------------------ team and pipeline
def set_team(catalog: Catalog, sheet: Mapping, team: Mapping) -> PatchResult:
    """A new team (`name`, `description`) or an existing one (`team`: id or name)."""
    result = PatchResult(sheet=copy_sheet(sheet))
    existing = team.get("team") or team.get("team_id")
    if existing:
        found = catalog.team(existing)
        if found is None:
            result.refused["team"] = f"el equipo {existing} no existe"
            return result
        result.sheet["team"] = {"team_id": found.id, "name": found.name}
    else:
        try:
            name = _text(team.get("name", ""), 80, required=True)
            description = _text(team.get("description", ""), 2000, required=False)
        except Refused as error:
            result.refused["team"] = str(error)
            return result
        if catalog.team(name) is not None:
            result.refused["team"] = f"ya hay un equipo {name}: úsalo con su nombre en «team»"
            return result
        result.sheet["team"] = {"name": name, "description": description}
    result.changed.append("team")
    return result


def use_existing_agent(catalog: Catalog, sheet: Mapping, value: object) -> PatchResult:
    result = PatchResult(sheet=copy_sheet(sheet))
    agent = catalog.agent(value)
    if agent is None or agent.status != AgentStatus.ACTIVE:
        result.refused["existing_agents"] = f"no hay ningún agente activo {value}"
        return result
    if agent.id not in result.sheet["existing_agents"]:
        result.sheet["existing_agents"].append(agent.id)
        result.changed.append("existing_agents")
    return result


def _stage_agent(catalog: Catalog, sheet: Mapping, value: object) -> str | None:
    """The agent of a stage: a ref of a new agent (`ref:<ref>`) or an existing agent's id."""
    if isinstance(value, str) and value in sheet["agents"]:
        return f"ref:{value}"
    agent = catalog.agent(value)
    if agent is not None and agent.status == AgentStatus.ACTIVE:
        return agent.id
    return None


def set_pipeline(catalog: Catalog, sheet: Mapping, pipeline: Mapping) -> PatchResult:
    """Stores the pipeline if its shape is right (project, stages with an agent, links by
    index); the graph rules are reported by `pipeline_issues`, not refused, so the model sees
    everything that is wrong at once."""
    result = PatchResult(sheet=copy_sheet(sheet))
    project = catalog.project(pipeline.get("project") or pipeline.get("project_id"))
    if project is None:
        result.refused["pipeline"] = "el proyecto no existe"
        return result
    stages_in = pipeline.get("stages")
    if not isinstance(stages_in, list) or not 1 <= len(stages_in) <= MAX_STAGES:
        result.refused["pipeline"] = f"stages debe tener entre 1 y {MAX_STAGES} etapas"
        return result
    stages, unknown = [], []
    for index, stage in enumerate(stages_in):
        if not isinstance(stage, dict) or not str(stage.get("name") or "").strip():
            result.refused["pipeline"] = f"la etapa {index} necesita un nombre"
            return result
        agent = _stage_agent(catalog, result.sheet, stage.get("agent"))
        if agent is None:
            unknown.append(f"{index} ({stage.get('agent')})")
        stages.append(
            {
                "id": stage.get("id"),
                "name": str(stage["name"]).strip()[:80],
                "agent": agent,
                "requires_review": bool(stage.get("requires_review", False)),
                "reject_to": stage.get("reject_to"),
                "reject_also": list(stage.get("reject_also") or []),
                "confirm_decision": bool(stage.get("confirm_decision", False)),
            }
        )
    if unknown:
        result.refused["pipeline"] = (
            f"etapas con un agente que no existe ni está en el equipo: {', '.join(unknown)}. "
            "Usa el agent_ref de un agente nuevo o el nombre de uno existente"
        )
        return result
    links = pipeline.get("links")
    if links is not None:
        try:
            links = [LinkWrite.model_validate(x).model_dump() for x in _list(links)]
        except (Refused, ValidationError) as error:
            result.refused["pipeline"] = f"links mal formados: {error}"
            return result
    result.sheet["pipeline"] = {
        "project_id": project.id,
        "project_name": project.name,
        "stages": stages,
        "links": links,
        # What the person set in the editor and the model cannot see is kept as it was.
        **_kept_settings(sheet.get("pipeline"), project.id),
    }
    if pipeline.get("max_rejections") is not None:
        result.sheet["pipeline"]["max_rejections"] = pipeline["max_rejections"]
    result.changed.append("pipeline")
    return result


PIPELINE_SETTINGS = ("name", "max_rejections", "decider_cli", "decider_account_id", "decider_model")


def _kept_settings(current: Mapping | None, project_id: str) -> dict:
    """The settings of the project's pipeline that the sheet carries along (its name, limit of
    rejections and who decides the forks); none for another project or a new pipeline."""
    if not current or current.get("project_id") != project_id:
        return {}
    return {key: current[key] for key in PIPELINE_SETTINGS if key in current}


def pipeline_write(sheet: Mapping, agent_ids: Mapping[str, str] | None = None) -> PipelineWrite:
    """The sheet's pipeline as the editor's payload. New agents' refs become `agent_ids[ref]`
    (or a placeholder id, enough to check the graph)."""
    data = sheet["pipeline"]
    agent_ids = agent_ids or {}

    def agent(value: str | None) -> str | None:
        if value and value.startswith("ref:"):
            ref = value[4:]
            return agent_ids.get(ref, f"new-agent:{ref}")
        return value

    return PipelineWrite(
        name=data.get("name", ""),
        max_rejections=data.get("max_rejections", 3),
        decider_cli=data.get("decider_cli"),
        decider_account_id=data.get("decider_account_id"),
        decider_model=data.get("decider_model"),
        stages=[
            StageWrite(
                id=s.get("id"),
                name=s["name"],
                agent_id=agent(s.get("agent")),
                requires_review=s.get("requires_review", False),
                reject_to=s.get("reject_to"),
                reject_also=s.get("reject_also", []),
                confirm_decision=s.get("confirm_decision", False),
            )
            for s in data["stages"]
        ],
        links=[LinkWrite.model_validate(x) for x in data["links"]]
        if data.get("links") is not None
        else None,
    )


def pipeline_issues(sheet: Mapping) -> list[Issue]:
    if not sheet.get("pipeline"):
        return []
    try:
        payload = pipeline_write(sheet)
        graph = check_graph(payload)
    except ValidationError as error:
        return [Issue("pipeline", "invalid", str(error))]
    except ApiError as error:  # indexes of links or rejections out of range
        return [Issue("pipeline", error.code, error.message)]
    issues = []
    for problem in graph:
        where = f"pipeline.stages.{problem.stage}" if problem.stage is not None else "pipeline"
        if problem.link is not None:
            where = f"pipeline.links.{problem.link}"
        issues.append(Issue(where, problem.code, GRAPH_MESSAGES.get(problem.code, problem.code)))
    return issues


def sheet_issues(catalog: Catalog, sheet: Mapping) -> list[Issue]:
    bases = (sheet.get("base") or {}).get("agents") or {}
    issues = []
    for ref, agent in (sheet.get("agents") or {}).items():
        base = bases.get(ref)
        for issue in agent_issues(catalog, agent, ref):
            # A stale reference the improvement does not touch (a model the CLI dropped, a
            # document that failed) is not the Architect's to fix, nor a reason to block.
            key = issue.field.split(".", 1)[-1]
            if (
                base is not None
                and issue.code in ("invalid", "gone")
                and key in agent
                and agent.get(key) == base.get(key)
            ):
                continue
            issues.append(issue)
    for agent_id in sheet.get("existing_agents") or []:
        if catalog.agent(agent_id) is None:
            issues.append(Issue("existing_agents", "gone", f"El agente {agent_id} ya no existe"))
    team = sheet.get("team") or {}
    if team.get("team_id") and catalog.team(team["team_id"]) is None:
        issues.append(Issue("team", "gone", "El equipo ya no existe"))
    pipeline = sheet.get("pipeline")
    if pipeline:
        if catalog.project(pipeline.get("project_id")) is None:
            issues.append(Issue("pipeline", "gone", "El proyecto ya no existe"))
        issues += pipeline_issues(sheet)
        for i, stage in enumerate(pipeline["stages"]):
            agent = stage.get("agent") or ""
            if agent.startswith("ref:") and agent[4:] not in sheet["agents"]:
                issues.append(
                    Issue(f"pipeline.stages.{i}", "gone", f"El agente {agent[4:]} ya no está")
                )
    return issues


def issues_payload(issues: Iterable[Issue]) -> list[dict]:
    return [
        {"field": i.field, "code": i.code, "message": i.message, "level": i.level} for i in issues
    ]


def pipeline_of(db: Session, project: Project) -> dict | None:
    """A project's pipeline in the sheet's format (stages keep their ids)."""
    pipeline = task_ops.pipeline_of(db, project.id)
    if pipeline is None:
        return None
    stages = sorted(pipeline.stages, key=lambda s: s.position)
    index = {s.id: i for i, s in enumerate(stages)}
    agents = {a.id: a.name for a in db.scalars(select(Agent))}
    return {
        "project_id": project.id,
        "project_name": project.name,
        "name": pipeline.name,
        "max_rejections": pipeline.max_rejections,
        "decider_cli": pipeline.decider_cli,
        "decider_account_id": pipeline.decider_account_id,
        "decider_model": pipeline.decider_model,
        "stages": [
            {
                "id": s.id,
                "name": s.name,
                "agent": s.agent_id,
                "agent_name": agents.get(s.agent_id or "", ""),
                "requires_review": s.requires_review,
                "reject_to": index.get(s.reject_to_stage_id) if s.reject_to_stage_id else None,
                "reject_also": [index[x] for x in s.reject_extra_ids if x in index],
                "confirm_decision": s.confirm_decision,
            }
            for s in stages
        ],
        "links": [
            {
                "source": index[link.from_stage_id],
                "target": index[link.to_stage_id],
                "name": link.name,
                "condition": link.condition,
                "always": link.always,
            }
            for link in sorted(pipeline.links, key=lambda x: x.position)
            if link.from_stage_id in index and link.to_stage_id in index
        ],
    }


def pipeline_layout(sheet: Mapping) -> dict[int, list[int]]:
    """Where to draw each stage of the sheet's pipeline (the editor's own layout)."""
    if not sheet.get("pipeline"):
        return {}
    try:
        payload = pipeline_write(sheet)
    except (ValidationError, KeyError):
        return {}
    return {i: list(xy) for i, xy in layout_of(payload).items()}


def _stage_key(stage: Mapping) -> tuple:
    return (
        stage.get("name"),
        stage.get("agent"),
        bool(stage.get("requires_review")),
        stage.get("reject_to"),
        tuple(stage.get("reject_also") or []),
    )


def _links(pipeline: Mapping) -> list[tuple]:
    links = pipeline.get("links")
    if links is None:
        links = [
            {"source": i, "target": i + 1} for i in range(len(pipeline.get("stages") or []) - 1)
        ]
    return sorted(
        (x["source"], x["target"], x.get("name", ""), x.get("condition", ""), bool(x.get("always")))
        for x in links
    )


def same_pipeline(a: Mapping | None, b: Mapping | None) -> bool:
    """Whether two pipelines in the sheet's format are the same (stages, by id, and links)."""
    if not a or not b:
        return not a and not b

    def stages(pipeline: Mapping) -> list[tuple]:
        return [(*_stage_key(s), s.get("id")) for s in pipeline["stages"]]

    return stages(a) == stages(b) and _links(a) == _links(b)


def pipeline_diff(before: Mapping | None, after: Mapping) -> dict:
    """What a pipeline proposal changes: stages added, removed and changed (by id), and
    whether the links (branches, conditions) change."""
    old = {s["id"]: s for s in (before or {}).get("stages") or [] if s.get("id")}
    new_ids = {s.get("id") for s in after["stages"] if s.get("id")}
    return {
        "added": [s["name"] for s in after["stages"] if not s.get("id") or s["id"] not in old],
        "removed": [s["name"] for sid, s in old.items() if sid not in new_ids],
        "changed": [
            s["name"]
            for s in after["stages"]
            if s.get("id") in old and _stage_key(old[s["id"]]) != _stage_key(s)
        ],
        "links_changed": _links(before or {"stages": []}) != _links(after),
    }
