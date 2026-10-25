"""Testing a connection (phase 18, block 3, CA4): start the server (or call its URL) as an MCP
client, shake hands and list its tools, resources and prompts. Every way it can fail ends in a
code and a sentence in Spanish that says what to do.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import httpx2
import mcp_types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from agentic_os.services.connections.redact import Redactor
from agentic_os.services.connections.render import Rendered

HINTS = {
    ("npx", "node", "npm"): "Falta Node.js: instálalo desde nodejs.org y vuelve a probar.",
    ("uvx", "uv"): "Falta uv: instálalo desde docs.astral.sh/uv y vuelve a probar.",
    ("python", "python3", "py", "pip"): "Falta Python: instálalo desde python.org.",
    ("docker",): "Falta Docker: instala Docker Desktop y arráncalo.",
}
STDERR_LINES = 20


@dataclass
class ProbeError:
    code: str
    message: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


@dataclass
class ProbeResult:
    ok: bool
    seconds: float = 0.0
    server: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)
    error: ProbeError | None = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "seconds": self.seconds,
            "server": self.server,
            "tools": self.tools,
            "resources": self.resources,
            "prompts": self.prompts,
            "error": self.error.as_dict() if self.error else None,
        }


# -- errors -------------------------------------------------------------------------------------
def leaves(error: BaseException) -> Iterator[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        for inner in error.exceptions:
            yield from leaves(inner)
    else:
        yield error


def missing_command_hint(command: str) -> str:
    name = Path(command).stem.lower()
    for names, hint in HINTS.items():
        if name in names:
            return hint
    return f"No se encuentra el programa «{command}»: instálalo o escribe su ruta completa."


def command_problem(command: str) -> ProbeError | None:
    """The command cannot start: not found in the PATH and not an existing path."""
    if not command.strip():
        return ProbeError("command_missing", "Falta el comando del servidor.")
    if shutil.which(command) or Path(command).exists():
        return None
    return ProbeError(
        "command_not_found",
        f"No se encuentra «{command}». {missing_command_hint(command)}",
        command,
    )


def classify(
    errors: list[BaseException], rendered: Rendered, stderr: str, statuses: list[int] | None = None
) -> ProbeError:
    texts = [f"{type(e).__name__}: {e}" for e in errors]
    detail = "; ".join(texts)[:300]
    for error in errors:
        if isinstance(error, TimeoutError):
            return ProbeError(
                "timeout",
                "El servidor no ha respondido a tiempo. Si es la primera vez, puede estar "
                "descargando el paquete: vuelve a probar o sube el tiempo de espera en Ajustes.",
                detail,
            )
    for error in errors:
        if isinstance(error, FileNotFoundError):
            return command_problem(rendered.command) or ProbeError(
                "command_not_found", f"No se encuentra «{rendered.command}».", detail
            )
        if isinstance(error, PermissionError):
            return ProbeError(
                "command_failed",
                f"No se puede ejecutar «{rendered.command}»: faltan permisos.",
                detail,
            )
    # The SDK turns an HTTP error into a generic MCPError: the statuses seen are recorded apart.
    codes = [
        *(statuses or []),
        *(getattr(getattr(e, "response", None), "status_code", None) for e in errors),
    ]
    for status in [s for s in codes if s is not None]:
        if status in (401, 403):
            return ProbeError(
                "unauthorized",
                f"El servidor rechaza las credenciales ({status}). Comprueba el token o la "
                "cabecera, o vuelve a conectar la cuenta.",
                detail,
            )
        if status == 404 and rendered.transport != "stdio":
            return ProbeError(
                "http_error",
                f"La dirección {rendered.url} no existe en el servidor (404): comprueba la URL.",
                detail,
            )
        if status >= 400:
            return ProbeError(
                "http_error", f"El servidor ha respondido con el error {status}.", detail
            )
    for error in errors:
        name = type(error).__name__
        if isinstance(error, (httpx2.ConnectError, OSError)) or name in (
            "ConnectError",
            "ConnectTimeout",
            "ReadTimeout",
            "RemoteProtocolError",
        ):
            return ProbeError(
                "unreachable",
                f"No se puede conectar con {rendered.url or 'el servidor'}. Comprueba la "
                "dirección y tu conexión a internet.",
                detail,
            )
    if rendered.transport == "stdio" and stderr:
        return ProbeError(
            "crashed",
            "El servidor se ha cerrado nada más arrancar. Esto es lo último que ha escrito:\n"
            + stderr,
            detail,
        )
    if any("closed" in str(e).lower() or "EOF" in str(e) for e in errors):
        return ProbeError(
            "crashed",
            "El servidor se ha cerrado antes de responder."
            + (f" Esto es lo último que ha escrito:\n{stderr}" if stderr else ""),
            detail,
        )
    return ProbeError(
        "protocol",
        "El servidor no habla el protocolo MCP como se esperaba. "
        + (detail[:160] if detail else ""),
        detail,
    )


# -- the probe ----------------------------------------------------------------------------------
def _tool(tool: Any) -> dict:
    notes = getattr(tool, "annotations", None)
    return {
        "name": tool.name,
        "description": (tool.description or "")[:2000],
        "input_schema": getattr(tool, "input_schema", None) or {},
        "read_only": getattr(notes, "read_only_hint", None),
        "destructive": getattr(notes, "destructive_hint", None),
    }


async def _listing(session: ClientSession, method: str, attribute: str) -> list[Any]:
    """Every page of a list. A server without that capability answers with an error: empty."""
    items: list[Any] = []
    cursor = None
    try:
        for _ in range(50):
            params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
            page = await getattr(session, method)(params=params)
            items.extend(getattr(page, attribute))
            cursor = page.next_cursor
            if not cursor:
                break
    except Exception:
        return items
    return items


async def _talk(read, write) -> ProbeResult:
    async with ClientSession(read, write) as session:
        initialized = await session.initialize()
        info = initialized.server_info
        tools = []
        cursor = None
        for _ in range(50):
            page = await session.list_tools(
                params=types.PaginatedRequestParams(cursor=cursor) if cursor else None
            )
            tools.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                break
        resources = await _listing(session, "list_resources", "resources")
        prompts = await _listing(session, "list_prompts", "prompts")
    return ProbeResult(
        ok=True,
        server={"name": info.name, "version": info.version},
        tools=[_tool(t) for t in tools],
        resources=[
            {"name": r.name, "uri": str(r.uri), "description": r.description or ""}
            for r in resources
        ],
        prompts=[{"name": p.name, "description": p.description or ""} for p in prompts],
    )


def _tail(handle, redactor: Redactor) -> str:
    handle.flush()
    handle.seek(0)
    lines = handle.read().replace("\r", "").strip().splitlines()[-STDERR_LINES:]
    return redactor.feed("\n".join(lines)) + redactor.flush()


async def probe(rendered: Rendered, timeout: float, auth: httpx2.Auth | None = None) -> ProbeResult:
    """Runs the test. Never raises: a failure is a result with an `error`."""
    started = time.monotonic()
    redactor = Redactor(rendered.secret_values)
    if rendered.transport == "stdio":
        problem = command_problem(rendered.command)
        if problem is not None:
            return ProbeResult(ok=False, error=problem)
    statuses: list[int] = []

    async def note(response: httpx2.Response) -> None:
        if response.status_code >= 400:
            statuses.append(response.status_code)

    errlog = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")  # noqa: SIM115
    try:
        with anyio.fail_after(timeout):
            if rendered.transport == "stdio":
                params = StdioServerParameters(
                    command=rendered.command,
                    args=rendered.args,
                    env=rendered.env or None,
                )
                async with stdio_client(params, errlog=errlog) as (read, write):
                    result = await _talk(read, write)
            elif rendered.transport == "sse":

                def factory(headers=None, timeout=None, auth=None) -> httpx2.AsyncClient:
                    return httpx2.AsyncClient(
                        headers=headers,
                        timeout=timeout or httpx2.Timeout(30, read=300),
                        auth=auth,
                        event_hooks={"response": [note]},
                    )

                async with sse_client(
                    rendered.url,
                    headers=rendered.headers or None,
                    auth=auth,
                    httpx_client_factory=factory,
                ) as (read, write):
                    result = await _talk(read, write)
            else:
                async with (
                    httpx2.AsyncClient(
                        headers=rendered.headers or None,
                        auth=auth,
                        timeout=timeout,
                        event_hooks={"response": [note]},
                    ) as http,
                    streamable_http_client(rendered.url, http_client=http) as (read, write),
                ):
                    result = await _talk(read, write)
        result.seconds = round(time.monotonic() - started, 1)
        return result
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        stderr = _tail(errlog, redactor)
        found = classify(list(leaves(error)), rendered, stderr, statuses)
        found.message = redactor.feed(found.message) + redactor.flush()
        found.detail = Redactor(rendered.secret_values).feed(found.detail)
        return ProbeResult(ok=False, seconds=round(time.monotonic() - started, 1), error=found)
    finally:
        with contextlib.suppress(OSError):
            errlog.close()


# -- background tests ---------------------------------------------------------------------------
@dataclass
class Test:
    id: str
    connection_id: str
    state: str = "running"  # running, done or cancelled
    result: ProbeResult | None = None
    started_at: float = field(default_factory=time.monotonic)
    _loop: asyncio.AbstractEventLoop | None = None
    _task: asyncio.Task | None = None
    done: threading.Event = field(default_factory=threading.Event)


class ProbeRunner:
    """Runs the tests in the background, one thread each, and can cancel them."""

    def __init__(self) -> None:
        self._tests: dict[str, Test] = {}
        self._lock = threading.Lock()

    def start(
        self, connection_id: str, rendered: Rendered, timeout: float, auth=None, on_done=None
    ):
        test = Test(id=str(uuid.uuid4()), connection_id=connection_id)
        with self._lock:
            self._tests[test.id] = test
            for old in [t for t in self._tests.values() if t.done.is_set()][:-20]:
                self._tests.pop(old.id, None)

        def work() -> None:
            async def main() -> None:
                test._loop = asyncio.get_running_loop()
                test._task = asyncio.current_task()
                try:
                    test.result = await probe(rendered, timeout, auth)
                    if on_done is not None:  # keeps the result before anybody is told it is done
                        with contextlib.suppress(Exception):
                            on_done(test)
                    test.state = "done"
                except asyncio.CancelledError:
                    test.state = "cancelled"

            try:
                asyncio.run(main())
            except Exception:
                test.state = "done"
            finally:
                test.done.set()

        threading.Thread(target=work, name=f"mcp-test-{test.id[:8]}", daemon=True).start()
        return test

    def get(self, test_id: str) -> Test | None:
        return self._tests.get(test_id)

    def cancel(self, test_id: str) -> bool:
        test = self._tests.get(test_id)
        if test is None or test.done.is_set():
            return False
        if test._loop is not None and test._task is not None:
            test._loop.call_soon_threadsafe(test._task.cancel)
        return True
