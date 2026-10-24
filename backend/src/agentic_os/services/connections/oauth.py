"""The OAuth login of the connections that need one (phase 18, block 6, CA8).

The app does the standard MCP flow with the SDK's own provider (spike S3): it finds the
authorization server, registers itself (dynamic registration) or uses the client id the person
pasted, sends the person to the browser with PKCE and takes the answer on a loopback port. The
tokens live in the credential store under reserved keys, never in the database; a run only ever
receives the access token, never the refresh token.

A token that is about to expire is renewed before a run starts. If the renewal fails the
connection is marked «hay que volver a conectar», the Inbox says so and the runs go on without it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import structlog
import uvicorn
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

from agentic_os.models import (
    InboxItem,
    InboxKind,
    InboxStatus,
    McpConnection,
    McpOAuth,
    OAuthStatus,
    Resolution,
)
from agentic_os.services import inbox
from agentic_os.services.connections import config as connection_config
from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_

log = structlog.get_logger()

TOKENS_KEY = "_oauth_tokens"
CLIENT_KEY = "_oauth_client"
REFRESH_MARGIN = 600  # seconds: a token that dies sooner is renewed before a run
FLOW_TIMEOUT = 300  # seconds the person has to finish in the browser
DONE_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>Agentic OS</title>"
    "<body style='font-family:system-ui;margin:3rem'><h2>Ya puedes volver a Agentic OS</h2>"
    "<p>La cuenta está conectada. Puedes cerrar esta pestaña.</p></body>"
)
FAILED_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>Agentic OS</title>"
    "<body style='font-family:system-ui;margin:3rem'><h2>No se ha podido conectar</h2>"
    "<p>{reason}</p></body>"
)


class NeedsLogin(Exception):
    """The person has to connect the account (again). `message` says it in Spanish."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# -- the credential store -----------------------------------------------------------------------
def stored_tokens(connection_id: str) -> dict | None:
    raw = secrets.get(connection_id, TOKENS_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def stored_client(connection_id: str) -> dict:
    raw = secrets.get(connection_id, CLIENT_KEY)
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def forget(connection_id: str) -> None:
    secrets.delete(connection_id, TOKENS_KEY)
    secrets.delete(connection_id, CLIENT_KEY)


class TokenStore:
    """The SDK's `TokenStorage` over the credential store."""

    def __init__(self, connection_id: str, client_info: OAuthClientInformationFull | None = None):
        self.connection_id = connection_id
        self.client_info = client_info
        self.tokens_set = 0

    async def get_tokens(self) -> OAuthToken | None:
        data = stored_tokens(self.connection_id)
        if not data or not data.get("access_token"):
            return None
        return OAuthToken(
            access_token=data["access_token"],
            token_type="Bearer",
            expires_in=None,  # the expiry is set by the provider below, from `expires_at`
            scope=data.get("scope"),
            refresh_token=data.get("refresh_token"),
        )

    async def set_tokens(self, tokens: OAuthToken) -> None:
        now = time.time()
        previous = stored_tokens(self.connection_id) or {}
        data = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or previous.get("refresh_token"),
            "scope": tokens.scope or previous.get("scope"),
            "obtained_at": now,
            "expires_at": now + tokens.expires_in if tokens.expires_in else None,
        }
        secrets.put(self.connection_id, TOKENS_KEY, json.dumps(data))
        self.tokens_set += 1

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if self.client_info is not None:
            return self.client_info
        info = stored_client(self.connection_id).get("info")
        return OAuthClientInformationFull.model_validate(info) if info else None

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        self.client_info = info
        saved = stored_client(self.connection_id)
        saved["info"] = info.model_dump(mode="json")
        secrets.put(self.connection_id, CLIENT_KEY, json.dumps(saved))


class Provider(OAuthClientProvider):
    """The SDK's provider, told when the stored token expires so that it renews it in time
    (the SDK only knows the lifetime of a token it has just received)."""

    def __init__(self, *args, connection_id: str, margin: float = REFRESH_MARGIN, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._connection_id = connection_id
        self._margin = margin

    async def _initialize(self) -> None:
        await super()._initialize()
        data = stored_tokens(self._connection_id) or {}
        if data.get("expires_at"):
            self.context.token_expiry_time = float(data["expires_at"]) - self._margin


def _metadata(redirect_uri: str, secret: bool) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        client_name="Agentic OS",
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="client_secret_post" if secret else "none",
    )


async def _never_interactive(_url: str) -> None:
    raise NeedsLogin("Hay que volver a conectar la cuenta.")


def _leaves(error: BaseException):
    if isinstance(error, BaseExceptionGroup):
        for inner in error.exceptions:
            yield from _leaves(inner)
    else:
        yield error


