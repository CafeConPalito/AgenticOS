"""An authorization server and a protected MCP server for the OAuth tests (phase 18), after spike
S3: dynamic registration, authorization (approved at once, like a person who clicks «Allow»),
token, refresh, revocation, and an MCP endpoint that wants a valid `Bearer` token."""

from __future__ import annotations

import secrets
import threading
import time
from base64 import urlsafe_b64encode
from hashlib import sha256
from urllib.parse import parse_qs, urlencode

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route


class Auth:
    def __init__(self, issuer: str, pasted_redirect: str = "", access_ttl: int = 3600) -> None:
        self.issuer = issuer
        self.access_ttl = access_ttl
        self.clients: dict[str, dict] = {}
        if pasted_redirect:  # registered by hand at the service, no dynamic registration
            self.clients["pasted-client"] = {"redirect_uris": [pasted_redirect]}
        self.codes: dict[str, dict] = {}
        self.access: dict[str, float] = {}
        self.refresh: dict[str, str] = {}
        self.revoked: list[str] = []
        self.log: list[str] = []
        self.refuse_refresh = False

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
        self.log.append(f"register {client_id}")
        return JSONResponse(
            {**body, "client_id": client_id, "token_endpoint_auth_method": "none"}, status_code=201
        )

    def authorize(self, request: Request) -> Response:
        q = request.query_params
        client = self.clients.get(q["client_id"])
        if not client or q["redirect_uri"] not in client["redirect_uris"]:
            self.log.append(f"authorize rejected {q.get('redirect_uri')}")
            return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
        code = secrets.token_urlsafe(12)
        self.codes[code] = {"challenge": q["code_challenge"], "client": q["client_id"]}
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
            if self.refuse_refresh or form["refresh_token"][0] not in self.refresh:
                self.log.append("refresh refused")
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
                "scope": "read",
            }
        )

    async def revoke(self, request: Request) -> Response:
        token = parse_qs((await request.body()).decode())["token"][0]
        self.revoked.append(token)
        self.access.pop(token, None)
        self.refresh.pop(token, None)
        return Response(status_code=200)


def build_app(auth: Auth) -> Starlette:
    mcp = MCPServer("oauth-probe")

    @mcp.tool()
    def whoami() -> str:
        """Return a fixed identity."""
        return "WHOAMI=probe-user@example.test"

    inner = mcp.streamable_http_app(streamable_http_path="/")

    class Guard:
        def __init__(self, app) -> None:
            self.app = app

        async def __call__(self, scope, receive, send) -> None:
            if scope["type"] == "http":
                headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
                token = headers.get("authorization", "").removeprefix("Bearer ")
                if auth.access.get(token, 0) < time.time():
                    await Response(
                        status_code=401,
                        headers={
                            "WWW-Authenticate": 'Bearer resource_metadata="'
                            f'{auth.issuer}/.well-known/oauth-protected-resource"'
                        },
                    )(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    return Starlette(
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


class Running:
    """The pair of servers in a thread of the test process, on the given port."""

    def __init__(self, port: int, pasted_redirect: str = "", access_ttl: int = 3600) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.url = f"{self.base}/mcp/"
        self.auth = Auth(self.base, pasted_redirect, access_ttl)
        config = uvicorn.Config(
            build_app(self.auth), host="127.0.0.1", port=port, log_level="error"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> Running:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
