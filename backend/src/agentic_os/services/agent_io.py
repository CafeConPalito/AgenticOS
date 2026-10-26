"""Agents as files and templates (phase 19, plan §6, ADR 0026 decision 7).

The format `agentic-os.agent` version 1 is plain JSON, without secrets or local ids:

    {"format": "agentic-os.agent", "version": 1,
     "agent": {name, role, description, color, cli, model, instructions, permission_mode,
               allowed_tools, max_concurrency, can_spawn_subagents, can_create_tasks,
               can_propose_agents},
     "skills": {"modes": [{"name", "mode"}],          # skills of the library, by name
                "own": [{"name", "files": {path: text}}]},  # the agent's own, embedded
     "knowledge": [{"title", "kind": "file" | "url", "source"}],
     "connections": ["github", …]}                   # by name: their secrets stay here

The account and the team are this installation's: they are not exported. Importing never
fails because something is missing: what does not exist here is listed, and left out.
The person's templates are this same format (`AgentTemplateRow.payload`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    AgentChange,
    AgentStatus,
    AgentTemplateRow,
    ChangeSource,
    Cli,
    KnowledgeDoc,
    KnowledgeScope,
    McpAssignment,
    McpConnection,
    Skill,
    SkillMode,
    SkillModeValue,
    SkillOriginKind,
    SkillReview,
    SourceKind,
)
from agentic_os.models.agent import MAX_CONCURRENCY, PermissionMode, Tool
from agentic_os.services.connections import library as connection_library
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import docs as knowledge_docs
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.library import SkillLibrary

FORMAT, VERSION = "agentic-os.agent", 1
FIELDS = (
    "name",
    "role",
    "description",
    "color",
    "cli",
    "model",
    "instructions",
    "permission_mode",
    "allowed_tools",
    "max_concurrency",
    "can_spawn_subagents",
    "can_create_tasks",
    "can_propose_agents",
)


# ---------------------------------------------------------------------------------- export
def export(db: Session, lib: SkillLibrary, agent: Agent) -> dict:
    values = {key: getattr(agent, key) for key in FIELDS}
    values["allowed_tools"] = list(agent.allowed_tools)
    modes = []
    for mode in db.scalars(select(SkillMode).where(SkillMode.agent_id == agent.id)):
        skill = db.get(Skill, mode.skill_id)
        if skill is not None and skill.scope != KnowledgeScope.AGENT:
            modes.append({"name": skill.name, "mode": mode.mode})
    own = []
    for skill in db.scalars(
        select(Skill).where(
            Skill.agent_id == agent.id,
            Skill.scope == KnowledgeScope.AGENT,
            Skill.review == SkillReview.NONE,
        )
    ):
        if not skill.current_version_id:
            continue
        files = lib.files(SkillLibrary.version(db, skill))
        texts = {}
        for path, data in files.items():
            try:
                texts[path] = data.decode("utf-8")
            except UnicodeDecodeError:  # binary files of a skill stay in this installation
                continue
        own.append({"name": skill.name, "files": texts})
    knowledge = [
        {
            "title": doc.title,
            "kind": "url" if doc.source_kind == SourceKind.URL else "file",
            "source": doc.url if doc.source_kind == SourceKind.URL else doc.path,
        }
        for doc in db.scalars(
            select(KnowledgeDoc).where(
                KnowledgeDoc.scope == KnowledgeScope.AGENT, KnowledgeDoc.agent_id == agent.id
            )
        )
        if doc.url or doc.path
    ]
    connections = sorted(
        connection.name
        for assignment in db.scalars(
            select(McpAssignment).where(
                McpAssignment.scope == KnowledgeScope.AGENT, McpAssignment.agent_id == agent.id
            )
        )
        if (connection := db.get(McpConnection, assignment.connection_id)) is not None
    )
    return {
        "format": FORMAT,
        "version": VERSION,
        "agent": values,
        "skills": {"modes": sorted(modes, key=lambda m: m["name"]), "own": own},
        "knowledge": knowledge,
        "connections": connections,
    }


# ---------------------------------------------------------------------------------- import
@dataclass
class Preview:
    agent: dict
    missing_skills: list[str] = field(default_factory=list)
    missing_connections: list[str] = field(default_factory=list)
    missing_knowledge: list[str] = field(default_factory=list)  # titles
    own_skills: list[str] = field(default_factory=list)
    cli_installed: bool = True
    notes: list[str] = field(default_factory=list)


def _valid(payload: Mapping) -> dict:
    """The file checked and normalized; unknown fields are dropped, wrong ones say why."""
    if not isinstance(payload, Mapping) or payload.get("format") != FORMAT:
        raise ApiError(422, "not_an_agent", "the file is not an Agentic OS agent")
    if payload.get("version") != VERSION:
        raise ApiError(
            422, "unsupported_version", f"version {payload.get('version')} is not supported"
        )
    raw = payload.get("agent")
    if not isinstance(raw, Mapping) or not str(raw.get("name") or "").strip():
        raise ApiError(422, "not_an_agent", "the agent has no name")
    agent: dict[str, Any] = {}
    for key in FIELDS:
        if key in raw:
            agent[key] = raw[key]
    agent["name"] = str(agent["name"]).strip()[:80]
    for key in ("role", "description", "instructions", "model"):
        agent[key] = str(agent.get(key) or "")
    agent["role"] = agent["role"][:80]
    agent["model"] = agent["model"][:80]
    if agent.get("cli") not in {c.value for c in Cli}:
        agent["cli"] = Cli.CLAUDE.value
    if agent.get("permission_mode") not in {m.value for m in PermissionMode}:
        agent["permission_mode"] = PermissionMode.ASK.value
    agent["allowed_tools"] = [
        t for t in agent.get("allowed_tools") or [] if t in {x.value for x in Tool}
    ]
    concurrency = agent.get("max_concurrency")
    agent["max_concurrency"] = (
        concurrency if isinstance(concurrency, int) and 1 <= concurrency <= MAX_CONCURRENCY else 1
    )
    for key in ("can_spawn_subagents", "can_create_tasks", "can_propose_agents"):
        agent[key] = bool(agent.get(key, False))
    color = str(agent.get("color") or "")
    agent["color"] = color if len(color) == 7 and color.startswith("#") else "#8FB4FF"
    skills = payload.get("skills") if isinstance(payload.get("skills"), Mapping) else {}
    return {
        "agent": agent,
        "modes": [m for m in skills.get("modes") or [] if isinstance(m, Mapping) and m.get("name")],
        "own": [s for s in skills.get("own") or [] if isinstance(s, Mapping) and s.get("files")],
        "knowledge": [k for k in payload.get("knowledge") or [] if isinstance(k, Mapping)],
        "connections": [str(c) for c in payload.get("connections") or [] if c],
    }


def _library_skill(db: Session, name: str) -> Skill | None:
    return db.scalar(
        select(Skill).where(
            Skill.workspace_id == DEFAULT_WORKSPACE,
            Skill.name == name,
            Skill.scope != KnowledgeScope.AGENT,
            Skill.review == SkillReview.NONE,
        )
    )


def _connection(db: Session, name: str) -> McpConnection | None:
    return db.scalar(
        select(McpConnection).where(
            McpConnection.workspace_id == DEFAULT_WORKSPACE, McpConnection.name == name
        )
    )


def preview(db: Session, payload: Mapping, installed: set[str] | None = None) -> Preview:
    """What importing would create, and what is missing here (it would be left out)."""
    data = _valid(payload)
    result = Preview(agent=data["agent"])
    result.missing_skills = [
        m["name"] for m in data["modes"] if _library_skill(db, m["name"]) is None
    ]
    result.missing_connections = [c for c in data["connections"] if _connection(db, c) is None]
    result.missing_knowledge = [
        str(k.get("title") or k.get("source"))
        for k in data["knowledge"]
        if k.get("kind") != "url" and not _file_exists(str(k.get("source") or ""))
    ]
    result.own_skills = [str(s.get("name")) for s in data["own"]]
    if installed is not None:
        result.cli_installed = data["agent"]["cli"] in installed
    return result


def _file_exists(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def apply(
    db: Session,
    lib: SkillLibrary,
    payload: Mapping,
    *,
    status: AgentStatus = AgentStatus.DRAFT,
    overrides: Mapping[str, Any] | None = None,
    template: str | None = None,
) -> tuple[Agent, list[str]]:
    """Creates the agent of `payload` (a draft by default): its fields (with `overrides` on top),
    the modes of the library's skills it has, its own skills, its connections and documents.
    Returns the agent and what was left out, in Spanish."""
    data = _valid(payload)
    notes: list[str] = []
    values = {**data["agent"], **{k: v for k, v in (overrides or {}).items() if v is not None}}
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, status=status, template=template, **values)
    db.add(agent)
    db.flush()
    for item in data["modes"]:
        skill = _library_skill(db, item["name"])
        mode = item.get("mode")
        if skill is None:
            notes.append(f"La skill «{item['name']}» no existe aquí.")
        elif mode in (SkillModeValue.ALWAYS, SkillModeValue.NEVER):
            db.add(SkillMode(skill_id=skill.id, agent_id=agent.id, mode=mode))
    for item in data["own"]:
        files = {str(p): str(t).encode("utf-8") for p, t in dict(item["files"]).items()}
        try:
            lib.create(
                db,
                scope=KnowledgeScope.AGENT,
                project_id=None,
                agent_id=agent.id,
                files=files,
                origin=SkillOriginKind.IMPORT,
                note="Importada con el agente",
            )
        except SkillError as error:
            notes.append(f"La skill «{item.get('name')}» no se pudo crear: {error.message}")
    for name in data["connections"]:
        connection = _connection(db, name)
        if connection is None:
            notes.append(f"La conexión «{name}» no existe aquí.")
        else:
            connection_library.assign(db, connection, KnowledgeScope.AGENT, agent_id=agent.id)
    limits = knowledge_config.load(db)
    for item in data["knowledge"]:
        source = str(item.get("source") or "")
        title = str(item.get("title") or source)
        try:
            if item.get("kind") == "url":
                knowledge_docs.add_url(db, KnowledgeScope.AGENT, None, agent.id, source)
                continue
            [added] = knowledge_docs.add_files(
                db, KnowledgeScope.AGENT, None, agent.id, [source], limits
            )
            if added.doc is None:
                notes.append(f"El documento «{title}» no se pudo añadir: {added.message}.")
        except ApiError as error:
            notes.append(f"El documento «{title}» no se pudo añadir: {error.message}.")
    db.add(
        AgentChange(agent_id=agent.id, source=ChangeSource.IMPORT, fields={"imported": agent.name})
    )
    db.flush()
    return agent, notes


# ------------------------------------------------------------------------------- templates
def _template_name(db: Session, wanted: str) -> str:
    taken = set(
        db.scalars(
            select(AgentTemplateRow.name).where(AgentTemplateRow.workspace_id == DEFAULT_WORKSPACE)
        )
    )
    for n in range(1, 1000):
        candidate = wanted if n == 1 else f"{wanted} ({n})"
        if candidate not in taken:
            return candidate[:80]
    raise ApiError(409, "template_name_taken", "too many templates with that name")


def save_template(
    db: Session, lib: SkillLibrary, agent: Agent, name: str | None = None
) -> AgentTemplateRow:
    payload = export(db, lib, agent)
    row = AgentTemplateRow(
        workspace_id=DEFAULT_WORKSPACE,
        name=_template_name(db, (name or agent.name).strip() or agent.name),
        description=agent.description,
        color=agent.color,
        payload=payload,
    )
    db.add(row)
    db.flush()
    return row


def get_template(db: Session, template_id: str) -> AgentTemplateRow:
    row = db.get(AgentTemplateRow, template_id)
    if row is None or row.workspace_id != DEFAULT_WORKSPACE:
        raise ApiError(404, "template_not_found", "template not found")
    return row


def duplicate_template(db: Session, row: AgentTemplateRow) -> AgentTemplateRow:
    copy = AgentTemplateRow(
        workspace_id=DEFAULT_WORKSPACE,
        name=_template_name(db, row.name),
        description=row.description,
        color=row.color,
        payload=dict(row.payload),
    )
    db.add(copy)
    db.flush()
    return copy


def rename_template(db: Session, row: AgentTemplateRow, values: Mapping[str, Any]) -> None:
    if "name" in values and values["name"] and values["name"] != row.name:
        row.name = _template_name(db, str(values["name"]).strip())
    if "description" in values:
        row.description = str(values["description"] or "")
    if values.get("color"):
        row.color = str(values["color"])
