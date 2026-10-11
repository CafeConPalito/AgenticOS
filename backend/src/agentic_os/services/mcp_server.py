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


class RunTokens:
    """Per-run bearer tokens, in memory: they die with the run (or the backend)."""

    def __init__(self) -> None:
        self._by_token: dict[str, str] = {}
        self._lock = threading.Lock()

    def issue(self, run_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._by_token[token] = run_id
        return token

    def resolve(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            return self._by_token.get(token)

    def revoke(self, run_id: str) -> None:
        with self._lock:
            for token in [t for t, r in self._by_token.items() if r == run_id]:
                del self._by_token[token]


class AgentBackend(Protocol):
    """What the tools do; implemented by the RunManager (blocking calls, run in a thread)."""

    def mcp_connected(self, run_id: str) -> None: ...
    def get_context(self, run_id: str) -> str: ...
    def report_status(self, run_id: str, message: str) -> None: ...
    def complete_task(self, run_id: str, summary: str, verdict: Verdict) -> str | None: ...
    def write_project_memory(self, run_id: str, note: str) -> None: ...
    def request_human(self, run_id: str, title: str, detail: str, options: list[str]) -> str: ...


class TokenGate:
    """ASGI middleware in front of the MCP app: token → run id, or 401."""

    def __init__(self, app: ASGIApp, tokens: RunTokens, on_request: Callable[[str], None]) -> None:
        self.app = app
        self.tokens = tokens
        self.on_request = on_request

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
        run_id = self.tokens.resolve(token)
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
        summary: str, ctx: Context, verdict: Literal["approved", "rejected"] = "approved"
    ) -> str:
        """Marca tu trabajo como terminado. El resumen debe contar qué has hecho y qué queda
        pendiente. `verdict` solo cambia en las etapas que revisan el trabajo de otras:
        "rejected" devuelve la tarea a la etapa anterior y el resumen debe explicar qué hay que
        corregir. Después de llamarla no sigas trabajando: Agentic OS cerrará la sesión."""
        error = await call(backend.complete_task, _run_id(ctx), _clip(summary), Verdict(verdict))
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
