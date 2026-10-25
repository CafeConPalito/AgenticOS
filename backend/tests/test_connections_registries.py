"""The explorer of public MCP registries (phase 18, block 8) with simulated sources: CA14 (most
used and search across the active sources, the ficha with the exact command and what is missing,
installing pinned to a version at a level) and CA15 (updates that are shown and never applied by
themselves, no network, a source that fails)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from agentic_os.services.connections import secrets
from agentic_os.services.connections.registries import service as registries

OFFICIAL = "https://registry.modelcontextprotocol.io/v0.1"


def entry(name: str, **server) -> dict:
    base = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": name,
        "description": f"{name} description",
        "version": "1.0.0",
    }
    return {
        "server": {**base, **server},
        "_meta": {
            "io.modelcontextprotocol.registry/official": {
                "status": "active",
                "updatedAt": "2026-10-01T00:00:00Z",
            }
        },
    }


PG = entry(
    "io.github.acme/pg-mcp",
    repository={"url": "https://github.com/acme/pg-mcp", "source": "github"},
    packages=[
        {
            "registryType": "npm",
            "identifier": "@acme/pg-mcp",
            "version": "latest",
            "transport": {"type": "stdio"},
            "environmentVariables": [
                {
                    "name": "PG_PASSWORD",
                    "description": "DB password",
                    "isRequired": True,
                    "isSecret": True,
                },
                {"name": "PG_HOST", "isRequired": False, "default": "localhost"},
            ],
            "packageArguments": [
                {"type": "named", "name": "--mode", "value": "read-only"},
                {"type": "positional", "valueHint": "database", "isRequired": True},
            ],
        },
        {  # a package that serves HTTP on a port: not usable from here
            "registryType": "npm",
            "identifier": "@acme/pg-mcp-http",
            "version": "1.0.0",
            "transport": {"type": "streamable-http"},
        },
        {
            "registryType": "pypi",
            "identifier": "acme-pg-mcp",
            "version": "0.4.0",
            "transport": {"type": "stdio"},
        },
    ],
)
LINEAR = entry(
    "app.linear/linear",
    websiteUrl="https://linear.app",
    remotes=[
        {
            "type": "streamable-http",
            "url": "https://mcp.linear.app/mcp",
            "headers": [
                {
                    "name": "Authorization",
                    "value": "Bearer {linear_token}",
                    "isSecret": True,
                    "isRequired": True,
                }
            ],
        }
    ],
)
SMITHERY_DUP = entry(
    "ai.smithery/other", remotes=[{"type": "streamable-http", "url": "https://x/mcp"}]
)


class Fake:
    """The registries' HTTP APIs, as much as the tests need. `calls` counts the requests."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.npm_latest = {"@acme/pg-mcp": "2.1.0"}
        self.downloads = {"@acme/pg-mcp": 5000}
        self.smithery_down = False
        self.offline = False
        self.official_entries = [PG, LINEAR, SMITHERY_DUP]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(str(url))
        if self.offline:
            raise httpx.ConnectError("no network")
        host, path = url.host, unquote(url.path)
        query = parse_qs(url.query.decode())
        if host == "registry.modelcontextprotocol.io":
            if path.endswith("/versions/latest"):
                name = path.removeprefix("/v0.1/servers/").removesuffix("/versions/latest")
                found = next(
                    (e for e in self.official_entries if e["server"]["name"] == name), None
                )
                return httpx.Response(200, json=found) if found else httpx.Response(404)
            term = (query.get("search") or [""])[0]
            hits = [
                e
                for e in self.official_entries
                if term in e["server"]["name"] + e["server"]["description"]
            ]
            return httpx.Response(200, json={"servers": hits, "metadata": {"count": len(hits)}})
        if host == "api.npmjs.org":
            pkg = path.removeprefix("/downloads/point/last-week/")
            return httpx.Response(200, json={"downloads": self.downloads.get(pkg, 0)})
        if host == "registry.npmjs.org":
            pkg = path.removeprefix("/").removesuffix("/latest")
            if pkg in self.npm_latest:
                return httpx.Response(
                    200, json={"version": self.npm_latest[pkg], "description": "pkg"}
                )
            return httpx.Response(404)
        if host == "pypi.org":
            return httpx.Response(200, json={"info": {"version": "0.9.0", "summary": "py"}})
        if host == "registry.smithery.ai":
            if self.smithery_down:
                return httpx.Response(500)
            if path == "/servers":
                return httpx.Response(
                    200,
                    json={
                        "servers": [
                            {
                                "qualifiedName": "github",
                                "displayName": "GitHub",
                                "useCount": 6059,
                                "remote": True,
                                "verified": True,
                                "description": "GitHub tools",
                                "namespace": "github",
                            },
                            {
                                "qualifiedName": "local-only",
                                "displayName": "Local",
                                "useCount": 99999,
                                "remote": False,
                            },
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "qualifiedName": "github",
                    "displayName": "GitHub",
                    "description": "GitHub tools",
                    "connections": [{"type": "http", "deploymentUrl": "https://github.run.tools"}],
                    "tools": [
                        {
                            "name": "list_issues",
                            "description": "List",
                            "inputSchema": {"type": "object"},
                        }
                    ],
                    "security": None,
                },
            )
        if host == "api.github.com":
            return httpx.Response(
                200,
                json={
                    "name": "repo",
                    "default_branch": "main",
                    "html_url": "https://github.com/o/repo",
                    "license": {"spdx_id": "MIT"},
                    "stargazers_count": 7,
                    "description": "d",
                },
            )
        if host == "raw.githubusercontent.com":
            if path.endswith("server.json"):
                return httpx.Response(200, json=PG["server"])
            if path.endswith("README.md"):
                return httpx.Response(404)
        return httpx.Response(404)


@pytest.fixture
def fake(client: TestClient) -> Fake:
    fake = Fake()
    client.app.state.mcp_registries = registries.RegistryService(httpx.MockTransport(fake))
    return fake


def _search(client: TestClient, **params) -> dict:
    response = client.get("/api/connections/registries/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _detail(client: TestClient, source: str, ref: str) -> dict:
    response = client.get(
        "/api/connections/registries/detail", params={"source": source, "ref": ref}
    )
    assert response.status_code == 200, response.text
    return response.json()


# -- listing ------------------------------------------------------------------------------------
def test_the_most_used_come_first_and_smithery_duplicates_are_left_out(
    client: TestClient, fake: Fake
):
    listing = _search(client)
    names = [(c["source"], c["name"]) for c in listing["cards"]]
    assert names == [("smithery", "GitHub"), ("official", "pg-mcp"), ("official", "linear")]
    # smithery's number of uses, the official registry's weekly npm downloads
    by_name = {c["name"]: c for c in listing["cards"]}
    assert by_name["GitHub"]["uses"] == 6059 and by_name["pg-mcp"]["uses"] == 5000
    assert (
        by_name["GitHub"]["verified"] is True and by_name["pg-mcp"]["verified"] is True
    )  # acme/acme
    assert by_name["linear"]["transport"] == "http" and by_name["pg-mcp"]["transport"] == "stdio"
    assert "other" not in by_name and "Local" not in by_name  # the Smithery copy / a non-remote one
    assert listing["errors"] == {}


def test_search_filters_by_source_and_transport(client: TestClient, fake: Fake):
    only_official = _search(client, query="mcp", source="official")
    assert {c["source"] for c in only_official["cards"]} == {"official"}
    http = _search(client, transport="http")
    assert {c["name"] for c in http["cards"]} == {"GitHub", "linear"}
    stdio = _search(client, transport="stdio")
    assert {c["name"] for c in stdio["cards"]} == {"pg-mcp"}


def test_a_source_that_fails_does_not_break_the_others(client: TestClient, fake: Fake):
    fake.smithery_down = True
    listing = _search(client, query="a")
    assert listing["errors"] == {"smithery": "unavailable"} and listing["cards"]
    fake.offline = True
    registries_down = _search(client, query="b")
    assert registries_down["errors"] == {"official": "offline", "smithery": "offline"}
    assert registries_down["cards"] == []
    assert client.get("/api/connections").status_code == 200  # the catalog goes on


def test_the_same_search_is_not_asked_twice(client: TestClient, fake: Fake):
    _search(client, query="pg")
    after_first = len(fake.calls)
    _search(client, query="pg")
    assert len(fake.calls) == after_first


def test_a_source_can_be_switched_off(client: TestClient, fake: Fake):
    saved = client.put(
        "/api/settings/connections", json={"registries": {"smithery": False, "bogus": True}}
    ).json()
    assert saved["registries"] == {"official": True, "smithery": False}
    listing = _search(client, query="a")
    assert {c["source"] for c in listing["cards"]} == {"official"}
    assert not [c for c in fake.calls if "smithery" in c]
    status = {s["id"]: s for s in client.get("/api/connections/registries").json()}
    assert status["smithery"]["enabled"] is False and status["package"]["switchable"] is False


# -- the ficha ----------------------------------------------------------------------------------
def test_the_ficha_says_what_would_run_and_what_is_missing(
    client: TestClient, fake: Fake, monkeypatch
):
    monkeypatch.setattr(registries.shutil, "which", lambda name: None if name == "npx" else "x")
    detail = _detail(client, "official", "io.github.acme/pg-mcp")
    assert (
        detail["card"]["name"] == "pg-mcp"
        and detail["repo_url"] == "https://github.com/acme/pg-mcp"
    )
    # the HTTP-serving package is not offered; npm and PyPI are
    assert [(o["kind"], o["package"]) for o in detail["options"]] == [
        ("npm", "@acme/pg-mcp"),
        ("pypi", "acme-pg-mcp"),
    ]
    npm = detail["options"][0]
    assert (
        npm["command"] == "npx -y @acme/pg-mcp@2.1.0 --mode read-only"
    )  # fixed arguments shown; «latest» resolved to the exact version
    assert npm["requires"] == ["npx"] and npm["missing"] == ["npx"]
    fields = {f["key"]: f for f in npm["fields"]}
    assert fields["PG_PASSWORD"]["secret"] and fields["PG_PASSWORD"]["required"]
    assert fields["PG_HOST"]["default"] == "localhost" and not fields["PG_HOST"]["required"]
    assert fields["database"]["where"] == "arg"
    assert (
        detail["options"][1]["command"] == "uvx acme-pg-mcp==0.4.0"
        and detail["options"][1]["missing"] == []
    )
    assert detail["installed_as"] is None


def test_a_remote_server_asks_for_its_header(client: TestClient, fake: Fake):
    option = _detail(client, "official", "app.linear/linear")["options"][0]
    assert option["kind"] == "remote" and option["url"] == "https://mcp.linear.app/mcp"
    [field] = option["fields"]
    assert (field["where"], field["name"], field["secret"]) == ("header", "Authorization", True)


def test_smithery_shows_its_tools_and_asks_for_the_login(client: TestClient, fake: Fake):
    detail = _detail(client, "smithery", "github")
    assert detail["tools"][0]["name"] == "list_issues"
    option = detail["options"][0]
    assert option["url"] == "https://github.run.tools" and option["oauth"] is True
    assert "Smithery" in detail["note"]


def test_a_server_without_a_way_to_run_it_is_explained(client: TestClient, fake: Fake):
    fake.official_entries.append(entry("x/none", description="nothing runnable"))
    response = client.get(
        "/api/connections/registries/detail", params={"source": "official", "ref": "x/none"}
    )
    assert (
        response.status_code == 502 and response.json()["detail"]["code"] == "registry_bad_server"
    )
    assert (
        client.get(
            "/api/connections/registries/detail", params={"source": "nope", "ref": "x"}
        ).status_code
        == 404
    )


# -- install ------------------------------------------------------------------------------------
def _install(client: TestClient, **body):
    payload = {"source": "official", "ref": "io.github.acme/pg-mcp", **body}
    return client.post("/api/connections/registries/install", json=payload)


def test_installing_pins_the_version_and_keeps_the_secret_apart(
    client: TestClient, fake: Fake, credential_store
):
    response = _install(
        client,
        values={"PG_PASSWORD": "pw-top-secret", "database": "shop"},
        level={"scope": "general"},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "pg-mcp" and created["origin"] == "registry"
    assert created["command"] == "npx"
    assert created["args"] == ["-y", "@acme/pg-mcp@2.1.0", "--mode", "read-only", "shop"]
    assert created["env"] == {"PG_PASSWORD": "${secret:PG_PASSWORD}", "PG_HOST": "localhost"}
    assert "pw-top-secret" not in json.dumps(created)
    assert secrets.get(created["id"], "PG_PASSWORD") == "pw-top-secret"
    assert created["assignments"][0]["scope"] == "general"
    origin = created["registry"]
    assert (origin["source"], origin["package"], origin["version"]) == (
        "official",
        "@acme/pg-mcp",
        "2.1.0",
    )
    assert origin["official"] is True and origin["update_available"] is False
    # nothing was started: it was never tested
    assert created["tested_at"] is None and created["tools"] == []
    # and the ficha now says it is installed
    assert _detail(client, "official", "io.github.acme/pg-mcp")["installed_as"] == "pg-mcp"
    cards = {c["name"]: c for c in _search(client, query="pg")["cards"]}
    assert cards["pg-mcp"]["installed_connection_id"] == created["id"]


def test_install_asks_for_what_is_required(client: TestClient, fake: Fake):
    missing = _install(client, values={"PG_PASSWORD": "x"})
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "field_required"
    assert "database" in missing.json()["detail"]["message"]
    assert client.get("/api/connections").json() == []  # nothing half-created
    bad = _install(client, option=9)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "option_unknown"


def test_a_remote_is_installed_with_its_header_and_the_login_if_asked(
    client: TestClient, fake: Fake
):
    response = _install(
        client, ref="app.linear/linear", values={"linear_token": "lin_api_123456"}, name="mi-linear"
    )
    created = response.json()
    assert created["transport"] == "http" and created["url"] == "https://mcp.linear.app/mcp"
    assert created["headers"] == {"Authorization": "Bearer ${secret:linear_token}"}
    assert created["name"] == "mi-linear" and created["auth"] == "none"
    smithery = _install(client, source="smithery", ref="github")
    assert (
        smithery.json()["auth"] == "oauth" and smithery.json()["url"] == "https://github.run.tools"
    )
    no_login = _install(client, source="smithery", ref="github", oauth=False)
    assert no_login.json()["auth"] == "none" and no_login.json()["name"] == "github-2"


def test_the_pypi_way_and_a_name_that_is_taken(client: TestClient, fake: Fake):
    first = _install(client, option=1)
    assert first.json()["args"] == ["acme-pg-mcp==0.4.0"] and first.json()["command"] == "uvx"
    second = _install(client, option=1)
    assert second.json()["name"] == "pg-mcp-2"


# -- by name or address ---------------------------------------------------------------------------
def test_a_package_or_a_repository_can_be_installed_by_its_address(client: TestClient, fake: Fake):
    fake.npm_latest["@x/tool"] = "3.0.0"
    card = _search(client, query="npm:@x/tool")["cards"][0]
    assert (card["source"], card["name"], card["version"]) == ("package", "@x/tool", "3.0.0")
    created = _install(client, source="package", ref="npm:@x/tool", name="tool").json()
    assert created["args"] == ["-y", "@x/tool@3.0.0"]
    repo = _detail(client, "package", "https://github.com/o/repo")
    assert (
        repo["license"] == "MIT" and repo["options"][0]["package"] == "@acme/pg-mcp"
    )  # from server.json
    assert _search(client, query="not-an-address-at-all")["errors"] == {}


# -- updates ------------------------------------------------------------------------------------
def test_an_update_is_shown_and_never_applied_by_itself(client: TestClient, fake: Fake):
    created = _install(client, values={"PG_PASSWORD": "pw", "database": "shop"}).json()
    url = f"/api/connections/{created['id']}"
    assert client.get(f"{url}/update").status_code == 422  # up to date: nothing to show
    fake.npm_latest["@acme/pg-mcp"] = "2.2.0"
    news = client.post("/api/connections/updates/check").json()
    assert news == [
        {"connection_id": created["id"], "name": "pg-mcp", "version": "2.1.0", "latest": "2.2.0"}
    ]
    card = client.get(url).json()["registry"]
    assert card["update_available"] is True and card["version"] == "2.1.0"  # still the old one
    assert client.get(url).json()["args"][1] == "@acme/pg-mcp@2.1.0"
    preview = client.get(f"{url}/update").json()
    assert preview["from"] == "2.1.0" and preview["to"] == "2.2.0"
    command = next(c for c in preview["changes"] if c["field"] == "command")
    assert command["from"].startswith("npx -y @acme/pg-mcp@2.1.0") and command["to"].startswith(
        "npx -y @acme/pg-mcp@2.2.0"
    )
    done = client.post(f"{url}/update").json()
    assert done["args"][1] == "@acme/pg-mcp@2.2.0" and done["revision"] == created["revision"] + 1
    assert done["registry"]["version"] == "2.2.0" and done["registry"]["update_available"] is False
    assert done["tools_changed"] is True  # test it again: the new version may have other tools
    assert done["secrets"] == created["secrets"]  # the secrets are kept


def test_an_edited_command_is_not_overwritten(client: TestClient, fake: Fake):
    created = _install(client, values={"PG_PASSWORD": "pw", "database": "shop"}).json()
    client.patch(
        f"/api/connections/{created['id']}", json={"args": ["-y", "@acme/pg-mcp@2.1.0-mio"]}
    )
    fake.npm_latest["@acme/pg-mcp"] = "2.2.0"
    client.post("/api/connections/updates/check")
    refused = client.post(f"/api/connections/{created['id']}/update")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "update_edited"
    assert (
        client.get(f"/api/connections/{created['id']}").json()["args"][1]
        == "@acme/pg-mcp@2.1.0-mio"
    )


def test_only_what_came_from_a_registry_has_updates(client: TestClient, fake: Fake):
    own = client.post("/api/connections", json={"name": "mia", "command": "x"}).json()[0]
    assert client.get(f"/api/connections/{own['id']}/update").status_code == 422
    assert client.post("/api/connections/updates/check").json() == []


def test_urls_in_a_ref_survive_the_query(client: TestClient, fake: Fake):
    # the parser of the address, on its own
    from agentic_os.services.connections.registries.packages import parse_reference

    assert parse_reference("https://www.npmjs.com/package/@x/tool") == ("npm", "@x/tool")
    assert parse_reference("https://pypi.org/project/foo/") == ("pypi", "foo")
    assert parse_reference("https://github.com/o/repo.git") == ("github", "o/repo")
    assert urlparse("npm:@x/y").scheme == "npm"
