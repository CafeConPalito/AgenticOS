"""Phase 18 · spike S3: OAuth for remote MCP servers with the SDK's own provider.

Part 1 (read only): what do real remote MCP servers advertise? Unauthenticated `initialize`
-> 401 + WWW-Authenticate, protected-resource metadata, authorization-server metadata.
No client is registered and nobody logs in.

Part 2 (local): a simulated authorization server + protected MCP server, driven by
`mcp.client.auth.OAuthClientProvider` the way the app would:
  - random loopback port for the redirect (dynamic registration);
  - tokens kept in a storage object (stands for the OS credential store);
  - a pre-registered client (`client_id` pasted, no dynamic registration) with a fixed port;
  - automatic refresh when the access token expires;
  - revocation.

Usage: uv run python mcp/s3_oauth.py [discover|local]
"""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
import sys
import time
from base64 import urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import uvicorn
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from mcp import ClientSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import REPO  # noqa: E402

EVIDENCE = REPO / "docs" / "phases" / "18-conexiones-mcp" / "evidencias"
REMOTE_SERVERS = {
    "linear": "https://mcp.linear.app/mcp",
    "notion": "https://mcp.notion.com/mcp",
    "github": "https://api.githubcopilot.com/mcp/",
    "atlassian": "https://mcp.atlassian.com/v1/mcp",
    "sentry": "https://mcp.sentry.dev/mcp",
    "asana": "https://mcp.asana.com/v2/mcp",
    "stripe": "https://mcp.stripe.com",
    "context7": "https://mcp.context7.com/mcp",
}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "agentic-os-spike", "version": "0"},
    },
}


# -- part 1: real servers, read only --------------------------------------------------------
async def discover_one(client: httpx.AsyncClient, name: str, url: str) -> dict:
    out: dict = {"url": url}
    try:
        response = await client.post(
            url,
            json=INIT,
            headers={"Accept": "application/json, text/event-stream"},
        )
    except httpx.HTTPError as error:
        return out | {"error": f"{type(error).__name__}: {error}"[:200]}
    out["status"] = response.status_code
    challenge = response.headers.get("www-authenticate", "")
    out["www_authenticate"] = challenge[:300]
    if response.status_code != 401:
        out["note"] = "no authentication required" if response.status_code < 400 else "other"
        return out
    metadata_url = None
    for part in challenge.split(","):
        if "resource_metadata=" in part:
            metadata_url = part.split("resource_metadata=")[1].strip().strip('"')
    parsed = urlparse(url)
    candidates = [metadata_url] if metadata_url else []
    candidates += [
        f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{parsed.path.rstrip('/')}",
        f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource",
    ]
    prm = None
    for candidate in candidates:
        r = await client.get(candidate)
        if r.status_code == 200:
            prm = r.json()
            out["prm_url"] = candidate
            break
    out["protected_resource"] = prm
    issuers = (prm or {}).get("authorization_servers") or [f"{parsed.scheme}://{parsed.netloc}"]
    issuer = issuers[0].rstrip("/")
    ip = urlparse(issuer)
    for meta_url in (
        f"{ip.scheme}://{ip.netloc}/.well-known/oauth-authorization-server{ip.path}",
        f"{ip.scheme}://{ip.netloc}/.well-known/openid-configuration{ip.path}",
        f"{issuer}/.well-known/openid-configuration",
    ):
        r = await client.get(meta_url)
        if r.status_code == 200:
            meta = r.json()
            out["authorization_server"] = {
                "issuer": meta.get("issuer"),
                "registration_endpoint": meta.get("registration_endpoint"),
                "revocation_endpoint": meta.get("revocation_endpoint"),
                "code_challenge_methods": meta.get("code_challenge_methods_supported"),
                "token_endpoint_auth_methods": meta.get("token_endpoint_auth_methods_supported"),
                "grant_types": meta.get("grant_types_supported"),
                "scopes": (meta.get("scopes_supported") or [])[:12],
                "client_id_metadata_document_supported": meta.get(
                    "client_id_metadata_document_supported"
                ),
            }
            break
    return out


async def discover() -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(discover_one(client, n, u) for n, u in REMOTE_SERVERS.items())
        )
    return dict(zip(REMOTE_SERVERS, results, strict=True))