# -- renewing -----------------------------------------------------------------------------------
def provider_for(connection: McpConnection, margin: float = REFRESH_MARGIN) -> Provider:
    """The provider that sends (and renews) the stored token. It never opens a browser: a
    login that is no longer valid is reported as `NeedsLogin`."""
    return Provider(
        connection.url,
        _metadata("http://127.0.0.1/callback", False),
        TokenStore(connection.id),
        redirect_handler=_never_interactive,
        callback_handler=None,
        connection_id=connection.id,
        margin=margin,
    )


async def _refresh(connection: McpConnection, margin: float = REFRESH_MARGIN) -> None:
    """One authenticated request: the provider renews the token first if it has to, and the
    new tokens are kept through `TokenStore`. Never opens a browser."""
    provider = provider_for(connection, margin)
    async with (
        httpx2.AsyncClient(auth=provider, timeout=30) as http,
        streamable_http_client(connection.url, http_client=http) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()


def _run_sync(coro, timeout: float = 90):
    """Runs a coroutine from any thread, also one that already has a running loop."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout)


def expires_soon(connection_id: str, margin: float = REFRESH_MARGIN) -> bool:
    tokens = stored_tokens(connection_id)
    if not tokens:
        return True
    expires = tokens.get("expires_at")
    return bool(expires) and float(expires) - time.time() < margin


def renew(db: Session, connection: McpConnection, margin: float = REFRESH_MARGIN) -> None:
    """Renews the token of a connected account now. Raises `NeedsLogin` (after marking the
    connection and telling the Inbox) if it cannot."""
    try:
        _run_sync(_refresh(connection, margin))
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        reasons = [str(e) for e in _leaves(error) if isinstance(e, NeedsLogin)]
        log.info("oauth renewal failed", connection=connection.name, error=repr(error)[:200])
        message = (
            reasons[0]
            if reasons
            else f"Hay que volver a conectar la cuenta de «{connection.name}»."
        )
        mark_needs_login(db, connection, message)
        raise NeedsLogin(message) from error
    login = db.get(McpOAuth, connection.id)
    tokens = stored_tokens(connection.id) or {}
    if login is not None and tokens.get("expires_at"):
        login.expires_at = datetime.fromtimestamp(float(tokens["expires_at"]), UTC)
    db.flush()


def access_token(db: Session, connection: McpConnection) -> str:
    """The access token a run sends as `Authorization: Bearer`, renewed first if it is about
    to expire. Raises `NeedsLogin`."""
    login = db.get(McpOAuth, connection.id)
    if login is None or login.status == OAuthStatus.DISCONNECTED:
        raise NeedsLogin(f"Conecta la cuenta de «{connection.name}» para poder usarla.")
    if login.status == OAuthStatus.NEEDS_REAUTH:
        raise NeedsLogin(f"Hay que volver a conectar la cuenta de «{connection.name}».")
    tokens = stored_tokens(connection.id)
    if not tokens or not tokens.get("access_token"):
        mark_needs_login(
            db, connection, f"Hay que volver a conectar la cuenta de «{connection.name}»."
        )
        raise NeedsLogin(f"Hay que volver a conectar la cuenta de «{connection.name}».")
    if expires_soon(connection.id) and tokens.get("refresh_token"):
        renew(db, connection)
        tokens = stored_tokens(connection.id) or tokens
    elif expires_soon(connection.id, 0):
        message = f"Hay que volver a conectar la cuenta de «{connection.name}»."
        mark_needs_login(db, connection, message)
        raise NeedsLogin(message)
    return str(tokens["access_token"])


# -- the state of the login and the Inbox -------------------------------------------------------
def _alert_items(db: Session, connection_id: str) -> list[InboxItem]:
    return list(
        db.scalars(
            select(InboxItem).where(
                InboxItem.kind == InboxKind.CONNECTION,
                InboxItem.connection_id == connection_id,
                InboxItem.status == InboxStatus.PENDING,
            )
        )
    )


def mark_needs_login(db: Session, connection: McpConnection, message: str) -> None:
    login = db.get(McpOAuth, connection.id)
    if login is None:
        login = McpOAuth(connection_id=connection.id)
        db.add(login)
    login.status = OAuthStatus.NEEDS_REAUTH
    if not _alert_items(db, connection.id):
        inbox.create(
            db,
            InboxKind.CONNECTION,
            f"Vuelve a conectar «{connection.name}»",
            message,
            connection_id=connection.id,
        )
    db.flush()


def clear_alerts(db: Session, connection_id: str) -> None:
    for item in _alert_items(db, connection_id):
        inbox.resolve(db, item, Resolution.DISMISSED)


def disconnect(db: Session, connection: McpConnection) -> None:
    """Revokes the token where the service allows it, forgets it and the login."""
    login = db.get(McpOAuth, connection.id)
    tokens = stored_tokens(connection.id) or {}
    saved = stored_client(connection.id)
    endpoint = (saved.get("meta") or {}).get("revocation_endpoint")
    token = tokens.get("refresh_token") or tokens.get("access_token")
    if endpoint and token:
        info = saved.get("info") or {}
        data = {"token": token, "client_id": info.get("client_id", "")}
        if info.get("client_secret"):
            data["client_secret"] = info["client_secret"]
        with contextlib.suppress(httpx.HTTPError):
            httpx.post(endpoint, data=data, timeout=10)
    secrets.delete(connection.id, TOKENS_KEY)
    if login is not None:
        if not login.client_pasted:  # a pasted client stays: it was typed in by the person
            secrets.delete(connection.id, CLIENT_KEY)
        login.status = OAuthStatus.DISCONNECTED
        login.account_label = ""
        login.expires_at = None
    clear_alerts(db, connection.id)
    db.flush()


def renew_expiring(factory: sessionmaker, within: float = 2 * 3600) -> int:
    """The accounts whose token dies within `within` seconds are renewed. Returns how many."""
    count = 0
    with factory() as db:
        for login in list(
            db.scalars(select(McpOAuth).where(McpOAuth.status == OAuthStatus.CONNECTED))
        ):
            connection = db.get(McpConnection, login.connection_id)
            if connection is None or not expires_soon(connection.id, within):
                continue
            try:
                renew(db, connection, within)
                count += 1
            except NeedsLogin:
                pass
            db.commit()
    return count


class Renewer:
    """Renews the tokens that are about to expire, every half hour, in the background."""

    def __init__(self, factory: sessionmaker, every: float = 1800) -> None:
        self._factory = factory
        self._every = every
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mcp-oauth-renewer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._every):
            try:
                renew_expiring(self._factory)
            except Exception:
                log.exception("renewing the MCP tokens failed")


# -- connecting ---------------------------------------------------------------------------------
@dataclass
class Flow:
    id: str
    connection_id: str
    state: str = "starting"  # starting, waiting (for the person), done, failed or cancelled
    authorization_url: str = ""
    redirect_uri: str = ""
    error: str = ""
    pasted: bool = False
    got_url: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    _loop: asyncio.AbstractEventLoop | None = None
    _task: asyncio.Task | None = None


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _random_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FlowManager:
    """The logins in progress: one thread each, with its own loop and loopback listener."""

    def __init__(self, factory: sessionmaker) -> None:
        self._factory = factory
        self._flows: dict[str, Flow] = {}
        self._lock = threading.Lock()

    def get(self, flow_id: str) -> Flow | None:
        return self._flows.get(flow_id)

    def cancel(self, flow_id: str) -> bool:
        flow = self._flows.get(flow_id)
        if flow is None or flow.done.is_set():
            return False
        if flow._loop is not None and flow._task is not None:
            flow._loop.call_soon_threadsafe(flow._task.cancel)
        return True

    def start(
        self,
        connection: McpConnection,
        port: int,
        client_id: str = "",
        client_secret: str = "",
    ) -> Flow:
        """Starts the login and returns once the page to open is known (or it failed)."""
        pasted = bool(client_id.strip())
        flow = Flow(id=str(uuid.uuid4()), connection_id=connection.id, pasted=pasted)
        wanted_port = port
        if not port_free(port):
            if pasted:
                raise ConnectionError_(
                    "oauth_port_busy",
                    f"El puerto {port} está ocupado y el servicio exige esa dirección de "
                    "retorno exacta. Libera el puerto o cámbialo en Ajustes › Conexiones "
                    "(y registra la nueva dirección en el servicio).",
                    port=port,
                )
            wanted_port = _random_port()  # dynamic registration accepts any loopback port
        with self._lock:
            self._flows[flow.id] = flow
            for old in [f for f in self._flows.values() if f.done.is_set()][:-20]:
                self._flows.pop(old.id, None)
        details = (connection.id, connection.name, connection.url, connection.transport)

        def work() -> None:
            asyncio.run(
                self._run(flow, details, wanted_port, client_id.strip(), client_secret.strip())
            )

        threading.Thread(target=work, name=f"mcp-oauth-{flow.id[:8]}", daemon=True).start()
        flow.got_url.wait(30)
        if not flow.got_url.is_set() and flow.state == "starting":
            self.cancel(flow.id)
            flow.state, flow.error = "failed", "El servicio no ha respondido a tiempo."
        return flow

    async def _run(
        self,
        flow: Flow,
        details: tuple[str, str, str, str],
        port: int,
        client_id: str,
        client_secret: str,
    ) -> None:
        connection_id, name, url, _transport = details
        flow._loop, flow._task = asyncio.get_running_loop(), asyncio.current_task()
        code: asyncio.Future[AuthorizationCodeResult] = asyncio.get_running_loop().create_future()
        listener = await _listen(port, code)
        flow.redirect_uri = f"http://127.0.0.1:{port}/callback"
        if client_id:
            info = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=client_secret or None,
                redirect_uris=[flow.redirect_uri],
                token_endpoint_auth_method="client_secret_post" if client_secret else "none",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            )
            storage = TokenStore(connection_id, info)
            await storage.set_client_info(info)
        else:
            secrets.delete(connection_id, CLIENT_KEY)  # a new registration for this address
            storage = TokenStore(connection_id)
        secrets.delete(connection_id, TOKENS_KEY)

        async def redirect_handler(authorization_url: str) -> None:
            flow.authorization_url, flow.state = authorization_url, "waiting"
            flow.got_url.set()

        async def callback_handler() -> AuthorizationCodeResult:
            return await asyncio.wait_for(code, FLOW_TIMEOUT)

        provider = Provider(
            url,
            _metadata(flow.redirect_uri, bool(client_secret)),
            storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
            connection_id=connection_id,
        )
        try:
            async with (
                httpx2.AsyncClient(auth=provider, timeout=30) as http,
                streamable_http_client(url, http_client=http) as (read, write),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
            self._finish(
                flow,
                connection_id,
                provider,
                storage,
                initialized.server_info.name,
                bool(client_id),
            )
        except asyncio.CancelledError:
            flow.state = "cancelled"
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            flow.state, flow.error = "failed", _explain(error, name)
            secrets.delete(connection_id, TOKENS_KEY)
            log.info("oauth login failed", connection=name, error=repr(error)[:300])
        finally:
            flow.got_url.set()
            flow.done.set()
            listener.should_exit = True

    def _finish(
        self,
        flow: Flow,
        connection_id: str,
        provider: Provider,
        storage: TokenStore,
        server_name: str,
        pasted: bool,
    ) -> None:
        meta = provider.context.oauth_metadata
        saved = stored_client(connection_id)
        saved["meta"] = {
            "revocation_endpoint": str(meta.revocation_endpoint)
            if meta and meta.revocation_endpoint
            else "",
            "issuer": str(meta.issuer) if meta else "",
        }
        secrets.put(connection_id, CLIENT_KEY, json.dumps(saved))
        tokens = stored_tokens(connection_id) or {}
        issuer = urlparse(saved["meta"]["issuer"]).netloc
        with self._factory() as db:
            login = db.get(McpOAuth, connection_id)
            if login is None:
                login = McpOAuth(connection_id=connection_id)
                db.add(login)
            info = storage.client_info
            login.issuer = saved["meta"]["issuer"]
            login.client_id = info.client_id if info else ""
            login.client_pasted = pasted
            login.redirect_uri = flow.redirect_uri
            login.scopes = tokens.get("scope") or ""
            login.account_label = f"{server_name} · {issuer}" if issuer else server_name
            login.expires_at = (
                datetime.fromtimestamp(float(tokens["expires_at"]), UTC)
                if tokens.get("expires_at")
                else None
            )
            login.status = OAuthStatus.CONNECTED
            clear_alerts(db, connection_id)
            db.commit()
        flow.state = "done"


def _explain(error: BaseException, name: str) -> str:
    for leaf in _leaves(error):
        if isinstance(leaf, NeedsLogin):
            return leaf.message
        if isinstance(leaf, (TimeoutError, asyncio.TimeoutError)):
            return "Se acabó el tiempo: no se completó la autorización en el navegador."
    text = " ".join(str(e) for e in _leaves(error))[:300]
    if "redirect" in text.lower():
        return (
            "El servicio no acepta la dirección de retorno. Si has pegado un client id, registra "
            "en el servicio esta dirección exacta y vuelve a intentarlo."
        )
    return f"No se ha podido conectar «{name}». {text}".strip()


async def _listen(port: int, code: asyncio.Future) -> uvicorn.Server:
    """The loopback page the service sends the person back to. It lives as long as the login."""

    async def callback(request: Request) -> Response:
        query = request.query_params
        if not code.done():
            if query.get("error"):
                reason = query.get("error_description") or query["error"]
                code.set_exception(NeedsLogin(f"La autorización se canceló o falló: {reason}"))
                return HTMLResponse(FAILED_PAGE.format(reason=reason), status_code=400)
            code.set_result(
                AuthorizationCodeResult(
                    code=query.get("code", ""), state=query.get("state"), iss=query.get("iss")
                )
            )
        return HTMLResponse(DONE_PAGE)

    server = uvicorn.Server(
        uvicorn.Config(
            Starlette(routes=[Route("/callback", callback)]),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    asyncio.get_running_loop().create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    return server


def parse_state(url: str) -> str:
    return (parse_qs(urlparse(url).query).get("state") or [""])[0]


def settings_port(db: Session) -> int:
    return connection_config.load(db).oauth_port
