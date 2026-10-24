"""The catalog of MCP connections through the API (phase 18, block 2): CA2 (create, edit, switch
off, export and delete a stdio and an HTTP one, form and pasted JSON, errors in words) and CA3
(no secret value in the database, the API or the export)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import secrets

STDIO = {"name": "postgres", "transport": "stdio", "command": "npx", "args": ["-y", "pg-mcp"]}
HTTP = {
    "name": "github",
    "transport": "http",
    "url": "https://api.example.test/mcp",
    "headers": {"Authorization": "Bearer ${secret:GITHUB_TOKEN}"},
    "secrets": {"GITHUB_TOKEN": "ghp_super_secret_123"},
}


def _create(client: TestClient, **payload) -> dict:
    response = client.post("/api/connections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()[0]


def _agent(client: TestClient) -> str:
    return client.post("/api/agents", json={"name": "Dev"}).json()["id"]


def _project(client: TestClient, tmp_path: Path) -> str:
    folder = tmp_path / "proyecto"
    folder.mkdir(exist_ok=True)
    return client.post("/api/projects", json={"name": "Tienda", "path": str(folder)}).json()["id"]


def _error(response) -> dict:
    assert response.status_code in (409, 422, 503), response.text
    return response.json()["detail"]


# -- CA2 ----------------------------------------------------------------------------------------
def test_create_a_stdio_and_an_http_connection(client: TestClient):
    stdio = _create(client, **STDIO)
    http = _create(client, **HTTP)
    assert (
        stdio["transport"] == "stdio"
        and stdio["command"] == "npx"
        and stdio["args"]
        == [
            "-y",
            "pg-mcp",
        ]
    )
    assert http["transport"] == "http" and http["revision"] == 1 and http["enabled"] is True
    assert http["secrets"] == [{"key": "GITHUB_TOKEN", "set": True}]
    listed = client.get("/api/connections").json()
    assert [c["name"] for c in listed] == ["github", "postgres"]


def test_edit_switch_off_and_delete(client: TestClient):
    created = _create(client, **STDIO)
    url = f"/api/connections/{created['id']}"
    edited = client.patch(url, json={"args": ["-y", "pg-mcp", "--ro"], "description": "BD"}).json()
    assert edited["args"][-1] == "--ro" and edited["description"] == "BD"
    assert edited["revision"] == 2  # what a run receives changed
    off = client.patch(url, json={"enabled": False}).json()
    assert off["enabled"] is False and off["revision"] == 2  # switching off is not a config change
    assert client.patch(url, json={"description": "otra"}).json()["revision"] == 2
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_pasted_json_creates_one_or_several_connections(client: TestClient):
    block = {
        "mcpServers": {
            "fs": {"command": "npx", "args": ["-y", "server-filesystem", "C:/data"]},
            "web": {"type": "http", "url": "https://web.example.test/mcp"},
        }
    }
    response = client.post("/api/connections", json={"json_text": json.dumps(block)})
    assert response.status_code == 201
    assert sorted(c["name"] for c in response.json()) == ["fs", "web"]
    single = client.post(
        "/api/connections",
        json={"name": "uno", "json_text": json.dumps({"command": "uvx", "args": ["x"]})},
    )
    assert single.status_code == 201 and single.json()[0]["name"] == "uno"


def test_bad_input_is_explained_in_words(client: TestClient):
    _create(client, **STDIO)
    taken = _error(client.post("/api/connections", json=STDIO))
    assert taken["code"] == "name_taken" and "Ya hay una conexión" in taken["message"]
    reserved = _error(client.post("/api/connections", json={**STDIO, "name": "agentic-os"}))
    assert reserved["code"] == "name_reserved"
    invalid = _error(client.post("/api/connections", json={**STDIO, "name": "Mi Servidor"}))
    assert invalid["code"] == "name_invalid" and "minúsculas" in invalid["message"]
    nocommand = _error(client.post("/api/connections", json={"name": "x", "transport": "stdio"}))
    assert nocommand["code"] == "command_missing" and "Falta el comando" in nocommand["message"]
    nourl = _error(client.post("/api/connections", json={"name": "y", "transport": "http"}))
    assert nourl["code"] == "url_missing"
    badurl = _error(
        client.post("/api/connections", json={"name": "z", "transport": "http", "url": "ftp://x"})
    )
    assert badurl["code"] == "url_invalid" and "http://" in badurl["message"]
    badjson = _error(client.post("/api/connections", json={"json_text": "{no json"}))
    assert badjson["code"] == "json_invalid" and "línea" in badjson["message"]
    nothing = _error(client.post("/api/connections", json={"json_text": '{"mcpServers": {}}'}))
    assert nothing["code"] == "config_invalid"
    # a rename cannot take another connection's name
    other = _create(client, name="otra", command="x")
    clash = _error(client.patch(f"/api/connections/{other['id']}", json={"name": "postgres"}))
    assert clash["code"] == "name_taken"


def test_the_json_preview_hides_the_secret_values(client: TestClient):
    block = {
        "mcpServers": {
            "api": {
                "url": "https://x.example.test/mcp",
                "headers": {"Authorization": "Bearer abc123def"},
            }
        }
    }
    preview = client.post("/api/connections/parse", json={"text": json.dumps(block)}).json()
    server = preview["servers"][0]
    assert server["headers"] == {"Authorization": "Bearer ${secret:AUTHORIZATION}"}
    assert server["secret_keys"] == ["AUTHORIZATION"]
    assert "abc123def" not in json.dumps(preview)


# -- CA3 ----------------------------------------------------------------------------------------
def _everything_stored(client: TestClient) -> str:
    """Every table of the database, as text."""
    engine = client.app.state.sessionmaker.kw["bind"]
    out = []
    with engine.connect() as db:
        tables = db.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars()
        for table in tables.all():
            rows = db.execute(text(f'SELECT * FROM "{table}"')).all()
            out.append(json.dumps([[str(v) for v in row] for row in rows]))
    return "\n".join(out)


def test_a_secret_is_nowhere_but_the_credential_store(client: TestClient, credential_store):
    created = _create(client, **HTTP)
    secret = "ghp_super_secret_123"
    assert secret not in json.dumps(created)
    assert secret not in json.dumps(client.get("/api/connections").json())
    assert secret not in json.dumps(client.get(f"/api/connections/{created['id']}").json())
    assert secret not in json.dumps(client.get(f"/api/connections/{created['id']}/export").json())
    assert secret not in _everything_stored(client)
    assert secrets.get(created["id"], "GITHUB_TOKEN") == secret  # it is there, for the run


def test_set_replace_and_clear_a_secret(client: TestClient, credential_store):
    created = _create(client, **{**HTTP, "secrets": {}})
    assert created["secrets"] == [{"key": "GITHUB_TOKEN", "set": False}]
    url = f"/api/connections/{created['id']}"
    after = client.put(f"{url}/secrets/GITHUB_TOKEN", json={"value": "first-value"}).json()
    assert after["secrets"][0]["set"] is True and after["revision"] == 2
    assert "first-value" not in json.dumps(after)
    client.put(f"{url}/secrets/GITHUB_TOKEN", json={"value": "second-value"})
    assert secrets.get(created["id"], "GITHUB_TOKEN") == "second-value"
    cleared = client.delete(f"{url}/secrets/GITHUB_TOKEN").json()
    assert cleared["secrets"][0]["set"] is False
    assert not credential_store.entries


def test_deleting_a_connection_deletes_its_secrets(client: TestClient, credential_store):
    created = _create(client, **HTTP)
    assert credential_store.entries
    client.delete(f"/api/connections/{created['id']}")
    assert not credential_store.entries


def test_dropping_a_placeholder_drops_its_secret(client: TestClient, credential_store):
    created = _create(client, **HTTP)
    client.patch(f"/api/connections/{created['id']}", json={"headers": {}})
    assert not credential_store.entries  # nothing refers to it any more


def test_an_unusable_credential_store_is_reported_not_swallowed(client: TestClient):
    import keyring
    from keyring.backends.fail import Keyring as FailKeyring

    previous = secrets.use(secrets.KeyringStore())
    try:
        keyring.set_keyring(FailKeyring())
        response = client.post("/api/connections", json=HTTP)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "secrets_unavailable"
        assert client.get("/api/connections").json() == []  # nothing half-created
    finally:
        secrets.use(previous)


def test_the_export_has_no_secrets_and_names_the_variables(client: TestClient):
    created = _create(client, **HTTP)
    exported = client.get(f"/api/connections/{created['id']}/export").json()
    server = exported["mcpServers"]["github"]
    assert server["type"] == "http" and server["url"] == "https://api.example.test/mcp"
    assert server["headers"] == {"Authorization": "Bearer ${GITHUB_TOKEN}"}


def test_a_system_variable_is_kept_as_a_reference(client: TestClient, monkeypatch):
    created = _create(client, name="viaenv", command="x", env={"TOKEN": "${env:MY_TOKEN}"})
    assert created["env"] == {"TOKEN": "${env:MY_TOKEN}"} and created["secrets"] == []


# -- the parser ---------------------------------------------------------------------------------
def test_the_parser_turns_secrets_into_placeholders():
    [draft] = fmt.parse_servers(
        json.dumps(
            {
                "mcpServers": {
                    "db": {
                        "command": "npx",
                        "args": ["pg", "postgres://user:s3cretpw@host:5432/app"],
                        "env": {"API_KEY": "abc-123", "MODE": "ro", "FROM": "${HOME}/x"},
                    }
                }
            }
        )
    )
    assert draft.args[1] == "postgres://user:${secret:PASSWORD}@host:5432/app"
    assert draft.env == {"API_KEY": "${secret:API_KEY}", "MODE": "ro", "FROM": "${env:HOME}/x"}
    assert draft.secrets == {"PASSWORD": "s3cretpw", "API_KEY": "abc-123"}
    assert draft.secret_keys == ["PASSWORD", "API_KEY"]


def test_the_parser_reads_the_other_shapes():
    vscode = fmt.parse_servers(json.dumps({"servers": {"a": {"command": "x"}}}))
    bare = fmt.parse_servers(json.dumps({"a": {"command": "x"}, "b": {"url": "https://u/sse"}}))
    assert vscode[0].name == "a"
    assert [d.transport for d in bare] == ["stdio", "sse"]  # the URL ending in /sse
    alias = fmt.parse_servers(
        json.dumps({"mcpServers": {"c": {"type": "streamable-http", "url": "https://u/mcp"}}})
    )
    assert alias[0].transport == "http"
    keeps = fmt.parse_servers(
        json.dumps({"mcpServers": {"d": {"command": "x", "oauth": {"a": 1}}}})
    )
    assert keeps[0].ignored == ["oauth"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ({"command": "x", "type": "websocket"}, "transport_invalid"),
        ({"command": "x", "args": "not-a-list"}, "config_invalid"),
        ({"command": "x", "env": ["A=1"]}, "config_invalid"),
        ({"description": "no way to run it"}, "config_invalid"),
    ],
)
def test_the_parser_names_what_is_wrong(raw, code):
    with pytest.raises(Exception) as error:
        fmt.parse_servers(json.dumps({"mcpServers": {"x": raw}}))
    assert error.value.code == code


def test_a_name_with_double_underscore_is_refused():
    with pytest.raises(Exception) as error:
        fmt.check_name("a__b")  # it would break the mcp__server__tool prefix
    assert error.value.code == "name_invalid"


# -- templates ----------------------------------------------------------------------------------
def test_templates_are_listed_with_their_form(client: TestClient):
    cards = {t["id"]: t for t in client.get("/api/connections/templates").json()}
    assert {"github", "playwright", "postgres", "sqlite", "filesystem", "fetch", "context7"} <= set(
        cards
    )
    assert {"linear", "notion"} <= set(cards) and cards["linear"]["auth"] == "oauth"
    assert cards["github"]["fields"][0]["secret"] is True
    assert cards["playwright"]["requires"] == ["npx"]
    assert "@0.0.83" in cards["playwright"]["command"]  # pinned (spec G)


def test_a_template_fills_the_form_and_stores_the_secret(client: TestClient, credential_store):
    response = client.post(
        "/api/connections/from-template",
        json={"template": "github", "values": {"GITHUB_TOKEN": "ghp_template_token"}},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "github" and created["origin"] == "template"
    assert created["headers"] == {"Authorization": "Bearer ${secret:GITHUB_TOKEN}"}
    assert "ghp_template_token" not in json.dumps(created)
    assert secrets.get(created["id"], "GITHUB_TOKEN") == "ghp_template_token"
    again = client.post("/api/connections/from-template", json={"template": "github"})
    assert again.json()["name"] == "github-2"  # a free name, no error


def test_a_template_with_a_path_field(client: TestClient):
    created = client.post(
        "/api/connections/from-template",
        json={"template": "filesystem", "values": {"folder": "C:/datos"}, "name": "datos"},
    ).json()
    assert created["command"] == "npx" and created["args"][-1] == "C:/datos"
    missing = _error(
        client.post("/api/connections/from-template", json={"template": "sqlite", "name": "s"})
    )
    assert missing["code"] == "field_required" and "Fichero" in missing["message"]
    unknown = _error(client.post("/api/connections/from-template", json={"template": "nope"}))
    assert unknown["code"] == "template_unknown"


def test_creating_with_a_level_gives_it_right_away(client: TestClient, tmp_path: Path):
    agent, project = _agent(client), _project(client, tmp_path)
    general = _create(client, **STDIO, level={"scope": "general"})
    assert [a["scope"] for a in general["assignments"]] == ["general"]
    in_project = _create(
        client, name="p", command="x", level={"scope": "project", "project_id": project}
    )
    assert in_project["assignments"][0]["project_id"] == project
    on_agent = _create(client, name="a", command="x", level={"scope": "agent", "agent_id": agent})
    assert on_agent["assignments"][0]["agent_id"] == agent
    bad = client.post(
        "/api/connections", json={"name": "q", "command": "x", "level": {"scope": "project"}}
    )
    assert bad.status_code == 422


# -- settings -----------------------------------------------------------------------------------
def test_settings_are_kept_and_limited(client: TestClient):
    assert client.get("/api/settings/connections").json()["oauth_port"] == 53682
    saved = client.put(
        "/api/settings/connections",
        json={"probe_timeout": 5000, "agy_grace": 8, "oauth_port": 54000},
    ).json()
    assert saved["probe_timeout"] == 600 and saved["agy_grace"] == 8  # limited
    assert client.get("/api/settings/connections").json()["oauth_port"] == 54000