# -- part 2: local authorization server + protected MCP server ------------------------------
class Auth:
    """A tiny OAuth 2.1 server: DCR, authorize (auto approve), token, refresh, revoke."""

    def __init__(self, issuer: str, access_ttl: int = 3600) -> None:
        self.issuer = issuer
        self.access_ttl = access_ttl
        self.clients: dict[str, dict] = {
            # pre-registered (no dynamic registration): exact redirect URI required
            "pasted-client": {"redirect_uris": ["http://127.0.0.1:53682/callback"]}
        }
        self.codes: dict[str, dict] = {}
        self.access: dict[str, float] = {}
        self.refresh: dict[str, str] = {}
        self.revoked: list[str] = []
        self.log: list[str] = []

    def metadata(self, _: Request) -> Response:
        return JSONResponse(
            {
                "issuer": self.issuer,
                "authorization_endpoint": f"{self.issuer}/authorize",
                "token_endpoint": f"{self.issuer}/token",
                "registration_endpoint": f"{self.issuer}/register",
                "revocation_endpoint": f"{self.issuer}/revoke",
                "code_challenge_methods_supported": ["S256"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],
                "response_types_supported": ["code"],
            }
        )

    def resource(self, _: Request) -> Response:
        return JSONResponse(
            {"resource": f"{self.issuer}/mcp", "authorization_servers": [self.issuer]}
        )

    async def register(self, request: Request) -> Response:
        body = await request.json()
        client_id = f"dyn-{secrets.token_hex(4)}"
        self.clients[client_id] = {"redirect_uris": body["redirect_uris"]}
        self.log.append(f"register {client_id} {body['redirect_uris']}")
        return JSONResponse(
            {**body, "client_id": client_id, "token_endpoint_auth_method": "none"}, status_code=201
        )

    def authorize(self, request: Request) -> Response:
        q = request.query_params
        client = self.clients.get(q["client_id"])
        if not client or q["redirect_uri"] not in client["redirect_uris"]:
            self.log.append(f"authorize REJECTED redirect {q.get('redirect_uri')}")
            return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
        code = secrets.token_urlsafe(12)
        self.codes[code] = {"challenge": q["code_challenge"], "client": q["client_id"]}
        self.log.append(f"authorize ok {q['redirect_uri']}")
        return RedirectResponse(
            f"{q['redirect_uri']}?{urlencode({'code': code, 'state': q.get('state', '')})}"
        )

    async def token(self, request: Request) -> Response:
        form = parse_qs((await request.body()).decode())
        grant = form["grant_type"][0]
        if grant == "authorization_code":
            entry = self.codes.pop(form["code"][0], None)
            verifier = form["code_verifier"][0]
            challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if not entry or entry["challenge"] != challenge:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
        elif grant == "refresh_token":
            if form["refresh_token"][0] not in self.refresh:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            self.log.append("refresh used")
        else:
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        access, refresh = f"at-{secrets.token_hex(6)}", f"rt-{secrets.token_hex(6)}"
        self.access[access] = time.time() + self.access_ttl
        self.refresh[refresh] = access
        return JSONResponse(
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": self.access_ttl,
                "refresh_token": refresh,
            }
        )

    async def revoke(self, request: Request) -> Response:
        form = parse_qs((await request.body()).decode())
        token = form["token"][0]
        self.revoked.append(token)
        self.access.pop(token, None)
        self.refresh.pop(token, None)
        return Response(status_code=200)


