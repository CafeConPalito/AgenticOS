"""The Architect's MCP servers (phase 19, plan §4 and change 4).

Two tool sets, each its own server under `/a/<set>/mcp`: «agent» (design or improve one agent)
and «team» (also teams and pipelines). In spike S3 the model, designing one agent, put it into
a pipeline nobody asked for: it only gets the tools of its job. Tokens are the Architect's
(`RunTokens` kind «architect»): an agent's token gets a 401 here, and an Architect's one gets a
401 at `/r`. Every tool runs in a thread and goes to `ArchitectBackend.call_tool`, which only
reads the installation and writes the sheet of the token's conversation.

The descriptions are in Spanish: the model reads them, and it talks to the person in Spanish.
"""

from __future__ import annotations

from typing import Any, Protocol

import anyio
from mcp.server.mcpserver import Context, MCPServer
from starlette.types import ASGIApp, Receive, Scope, Send

from agentic_os.services.mcp_server import ARCHITECT, RUN_HEADER, RunTokens, TokenGate

AGENT, TEAM = "agent", "team"
TOOLSETS = (AGENT, TEAM)


class ArchitectBackend(Protocol):
    def mcp_connected(self, run_id: str) -> None: ...
    def call_tool(self, run_id: str, name: str, args: dict[str, Any]) -> str: ...


def _run_id(ctx: Context) -> str:
    run_id = (ctx.headers or {}).get(RUN_HEADER)
    if not run_id:  # unreachable behind the gate
        raise PermissionError("no run")
    return run_id


