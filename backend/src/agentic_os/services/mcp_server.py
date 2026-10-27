"""The `agentic-os` MCP server the agent CLIs talk to (ADR 0004 / 0008).

Mounted in the backend at `/r/<token>/mcp`. Every run gets its own token: the gate resolves it
to the run id and passes it to the tools in a header the client can never set itself, so a
token only ever acts on its own run (a model may read the token from its config and call the
server by other means). Unknown tokens, and tokens of finished runs, get 401.

The tool descriptions are in Spanish: the models read them, and the agents work in Spanish.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections.abc import Callable
from typing import Any, Literal, Protocol

import anyio
from mcp.server.mcpserver import Context, MCPServer
from starlette.types import ASGIApp, Receive, Scope, Send

from agentic_os.models.run import Verdict

RUN_HEADER = "x-agentic-os-run"
# /<token>/mcp… once mounted at /r (Starlette strips the mount prefix into root_path).
TOKEN_PATH = re.compile(r"^/([A-Za-z0-9_-]{16,128})(/mcp.*)$")
MAX_TEXT = 4000


AGENT, ARCHITECT = "agent", "architect"  # who a token belongs to


class RunTokens:
    """Per-run bearer tokens, in memory: they die with the run (or the backend). A token is an
    agent's or the Architect's (phase 19): each MCP server only accepts its own kind, so an
    agent cannot edit a sheet and the Architect cannot complete a task."""

    def __init__(self) -> None:
        self._by_token: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def issue(self, run_id: str, kind: str = AGENT) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._by_token[token] = (run_id, kind)
        return token

    def resolve(self, token: str | None, kind: str | None = None) -> str | None:
        """The run of a token; with `kind`, only if the token is of that kind."""
        if not token:
            return None
        with self._lock:
            found = self._by_token.get(token)
        if found is None or (kind is not None and found[1] != kind):
            return None
        return found[0]

    def revoke(self, run_id: str) -> None:
        with self._lock:
            for token in [t for t, (r, _kind) in self._by_token.items() if r == run_id]:
                del self._by_token[token]


class AgentBackend(Protocol):
    """What the tools do; implemented by the RunManager (blocking calls, run in a thread)."""

    def mcp_connected(self, run_id: str) -> None: ...
    def get_context(self, run_id: str) -> str: ...
    def report_status(self, run_id: str, message: str) -> None: ...
    def complete_task(
        self, run_id: str, summary: str, verdict: Verdict, reject_to: str = ""
    ) -> str | None: ...
    def write_project_memory(self, run_id: str, note: str) -> None: ...
    def search_knowledge(self, run_id: str, query: str, limit: int, graph: str) -> str: ...
    def knowledge_map(self, run_id: str, topic: str) -> str: ...
    def related_knowledge(self, run_id: str, document: str, kinds: str, origin: str) -> str: ...
    def explore_knowledge(
        self,
        run_id: str,
        document: str,
        query: str,
        hops: int,
        kinds: str,
        origin: str,
        level: str,
        max_docs: int,
    ) -> str: ...
    def knowledge_path(self, run_id: str, source: str, target: str, max_hops: int) -> str: ...
    def read_knowledge(self, run_id: str, document: str, location: str, part: int) -> str: ...
    def propose_knowledge(
        self,
        run_id: str,
        title: str,
        markdown: str,
        description: str,
        based_on: list[str],
        level: str,
        replaces: str,
    ) -> str: ...
    def use_skill(self, run_id: str, name: str) -> str: ...
    def read_skill_file(self, run_id: str, name: str, path: str) -> str: ...
    def propose_skill(
        self,
        run_id: str,
        name: str,
        description: str,
        body: str,
        files: dict[str, str],
        remove: list[str],
        level: str,
        replaces: str,
        note: str,
    ) -> str: ...
    def request_human(self, run_id: str, title: str, detail: str, options: list[str]) -> str: ...
    def spawn_subagent(self, run_id: str, prompt: str, agent_name: str) -> str: ...
    def create_subtask(self, run_id: str, title: str, description: str, agent_name: str) -> str: ...
    def propose_agent(self, run_id: str, sheet: dict, reason: str) -> str: ...


class TokenGate:
    """ASGI middleware in front of the MCP app: token → run id, or 401."""

    def __init__(
        self,
        app: ASGIApp,
        tokens: RunTokens,
        on_request: Callable[[str], None],
        kind: str = AGENT,
    ) -> None:
        self.app = app
        self.tokens = tokens
        self.on_request = on_request
        self.kind = kind

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        root = scope.get("root_path", "")
        if root and path.startswith(root):
            path = path[len(root) :]
        token, inner = None, path
        match = TOKEN_PATH.match(path)
        if match:
            token, inner = match.group(1), match.group(2)
        headers = [(k, v) for k, v in scope.get("headers") or [] if k != RUN_HEADER.encode()]
        if token is None:
            auth = dict(headers).get(b"authorization", b"").decode()
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        run_id = self.tokens.resolve(token, self.kind)
        if run_id is None:
            await _reject(send)
            return
        # May touch the DB (first request of a run): never on the event loop.
        await anyio.to_thread.run_sync(self.on_request, run_id)
        scope = {
            **scope,
            "path": inner,
            "raw_path": inner.encode(),
            "root_path": "",
            "headers": [*headers, (RUN_HEADER.encode(), run_id.encode())],
        }
        await self.app(scope, receive, send)


async def _reject(send: Send) -> None:
    body = json.dumps({"error": "unknown or expired run token"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _run_id(ctx: Context) -> str:
    run_id = (ctx.headers or {}).get(RUN_HEADER)
    if not run_id:  # unreachable behind the gate
        raise PermissionError("no run")
    return run_id


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def build_mcp(backend: AgentBackend) -> MCPServer:
    server = MCPServer(
        "agentic-os",
        instructions=(
            "Servidor de coordinación de Agentic OS. Usa report_status para contar en qué "
            "estás, write_project_memory para guardar lo que sirva en futuras tareas del "
            "proyecto y complete_task cuando hayas terminado."
        ),
    )

    async def call(fn: Callable[..., Any], *args: Any) -> Any:
        return await anyio.to_thread.run_sync(fn, *args)

    @server.tool()
    async def get_context(ctx: Context) -> str:
        """Devuelve tus instrucciones, la tarea (prompt) y la memoria del proyecto."""
        return await call(backend.get_context, _run_id(ctx))

    @server.tool()
    async def report_status(message: str, ctx: Context) -> str:
        """Informa a Agentic OS (y al humano que observa) de en qué estás trabajando ahora."""
        await call(backend.report_status, _run_id(ctx), _clip(message))
        return "Estado registrado."

    @server.tool()
    async def complete_task(
        summary: str,
        ctx: Context,
        verdict: Literal["approved", "rejected"] = "approved",
        reject_to: str = "",
    ) -> str:
        """Marca tu trabajo como terminado. El resumen debe contar qué has hecho y qué queda
        pendiente. `verdict` solo cambia en las etapas que revisan el trabajo de otras:
        "rejected" devuelve la tarea a la etapa anterior y el resumen debe explicar qué hay que
        corregir. Si tu etapa puede devolver la tarea a varias etapas, `reject_to` es el nombre de
        la que debe rehacerlo. Después de llamarla no sigas trabajando: Agentic OS cerrará la
        sesión."""
        error = await call(
            backend.complete_task,
            _run_id(ctx),
            _clip(summary),
            Verdict(verdict),
            reject_to.strip()[:80],
        )
        if error:
            return error
        return "Tarea completada. Puedes terminar tu turno."

    @server.tool()
    async def request_human(
        title: str, ctx: Context, detail: str = "", options: list[str] | None = None
    ) -> str:
        """Pide algo a la persona: una decisión, un dato o algo que solo ella puede hacer.
        `title` es la pregunta, corta; `detail`, el contexto que necesita para responder; con
        `options` (de 2 a 5 respuestas cortas) es una pregunta de opciones. Llega a su Inbox y como
        notificación. Después, termina tu turno: la respuesta te llegará como un mensaje."""
        return await call(
            backend.request_human,
            _run_id(ctx),
            _clip(title)[:300],
            _clip(detail),
            [_clip(o)[:80] for o in (options or [])][:5],
        )

    @server.tool()
    async def spawn_subagent(prompt: str, ctx: Context, agent: str = "") -> str:
        """Lanza un subagente que trabaja en paralelo, en tu misma carpeta, en una parte
        independiente de la tarea. `prompt`: qué tiene que hacer exactamente; `agent`: el nombre
        de otro agente (vacío: uno como tú). Su resultado te llegará como un mensaje."""
        return await call(backend.spawn_subagent, _run_id(ctx), _clip(prompt), agent.strip())

    @server.tool()
    async def create_subtask(
        title: str, ctx: Context, description: str = "", agent: str = ""
    ) -> str:
        """Crea una tarea nueva en este proyecto, ligada a la tuya, que entra en cola: trabajo
        que debe hacerse después o que hará otro agente (`agent`, por su nombre)."""
        return await call(
            backend.create_subtask, _run_id(ctx), _clip(title)[:200], _clip(description), agent
        )

    @server.tool()
    async def search_knowledge(
        query: str, ctx: Context, limit: int = 8, graph: str = "neighbors"
    ) -> str:
        """Busca en los documentos de conocimiento que la persona te ha dado (manuales,
        especificaciones, páginas web, hojas de cálculo, imágenes…). `query`: una pregunta
        o un código exacto (`ERR_4012`, `/v2/facturas`); devuelve los pasajes más
        relevantes, con su documento y su lugar. `limit`: cuántos resultados directos (1 a 20; el
        grafo puede añadir detrás hasta 3 vecinos más). `graph`: «off»
        (solo la búsqueda), «neighbors» (por defecto: cada resultado lista los documentos
        vecinos y se añaden los vecinos que también responden) o «explore» (además, dibuja
        los documentos cercanos a los mejores resultados)."""
        return await call(backend.search_knowledge, _run_id(ctx), _clip(query), limit, graph)

    @server.tool()
    async def knowledge_map(ctx: Context, topic: str = "") -> str:
        """Mapa de la biblioteca de conocimiento: los TEMAS (grupos de documentos muy
        relacionados), con cuántos documentos tienen, los principales y qué temas tienen
        cerca. Úsalo para orientarte ANTES de buscar. `topic` (opcional): el número o el
        nombre de un tema, para ver todos sus documentos."""
        return await call(backend.knowledge_map, _run_id(ctx), _clip(topic))

    @server.tool()
    async def related_knowledge(
        document: str, ctx: Context, kinds: str = "all", origin: str = "all"
    ) -> str:
        """Los documentos vecinos de uno, con el motivo del vínculo (derivado de, origen de,
        relacionado y su fuerza). `document`: título o identificador. `kinds`: «all»,
        «derived» o «related». `origin`: «all», «user» (lo puso la persona) o «agent»
        (lo propuso un agente)."""
        return await call(
            backend.related_knowledge, _run_id(ctx), _clip(document), _clip(kinds), _clip(origin)
        )

    @server.tool()
    async def explore_knowledge(
        ctx: Context,
        document: str = "",
        query: str = "",
        hops: int = 2,
        kinds: str = "all",
        origin: str = "all",
        level: str = "",
        max_docs: int = 15,
    ) -> str:
        """Recorre el grafo de conocimiento varios saltos desde un documento (`document`) o
        desde los mejores resultados de una búsqueda (`query`) y devuelve los documentos
        alcanzados con el camino que los une. Sirve para encontrar material que la búsqueda
        no da por sí sola (p. ej. la guía derivada de un PDF, o un documento relacionado con
        ella). `hops`: saltos (1 a 3). `kinds`: «all», «derived» o «related». `origin`:
        «all», «user» o «agent». `level`: «general», «project» o «agent». `max_docs`: tope."""
        return await call(
            backend.explore_knowledge,
            _run_id(ctx),
            _clip(document),
            _clip(query),
            hops,
            _clip(kinds),
            _clip(origin),
            _clip(level),
            max_docs,
        )

    @server.tool()
    async def knowledge_path(source: str, target: str, ctx: Context, max_hops: int = 4) -> str:
        """El camino más fuerte entre dos documentos de conocimiento (qué tiene que ver uno
        con otro), o la respuesta de que no hay. `source` y `target`: título o identificador.
        `max_hops`: saltos como máximo (1 a 6)."""
        return await call(
            backend.knowledge_path, _run_id(ctx), _clip(source), _clip(target), max_hops
        )

    @server.tool()
    async def read_knowledge(document: str, ctx: Context, location: str = "", part: int = 1) -> str:
        """Lee un documento de conocimiento. `document`: su título o el identificador que
        aparece entre corchetes. `location` (opcional): una página (`12`), una diapositiva
        (`diapositiva 3`), una hoja (`hoja Ventas`) o el título de un apartado. Los
        documentos largos se leen por partes: `part` indica cuál (la respuesta dice cuántas
        hay)."""
        return await call(
            backend.read_knowledge, _run_id(ctx), _clip(document), _clip(location), part
        )

    @server.tool()
    async def propose_knowledge(
        title: str,
        markdown: str,
        ctx: Context,
        description: str = "",
        based_on: list[str] | None = None,
        level: str = "",
        replaces: str = "",
    ) -> str:
        """Propone un documento de conocimiento NUEVO con algo que has aprendido y que
        ayudaría a otros agentes (una guía, una solución verificada, una síntesis). No
        modifica nunca los documentos existentes: se crea uno aparte, vinculado a los que lo
        inspiraron, y la persona lo revisa antes de que nadie lo use; tú sigues trabajando.
        `title`: título claro. `markdown`: el texto completo en Markdown, autocontenido y
        comprobado (no resúmenes de lo que ya hay escrito). `description`: una línea.
        `based_on`: los documentos en los que te basas (título o identificador). `level`:
        «general», «project» o «agent» si tienes preferencia (decide la persona). `replaces`:
        una propuesta tuya ya aceptada a la que esta sustituye. Hay un máximo de propuestas
        por ejecución; si algo no se puede, la respuesta te explica por qué."""
        return await call(
            backend.propose_knowledge,
            _run_id(ctx),
            _clip(title)[:200],
            markdown.strip(),
            _clip(description),
            [_clip(x)[:200] for x in (based_on or [])][:10],
            _clip(level),
            _clip(replaces),
        )

    @server.tool()
    async def use_skill(ctx: Context, name: str = "") -> str:
        """Carga una skill: instrucciones probadas para un tipo de tarea, que debes seguir.
        `name`: su nombre, tal como sale en la sección «Skills» de tus instrucciones. Sin
        nombre, lista todas las skills que tienes. Devuelve su SKILL.md entero, la carpeta
        donde están sus ficheros (para ejecutar sus scripts) y la lista de esos ficheros."""
        return await call(backend.use_skill, _run_id(ctx), _clip(name)[:120])

    @server.tool()
    async def read_skill_file(name: str, path: str, ctx: Context) -> str:
        """Lee un fichero de apoyo de una skill (una plantilla, un ejemplo, una referencia).
        `name`: la skill. `path`: la ruta del fichero dentro de ella, como la lista
        `use_skill` (p. ej. `reference/forms.md`)."""
        return await call(backend.read_skill_file, _run_id(ctx), _clip(name)[:120], _clip(path))

    @server.tool()
    async def propose_skill(
        ctx: Context,
        name: str = "",
        description: str = "",
        body: str = "",
        files: dict[str, str] | None = None,
        remove: list[str] | None = None,
        level: str = "",
        replaces: str = "",
        note: str = "",
    ) -> str:
        """Propone una skill NUEVA (o una versión nueva de una que ya tienes) con una forma de
        trabajar comprobada y reutilizable que has descubierto; no un resumen de esta tarea. La
        persona la revisa antes de que nadie la use; tú sigues trabajando. `name`: en
        minúsculas con guiones (p. ej. `migraciones-alembic`). `description`: una o dos
        frases que digan qué hace y cuándo usarla (es lo que se usa para elegirla). `body`:
        las instrucciones en Markdown. `files`: ficheros de apoyo {ruta: texto} (plantillas,
        ejemplos, scripts). Para una versión nueva: `replaces` con el nombre de la skill; solo
        envía lo que cambia (`remove`: rutas a quitar). `level`: «general», «project» o
        «agent» si tienes preferencia. `note`: qué aporta o qué cambia. Hay un máximo por
        ejecución; si algo no se puede, la respuesta te explica por qué."""
        return await call(
            backend.propose_skill,
            _run_id(ctx),
            _clip(name)[:64],
            description.strip()[:1_100],
            body,
            {str(k)[:240]: str(v) for k, v in (files or {}).items()},
            [str(p)[:240] for p in (remove or [])][:50],
            _clip(level),
            _clip(replaces)[:120],
            note.strip()[:500],
        )

    @server.tool()
    async def propose_agent(sheet: dict[str, Any], reason: str, ctx: Context) -> str:
        """Propón un agente nuevo para el equipo cuando, trabajando, veas que falta un rol (p. ej.
        «haría falta un traductor para estos textos»). La persona lo revisa antes de que reciba
        tareas; tú sigues con tu tarea. `reason`: por qué hace falta, en una o dos frases.
        `sheet`: su ficha: name, role, description, cli («claude» o «agy»), model,
        permission_mode (autonomous · restricted · ask), allowed_tools, instructions (su
        *system prompt* en Markdown, en segunda persona), skills [{name, mode: always|never}],
        knowledge [título de documento], connections [nombre]. Solo cosas que existan: si algo
        no, la respuesta te dice qué. Como mucho una propuesta por ejecución."""
        return await call(
            backend.propose_agent, _run_id(ctx), dict(sheet or {}), reason.strip()[:1000]
        )

    @server.tool()
    async def write_project_memory(note: str, ctx: Context) -> str:
        """Añade una nota a la memoria del proyecto (decisiones, convenciones, trampas…) para
        que la lean los agentes de futuras tareas. Sé breve y concreto."""
        await call(backend.write_project_memory, _run_id(ctx), _clip(note))
        return "Nota guardada en la memoria del proyecto."

    return server


def mount_app(backend: AgentBackend, tokens: RunTokens) -> tuple[ASGIApp, Any]:
    """The ASGI app to mount at /r, and the MCP session manager to run in the lifespan."""
    server = build_mcp(backend)
    app = server.streamable_http_app(streamable_http_path="/mcp")
    return TokenGate(app, tokens, backend.mcp_connected), server.session_manager