def build_server(auth: Auth) -> Starlette:
    mcp = MCPServer("oauth-probe")

    @mcp.tool()
    def whoami() -> str:
        """Return a fixed identity."""
        return "WHOAMI=probe-user@example.test"

    inner = mcp.streamable_http_app(streamable_http_path="/")

    class Guard:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
                token = headers.get("authorization", "").removeprefix("Bearer ")
                if auth.access.get(token, 0) < time.time():
                    response = Response(
                        status_code=401,
                        headers={
                            "WWW-Authenticate": 'Bearer resource_metadata="'
                            f'{auth.issuer}/.well-known/oauth-protected-resource"'
                        },
                    )
                    await response(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    app = Starlette(
        routes=[
            Route("/.well-known/oauth-protected-resource", auth.resource),
            Route("/.well-known/oauth-protected-resource/mcp", auth.resource),
            Route("/.well-known/oauth-authorization-server", auth.metadata),
            Route("/register", auth.register, methods=["POST"]),
            Route("/authorize", auth.authorize),
            Route("/token", auth.token, methods=["POST"]),
            Route("/revoke", auth.revoke, methods=["POST"]),
            Mount("/mcp", app=Guard(inner)),
        ],
        lifespan=inner.router.lifespan_context,
    )
    return app


class Storage:
    """Stands for the OS credential store (keyring) in the app."""

    def __init__(self, client_info: OAuthClientInformationFull | None = None) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info = client_info
        self.writes = 0

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens
        self.writes += 1

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, info):
        self.client_info = info


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def loopback_callback(port: int):
    """What the backend's /oauth/callback does: receives the redirect and hands code+state over."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[AuthorizationCodeResult] = loop.create_future()

    async def callback(request: Request) -> Response:
        q = request.query_params
        if not future.done():
            future.set_result(AuthorizationCodeResult(code=q["code"], state=q.get("state")))
        return HTMLResponse("You can go back to Agentic OS.")

    server = uvicorn.Server(
        uvicorn.Config(
            Starlette(routes=[Route("/callback", callback)]),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    return future, server, task


async def connect(url: str, provider: OAuthClientProvider) -> dict:
    import httpx2

    async with (
        httpx2.AsyncClient(auth=provider, timeout=30) as http,
        streamable_http_client(url, http_client=http) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
        result = await session.call_tool("whoami", {})
        return {"tools": tools, "call": result.content[0].text}


async def run_flow(auth: Auth, base: str, *, port: int, client_info=None, label: str) -> dict:
    """One 'Conectar': the redirect handler hits the authorize URL like a browser would."""
    storage = Storage(client_info)
    future, cb_server, cb_task = await loopback_callback(port)
    redirect = f"http://127.0.0.1:{port}/callback"
    opened: list[str] = []

    async def redirect_handler(authorization_url: str) -> None:
        opened.append(authorization_url)
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as browser:
            await browser.get(authorization_url)  # the user's browser, consent auto-approved

    async def callback_handler() -> AuthorizationCodeResult:
        return await asyncio.wait_for(future, timeout=20)

    provider = OAuthClientProvider(
        server_url=f"{base}/mcp/",
        client_metadata=OAuthClientMetadata(
            client_name="Agentic OS",
            redirect_uris=[redirect],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )
    out: dict = {"label": label, "redirect_uri": redirect}
    try:
        out["first_connect"] = await connect(f"{base}/mcp/", provider)
        out["client_id"] = storage.client_info.client_id if storage.client_info else None
        out["token_writes"] = storage.writes
        out["has_refresh_token"] = bool(storage.tokens and storage.tokens.refresh_token)
        # the access token expires: the next connection must refresh by itself
        first_access = storage.tokens.access_token
        auth.access[first_access] = time.time() - 1
        provider.context.token_expiry_time = time.time() - 1
        out["after_expiry"] = await connect(f"{base}/mcp/", provider)
        out["refreshed"] = storage.tokens.access_token != first_access
        out["browser_opened_times"] = len(opened)
        # revoke (what 'Desconectar' does)
        await httpx.AsyncClient().post(
            f"{base}/revoke", data={"token": storage.tokens.refresh_token}
        )
        out["revoked_server_side"] = len(auth.revoked)
    except Exception as error:  # noqa: BLE001 - the spike reports, whatever it is
        out["error"] = f"{type(error).__name__}: {error}"[:400]
    finally:
        cb_server.should_exit = True
        await cb_task
    return out


async def local() -> dict:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    auth = Auth(base)
    server = uvicorn.Server(
        uvicorn.Config(build_server(auth), host="127.0.0.1", port=port, log_level="error")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    results = {}
    try:
        results["dynamic_random_port"] = await run_flow(
            auth, base, port=free_port(), label="dynamic registration, random loopback port"
        )
        results["dynamic_other_port"] = await run_flow(
            auth, base, port=free_port(), label="same, another random port (new registration)"
        )
        pasted = OAuthClientInformationFull(
            client_id="pasted-client",
            redirect_uris=["http://127.0.0.1:53682/callback"],
            token_endpoint_auth_method="none",
        )
        results["pasted_client_fixed_port"] = await run_flow(
            auth, base, port=53682, client_info=pasted, label="pasted client_id, fixed port 53682"
        )
        results["pasted_client_wrong_port"] = await run_flow(
            auth, base, port=free_port(), client_info=pasted, label="pasted client_id, other port"
        )
    finally:
        server.should_exit = True
        await task
    results["auth_server_log"] = auth.log
    return results


def main() -> None:
    wanted = set(sys.argv[1:]) or {"discover", "local"}
    report: dict = {}
    if "discover" in wanted:
        report["discover"] = asyncio.run(discover())
        for name, info in report["discover"].items():
            meta = info.get("authorization_server") or {}
            print(
                f"{name:10} status={info.get('status')} dcr={bool(meta.get('registration_endpoint'))}"
                f" revoke={bool(meta.get('revocation_endpoint'))} pkce={meta.get('code_challenge_methods')}"
                f" err={info.get('error', '')[:60]}"
            )
    if "local" in wanted:
        report["local"] = asyncio.run(local())
        print(json.dumps(report["local"], indent=1))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s3-oauth-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