def build(backend: ArchitectBackend, toolset: str) -> MCPServer:
    server = MCPServer(
        "architect",
        instructions=(
            "Herramientas del Agente Arquitecto de Agentic OS: consultar lo que hay instalado "
            "y rellenar la ficha que el usuario ve en vivo. No cambian nada fuera de la ficha."
        ),
    )

    async def call(ctx: Context, tool: str, /, **args: Any) -> str:
        # `tool` is positional-only: some tools have an argument called `name` of their own.
        return await anyio.to_thread.run_sync(backend.call_tool, _run_id(ctx), tool, args)

    # ------------------------------------------------------------------------ reading
    @server.tool()
    async def list_clis(ctx: Context) -> str:
        """CLIs instalados, con sus cuentas (id y nombre), los modelos que admite cada uno y las
        herramientas que se pueden permitir a un agente."""
        return await call(ctx, "list_clis")

    @server.tool()
    async def list_teams(ctx: Context) -> str:
        """Equipos existentes."""
        return await call(ctx, "list_teams")

    @server.tool()
    async def list_agents(ctx: Context) -> str:
        """Agentes existentes: nombre, rol, equipo, CLI, modelo y estado."""
        return await call(ctx, "list_agents")

    @server.tool()
    async def get_agent(name: str, ctx: Context) -> str:
        """La ficha completa de un agente existente (por nombre o id)."""
        return await call(ctx, "get_agent", name=name)

    @server.tool()
    async def search_skills(query: str, ctx: Context) -> str:
        """Busca skills de la biblioteca por texto (nombre y descripción); devuelve las 8 que
        mejor encajan. Usa varias palabras del tema."""
        return await call(ctx, "search_skills", query=query)

    @server.tool()
    async def search_knowledge_docs(query: str, ctx: Context) -> str:
        """Busca documentos de conocimiento por texto; devuelve los 8 que mejor encajan con su
        id, título, nivel (general, proyecto o agente) y proyecto."""
        return await call(ctx, "search_knowledge_docs", query=query)

    @server.tool()
    async def list_connections(ctx: Context) -> str:
        """Conexiones MCP activas del catálogo: nombre, descripción y número de herramientas."""
        return await call(ctx, "list_connections")

    @server.tool()
    async def get_connection(name: str, ctx: Context) -> str:
        """Una conexión del catálogo con sus herramientas."""
        return await call(ctx, "get_connection", name=name)

    @server.tool()
    async def search_connection_registry(query: str, ctx: Context) -> str:
        """Busca servidores MCP en los registros públicos, para sugerir uno que no está en el
        catálogo. Devuelve `registry_ref` para suggest_connection."""
        return await call(ctx, "search_connection_registry", query=query)

    @server.tool()
    async def list_owls(ctx: Context) -> str:
        """Los búhos de la galería para la imagen del agente (campo `avatar`, «owl:<id>»).
        Elige uno que encaje con su rol; si no encaja ninguno, déjalo en null (iniciales)."""
        return await call(ctx, "list_owls")

    @server.tool()
    async def list_templates(ctx: Context) -> str:
        """Plantillas de agente: las fijas y las del usuario."""
        return await call(ctx, "list_templates")

    @server.tool()
    async def get_template(template: str, ctx: Context) -> str:
        """Una plantilla completa (por id o nombre), para partir de ella."""
        return await call(ctx, "get_template", template=template)

    @server.tool()
    async def get_sheet(ctx: Context) -> str:
        """Lo que estás diseñando ahora: la ficha, los campos fijados por el usuario, los
        problemas pendientes y lo completa que está."""
        return await call(ctx, "get_sheet")

    # ------------------------------------------------------------------------ the sheet
    @server.tool()
    async def update_sheet(patch: dict[str, Any], ctx: Context, agent_ref: str = "main") -> str:
        """Cambia campos de la ficha de un agente. `agent_ref`: «main» si diseñas uno solo; en
        un equipo, una clave corta por agente («redactor»). Campos: name, role, description,
        color (#RRGGBB), avatar (owl:<id> de list_owls), team, cli, account, model,
        permission_mode (autonomous · restricted ·
        ask), allowed_tools, max_concurrency (1-5), can_spawn_subagents, can_create_tasks,
        can_propose_agents, instructions, skills [{name, mode: always|never}], knowledge
        [título o id de documento], connections [nombre], template. Lo que no existe y los
        campos fijados por el usuario no se guardan: la respuesta dice por qué."""
        return await call(ctx, "update_sheet", patch=patch, agent_ref=agent_ref)

    @server.tool()
    async def draft_skill(
        name: str, description: str, body: str, ctx: Context, agent_ref: str = "main"
    ) -> str:
        """Escribe una skill nueva para este agente: `name` en minúsculas con guiones,
        `description` (qué hace y cuándo usarla) y `body` (instrucciones en Markdown). Se
        aprueba junto con el agente."""
        return await call(
            ctx, "draft_skill", name=name, description=description, body=body, agent_ref=agent_ref
        )

    @server.tool()
    async def suggest_connection(
        registry_ref: str, reason: str, ctx: Context, agent_ref: str = "main"
    ) -> str:
        """Sugiere instalar un servidor MCP que no está en el catálogo (`registry_ref` de
        search_connection_registry). No se instala: el usuario lo hará desde la ficha."""
        return await call(
            ctx, "suggest_connection", registry_ref=registry_ref, reason=reason, agent_ref=agent_ref
        )

    @server.tool()
    async def request_unlock(field: str, reason: str, ctx: Context) -> str:
        """Pide al usuario que suelte un campo que ha fijado (p. ej. «main.color»). Verá un
        botón; no cambies el campo hasta que lo suelte."""
        return await call(ctx, "request_unlock", field=field, reason=reason)

    if toolset != TEAM:
        return server

    # ------------------------------------------------------------------- teams and pipelines
    @server.tool()
    async def list_projects(ctx: Context) -> str:
        """Proyectos y su pipeline actual (etapas con su agente y enlaces)."""
        return await call(ctx, "list_projects")

    @server.tool()
    async def set_team(ctx: Context, name: str = "", description: str = "", team: str = "") -> str:
        """El equipo que diseñas: uno nuevo (`name`, `description`) o uno existente (`team`)."""
        return await call(ctx, "set_team", name=name, description=description, team=team)

    @server.tool()
    async def use_existing_agent(name: str, ctx: Context) -> str:
        """Incluye en el equipo un agente que ya existe (sin cambiarlo), para no duplicar roles."""
        return await call(ctx, "use_existing_agent", name=name)

    @server.tool()
    async def remove_agent(agent_ref: str, ctx: Context) -> str:
        """Quita del diseño un agente nuevo (`agent_ref`) o uno existente (su nombre)."""
        return await call(ctx, "remove_agent", agent_ref=agent_ref)

    @server.tool()
    async def set_pipeline(
        project: str,
        stages: list[dict[str, Any]],
        ctx: Context,
        links: list[dict[str, Any]] | None = None,
        max_rejections: int | None = None,
    ) -> str:
        """El pipeline completo de un proyecto existente. `stages`: [{name, agent (agent_ref de
        un agente nuevo o nombre de uno existente), requires_review?, reject_to? (índice de una
        etapa anterior a la que vuelve el trabajo rechazado), id? (para conservar una etapa que
        ya existía)}]. `links`: [{source, target, name?, condition?}] por índice; sin links, una
        cadena. Una etapa con varios enlaces de salida es una bifurcación: una rama sin condición
        se hace siempre, una con condición solo si la tarea la cumple, y las ramas se vuelven a
        unir en una misma etapa."""
        return await call(
            ctx,
            "set_pipeline",
            project=project,
            stages=stages,
            links=links,
            max_rejections=max_rejections,
        )

    return server


class ArchitectGateway:
    """`/a/<set>/…` → the gate of that tool set. Starlette leaves the mount in `root_path`."""

    def __init__(self, gates: dict[str, ASGIApp]) -> None:
        self.gates = gates

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path, root = scope["path"], scope.get("root_path", "")
        inner = path[len(root) :] if root and path.startswith(root) else path
        toolset = inner.strip("/").split("/", 1)[0]
        gate = self.gates.get(toolset)
        if gate is None:
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await gate({**scope, "root_path": f"{root}/{toolset}"}, receive, send)


def mount(backend: ArchitectBackend, tokens: RunTokens) -> tuple[ASGIApp, list[Any]]:
    """The ASGI app to mount at /a, and the MCP session managers to run in the lifespan."""
    gates, managers = {}, []
    for toolset in TOOLSETS:
        server = build(backend, toolset)
        app = server.streamable_http_app(streamable_http_path="/mcp")
        gates[toolset] = TokenGate(app, tokens, backend.mcp_connected, kind=ARCHITECT)
        managers.append(server.session_manager)
    return ArchitectGateway(gates), managers
