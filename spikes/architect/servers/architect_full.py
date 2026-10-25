"""The Architect's MCP server over a fake installation (phase 19, spike S3).

Read tools over `fake_install.installation()` and sheet tools that validate like the app will
(plan §2): unknown CLIs, accounts, models, skills, documents, connections or agents are not
stored and come back as issues; a pipeline is checked as a graph. The state (sheet, issues,
rejected references, calls) is written to ARCH_STATE after every call.

Env: ARCH_TOKEN, ARCH_STATE, ARCH_MODE (agent · improve_agent · team · improve_pipeline),
ARCH_TARGET (agent name or project name). Usage: python architect_full.py <port>
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from pathlib import Path

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fake_install import installation  # noqa: E402

TOKEN = os.environ.get("ARCH_TOKEN", "arch-token")
STATE_PATH = os.environ.get("ARCH_STATE", "")
MODE = os.environ.get("ARCH_MODE", "agent")
TARGET = os.environ.get("ARCH_TARGET", "")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770

INST = installation()
AGENT_FIELDS = {
    "name", "role", "description", "color", "team", "cli", "account", "model",
    "permission_mode", "allowed_tools", "max_concurrency", "can_spawn_subagents",
    "can_create_tasks", "can_propose_agents", "instructions", "skills", "new_skills",
    "knowledge", "connections", "template",
}  # fmt: skip
REQUIRED = ("name", "role", "cli", "instructions")

STATE: dict = {
    "mode": MODE,
    "target": TARGET,
    "agents": {},  # ref → sheet (team mode: several; agent modes: "main")
    "existing": [],  # team mode: names of existing agents in the team
    "team": {},
    "pipeline": None,
    "locked": ["color"],
    "rejected": [],  # references the model tried that do not exist
    "calls": [],
    "suggested_connections": [],
    "unlock_requests": [],
}
if MODE == "improve_agent":
    base = next(a for a in INST["agents"] if a["name"] == TARGET)
    STATE["agents"]["main"] = copy.deepcopy(base)
    STATE["base"] = copy.deepcopy(base)
if MODE == "improve_pipeline":
    project = next(p for p in INST["projects"] if p["name"] == TARGET)
    STATE["pipeline"] = copy.deepcopy(project["pipeline"])
    STATE["base_pipeline"] = copy.deepcopy(project["pipeline"])

server = MCPServer("architect")


def _save(tool: str, args: dict) -> None:
    STATE["calls"].append({"t": time.time(), "tool": tool, "args": args})
    if STATE_PATH:
        Path(STATE_PATH).write_text(json.dumps(STATE, ensure_ascii=False, indent=1), "utf-8")


def _names(key: str) -> set[str]:
    return {x["name"] for x in INST[key]}


def _check_field(key: str, value, sheet: dict) -> str | None:
    """Why `value` cannot go in `key`, or None."""
    clis = {c["cli"]: c for c in INST["clis"]}
    if key == "cli" and value not in clis:
        return f"CLI desconocido: {value}. Disponibles: {', '.join(clis)}"
    if key == "model":
        cli = sheet.get("cli")
        models = clis[cli]["models"] if cli in clis else []
        if cli and value not in models:
            return f"El modelo {value} no existe en {cli}. Disponibles: {', '.join(models)}"
    if key == "account":
        cli = sheet.get("cli")
        accounts = [a["name"] for a in clis[cli]["accounts"]] if cli in clis else []
        if value not in accounts:
            return f"La cuenta {value} no es de {cli}. Cuentas: {', '.join(accounts) or 'ninguna'}"
    if key == "team" and value and value not in _names("teams") | {STATE["team"].get("name")}:
        return f"El equipo {value} no existe"
    if key == "permission_mode" and value not in ("autonomous", "restricted", "ask"):
        return "permission_mode debe ser autonomous, restricted o ask"
    if key == "allowed_tools":
        bad = [t for t in value if t not in INST["tools"]]
        if bad:
            return f"Herramientas desconocidas: {bad}. Disponibles: {INST['tools']}"
    if key == "skills":
        names = _names("skills")
        bad = [s.get("name") for s in value if s.get("name") not in names]
        if bad:
            return f"Skills que no existen: {bad}. Búscalas con search_skills o propón una nueva con draft_skill"
    if key == "knowledge":
        ids = {d["id"] for d in INST["docs"]}
        bad = [d for d in value if d not in ids]
        if bad:
            return f"Documentos que no existen: {bad}"
    if key == "connections":
        names = _names("connections")
        bad = [c.get("name") for c in value if c.get("name") not in names]
        if bad:
            return f"Conexiones que no existen: {bad}. Si hace falta una, sugiérela con suggest_connection"
    if key == "max_concurrency" and not (isinstance(value, int) and 1 <= value <= 5):
        return "max_concurrency va de 1 a 5"
    return None


def _issues(sheet: dict) -> list[str]:
    return [f"Falta {k}" for k in REQUIRED if not sheet.get(k)]


def _pipeline_issues(pipeline: dict | None) -> list[str]:
    if not pipeline:
        return ["No hay pipeline"]
    stages = pipeline.get("stages") or []
    if not stages:
        return ["El pipeline no tiene etapas"]
    known = set(STATE["agents"]) | set(STATE["existing"]) | _names("agents")
    issues = [
        f"Etapa {i} ({s.get('name')}): el agente {s.get('agent')} no existe ni está en el equipo"
        for i, s in enumerate(stages)
        if s.get("agent") not in known
    ]
    links = pipeline.get("links")
    if links is None:
        links = [{"source": i, "target": i + 1} for i in range(len(stages) - 1)]
    out: dict[int, list[dict]] = {}
    for link in links:
        s, t = link.get("source"), link.get("target")
        if not (
            isinstance(s, int)
            and isinstance(t, int)
            and 0 <= s < len(stages)
            and 0 <= t < len(stages)
        ):
            issues.append(f"Enlace con índices fuera de rango: {link}")
            continue
        out.setdefault(s, []).append(link)
    for s, group in out.items():
        if len(group) > 1:
            for link in group:
                if not link.get("always") and not (link.get("condition") or "").strip():
                    issues.append(
                        f"La rama {s}→{link['target']} de una bifurcación no tiene condición"
                    )
    # acyclic and everything reachable from stage 0
    seen, stack, visiting = set(), [], set()

    def visit(n: int) -> bool:
        if n in visiting:
            return False
        if n in seen:
            return True
        visiting.add(n)
        ok = all(visit(link["target"]) for link in out.get(n, []))
        visiting.discard(n)
        seen.add(n)
        stack.append(n)
        return ok

    if not visit(0):
        issues.append("El pipeline tiene un ciclo (los rechazos van en reject_to, no en links)")
    unreachable = [i for i in range(len(stages)) if i not in seen]
    if unreachable:
        issues.append(f"Etapas a las que no se llega desde la primera: {unreachable}")
    for i, stage in enumerate(stages):
        r = stage.get("reject_to")
        if r is not None and not (isinstance(r, int) and 0 <= r < i):
            issues.append(f"Etapa {i}: reject_to debe ser una etapa anterior")
    return issues


def _summary() -> dict:
    agents = {ref: {"sheet": s, "issues": _issues(s)} for ref, s in STATE["agents"].items()}
    answer: dict = {"agents": agents, "locked": STATE["locked"]}
    if MODE in ("team", "improve_pipeline"):
        answer["team"] = STATE["team"]
        answer["existing_agents"] = STATE["existing"]
        answer["pipeline"] = STATE["pipeline"]
        answer["pipeline_issues"] = _pipeline_issues(STATE["pipeline"])
    return answer


# ------------------------------------------------------------------------------ read tools
@server.tool()
def list_clis() -> str:
    """CLIs instalados, con sus cuentas, los modelos que admite cada uno y las herramientas
    que se pueden permitir a un agente."""
    _save("list_clis", {})
    return json.dumps({"clis": INST["clis"], "tools": INST["tools"]}, ensure_ascii=False)


@server.tool()
def list_teams() -> str:
    """Equipos existentes."""
    _save("list_teams", {})
    return json.dumps(INST["teams"], ensure_ascii=False)


@server.tool()
def list_agents() -> str:
    """Agentes existentes: nombre, rol, equipo, CLI y modelo."""
    _save("list_agents", {})
    keys = ("name", "role", "team", "cli", "model")
    return json.dumps([{k: a[k] for k in keys} for a in INST["agents"]], ensure_ascii=False)


@server.tool()
def get_agent(name: str) -> str:
    """La ficha completa de un agente existente."""
    _save("get_agent", {"name": name})
    agent = next((a for a in INST["agents"] if a["name"] == name), None)
    return json.dumps(agent or {"error": f"No hay ningún agente {name}"}, ensure_ascii=False)


def _search(items: list[dict], query: str, fields: tuple[str, ...], limit: int = 8) -> list[dict]:
    words = [w for w in query.lower().split() if len(w) > 2]
    scored = []
    for item in items:
        text = " ".join(str(item.get(f, "")) for f in fields).lower()
        score = sum(1 for w in words if w[:5] in text)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:limit]]


@server.tool()
def search_skills(query: str) -> str:
    """Busca skills de la biblioteca por texto (nombre y descripción). Usa varias palabras."""
    _save("search_skills", {"query": query})
    return json.dumps(_search(INST["skills"], query, ("name", "description")), ensure_ascii=False)


@server.tool()
def search_knowledge_docs(query: str) -> str:
    """Busca documentos de conocimiento por texto. Devuelve id, título, nivel y proyecto."""
    _save("search_knowledge_docs", {"query": query})
    return json.dumps(
        _search(INST["docs"], query, ("title", "source", "project")), ensure_ascii=False
    )


@server.tool()
def list_connections() -> str:
    """Conexiones MCP del catálogo, con sus herramientas."""
    _save("list_connections", {})
    return json.dumps(INST["connections"], ensure_ascii=False)


@server.tool()
def search_connection_registry(query: str) -> str:
    """Busca servidores MCP en los registros públicos (para sugerir uno que no está instalado)."""
    _save("search_connection_registry", {"query": query})
    return json.dumps(_search(INST["registry"], query, ("ref", "description")), ensure_ascii=False)


@server.tool()
def list_templates() -> str:
    """Plantillas de agente disponibles."""
    _save("list_templates", {})
    return json.dumps(INST["templates"], ensure_ascii=False)


@server.tool()
def list_projects() -> str:
    """Proyectos y su pipeline actual (etapas con su agente y enlaces)."""
    _save("list_projects", {})
    return json.dumps(INST["projects"], ensure_ascii=False)


# ----------------------------------------------------------------------------- sheet tools
@server.tool()
def get_sheet() -> str:
    """El estado actual de lo que estás diseñando, con los problemas pendientes."""
    _save("get_sheet", {})
    return json.dumps(_summary(), ensure_ascii=False)


@server.tool()
def update_sheet(patch: dict, agent_ref: str = "main") -> str:
    """Cambia campos de la ficha de un agente. `agent_ref` identifica al agente dentro de lo
    que diseñas ("main" si es uno solo; en un equipo, una clave corta como "redactor").
    Campos: name, role, description, color, team, cli, account, model, permission_mode,
    allowed_tools, max_concurrency, can_spawn_subagents, can_create_tasks, can_propose_agents,
    instructions, skills [{name, mode: auto|always|never}], knowledge [ids de documento],
    connections [{name, tools?}], template. Los campos fijados por el usuario y las
    referencias que no existen no se guardan: la respuesta dice por qué."""
    _save("update_sheet", {"patch": patch, "agent_ref": agent_ref})
    sheet = STATE["agents"].setdefault(agent_ref, {})
    refused: dict[str, str] = {}
    for key, value in patch.items():
        if key not in AGENT_FIELDS:
            refused[key] = "campo desconocido"
        elif key in STATE["locked"]:
            refused[key] = "campo fijado por el usuario (usa request_unlock si hace falta)"
        else:
            problem = _check_field(key, value, {**sheet, **patch})
            if problem:
                refused[key] = problem
                STATE["rejected"].append({"field": key, "value": value, "why": problem})
            else:
                sheet[key] = value
    _save("update_sheet:after", {})
    return json.dumps({"refused": refused, **_summary()}, ensure_ascii=False)


@server.tool()
def draft_skill(name: str, description: str, body: str, agent_ref: str = "main") -> str:
    """Propone una skill nueva escrita para este agente (SKILL.md: descripción y cuerpo en
    Markdown). Se aprobará junto con el agente."""
    _save("draft_skill", {"name": name, "description": description, "agent_ref": agent_ref})
    sheet = STATE["agents"].setdefault(agent_ref, {})
    sheet.setdefault("new_skills", []).append(
        {"name": name, "description": description, "body": body}
    )
    return json.dumps(_summary(), ensure_ascii=False)


@server.tool()
def suggest_connection(registry_ref: str, reason: str, agent_ref: str = "main") -> str:
    """Sugiere instalar un servidor MCP de los registros públicos que no está en el catálogo.
    No se instala: el usuario lo hará desde la ficha."""
    _save("suggest_connection", {"registry_ref": registry_ref, "reason": reason})
    known = {r["ref"] for r in INST["registry"]}
    if registry_ref not in known:
        return json.dumps(
            {
                "error": f"{registry_ref} no está en los registros; búscalo con search_connection_registry"
            }
        )
    STATE["suggested_connections"].append(
        {"ref": registry_ref, "reason": reason, "agent_ref": agent_ref}
    )
    return json.dumps({"ok": True})


@server.tool()
def request_unlock(field: str, reason: str) -> str:
    """Pide al usuario que suelte un campo que ha fijado. Se le muestra un botón."""
    _save("request_unlock", {"field": field, "reason": reason})
    STATE["unlock_requests"].append({"field": field, "reason": reason})
    return json.dumps(
        {
            "ok": True,
            "note": "El usuario verá la petición; no cambies el campo hasta que lo suelte.",
        }
    )


@server.tool()
def update_team(name: str = "", description: str = "", existing_team: str = "") -> str:
    """Equipo que diseñas: uno nuevo (name, description) o uno existente (existing_team)."""
    _save("update_team", {"name": name, "description": description, "existing_team": existing_team})
    if existing_team:
        if existing_team not in _names("teams"):
            return json.dumps({"error": f"El equipo {existing_team} no existe"})
        STATE["team"] = {"existing": existing_team}
    else:
        STATE["team"] = {"name": name, "description": description}
    return json.dumps(_summary(), ensure_ascii=False)


@server.tool()
def use_existing_agent(name: str) -> str:
    """Incluye en el equipo un agente que ya existe (sin cambiarlo), para no duplicar roles."""
    _save("use_existing_agent", {"name": name})
    if name not in _names("agents"):
        STATE["rejected"].append({"field": "existing_agent", "value": name, "why": "no existe"})
        return json.dumps({"error": f"No hay ningún agente {name}"})
    if name not in STATE["existing"]:
        STATE["existing"].append(name)
    return json.dumps(_summary(), ensure_ascii=False)


@server.tool()
def set_pipeline(project: str, stages: list[dict], links: list[dict] | None = None) -> str:
    """El pipeline del proyecto. stages: [{name, agent (agent_ref de un agente nuevo o nombre
    de uno existente), requires_review?, reject_to? (índice de una etapa anterior)}].
    links: [{source, target, name?, condition?, always?}] por índice; sin links, cadena lineal.
    Una etapa con varios enlaces de salida es una bifurcación: cada rama necesita condición
    (o always). Las ramas se unen apuntando a la misma etapa."""
    _save("set_pipeline", {"project": project, "stages": stages, "links": links})
    if project not in {p["name"] for p in INST["projects"]}:
        return json.dumps({"error": f"El proyecto {project} no existe"})
    STATE["pipeline"] = {"project": project, "stages": stages, "links": links}
    STATE.setdefault("pipeline_attempts", []).append(_pipeline_issues(STATE["pipeline"]))
    return json.dumps(_summary(), ensure_ascii=False)


app = server.streamable_http_app(streamable_http_path="/mcp")


class Auth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            if headers.get("authorization") != f"Bearer {TOKEN}":
                await PlainTextResponse("unauthorized", status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app = Auth(app)

if __name__ == "__main__":
    _save("start", {})
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
