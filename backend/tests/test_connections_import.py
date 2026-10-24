"""Importing the servers the person already has in their CLIs (phase 18, block 2): CA9 (global and
per-project servers of `~/.claude.json`, a project's `.mcp.json` and `agy`'s list; the secrets
go to the credential store; the originals do not change)."""

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_os.config import Settings
from agentic_os.services.connections import secrets


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _setup(client: TestClient, settings: Settings, tmp_path: Path) -> dict:
    folder = tmp_path / "tienda"
    folder.mkdir()
    project = client.post("/api/projects", json={"name": "Tienda", "path": str(folder)}).json()
    claude = _write(
        settings.claude_config_file,
        {
            "numStartups": 3,
            "mcpServers": {
                "excalidraw": {
                    "type": "http",
                    "url": "https://excalidraw.example.test/mcp",
                    "headers": {"Authorization": "Bearer abc-secret-123"},
                },
                "blender": {"type": "stdio", "command": "uvx", "args": ["blender-mcp"], "env": {}},
            },
            "projects": {
                str(folder): {
                    "mcpServers": {
                        "db": {"command": "npx", "args": ["pg"], "env": {"DB_PASSWORD": "pw-777"}}
                    }
                },
                str(tmp_path / "otro"): {"mcpServers": {}},
            },
        },
    )
    mcp_json = _write(
        folder / ".mcp.json", {"mcpServers": {"local": {"command": "node", "args": ["srv.js"]}}}
    )
    agy = _write(
        settings.agy_mcp_config_file,
        {"mcpServers": {"gem": {"url": "https://gem.example.test/mcp"}}},
    )
    return {
        "project": project["id"],
        "claude": claude,
        "mcp_json": mcp_json,
        "agy": agy,
        "folder": folder,
    }


def test_every_source_is_listed_without_secret_values(
    client: TestClient, settings: Settings, tmp_path: Path
):
    _setup(client, settings, tmp_path)
    response = client.get("/api/connections/import/scan")
    assert response.status_code == 200
    found = {(f["source"], f["name"]): f for f in response.json()}
    assert set(found) == {
        ("claude", "excalidraw"),
        ("claude", "blender"),
        ("claude-project", "db"),
        ("mcp-json", "local"),
        ("agy", "gem"),
    }
    assert found[("claude", "excalidraw")]["has_secrets"] is True
    assert found[("claude", "excalidraw")]["header_keys"] == ["Authorization"]
    assert found[("claude", "blender")]["target"] == "uvx blender-mcp"
    assert "abc-secret-123" not in response.text and "pw-777" not in response.text
    assert all(f["imported"] is False for f in found.values())


def test_importing_stores_the_secrets_and_gives_each_one_its_level(
    client: TestClient, settings: Settings, tmp_path: Path, credential_store
):
    data = _setup(client, settings, tmp_path)
    before = {
        name: _hash(path)
        for name, path in (
            ("claude", data["claude"]),
            ("mcp", data["mcp_json"]),
            ("agy", data["agy"]),
        )
    }
    ids = {
        (f["source"], f["name"]): f["id"] for f in client.get("/api/connections/import/scan").json()
    }
    response = client.post(
        "/api/connections/import",
        json={
            "items": [
                {"id": ids[("claude", "excalidraw")], "scope": "general"},
                {
                    "id": ids[("claude-project", "db")],
                    "scope": "project",
                    "project_id": data["project"],
                },
                {
                    "id": ids[("mcp-json", "local")],
                    "scope": "project",
                    "project_id": data["project"],
                },
                {"id": ids[("agy", "gem")], "scope": "general", "name": "gemini"},
            ]
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["problems"] == []
    created = {c["name"]: c for c in result["created"]}
    assert set(created) == {"excalidraw", "db", "local", "gemini"}
    assert created["excalidraw"]["origin"] == "import"
    assert created["excalidraw"]["headers"] == {"Authorization": "Bearer ${secret:AUTHORIZATION}"}
    assert created["db"]["env"] == {"DB_PASSWORD": "${secret:DB_PASSWORD}"}
    assert created["db"]["assignments"][0]["project_id"] == data["project"]
    assert created["excalidraw"]["assignments"][0]["scope"] == "general"
    assert secrets.get(created["excalidraw"]["id"], "AUTHORIZATION") == "abc-secret-123"
    assert secrets.get(created["db"]["id"], "DB_PASSWORD") == "pw-777"
    assert "abc-secret-123" not in json.dumps(result) and "pw-777" not in json.dumps(result)
    # the originals are the same bytes (CA9)
    assert before == {
        "claude": _hash(data["claude"]),
        "mcp": _hash(data["mcp_json"]),
        "agy": _hash(data["agy"]),
    }


def test_what_is_already_imported_is_marked_and_a_taken_name_gets_a_number(
    client: TestClient, settings: Settings, tmp_path: Path
):
    _setup(client, settings, tmp_path)
    ids = {
        (f["source"], f["name"]): f["id"] for f in client.get("/api/connections/import/scan").json()
    }
    client.post("/api/connections/import", json={"items": [{"id": ids[("claude", "blender")]}]})
    again = {(f["source"], f["name"]): f for f in client.get("/api/connections/import/scan").json()}
    assert again[("claude", "blender")]["imported"] is True
    second = client.post(
        "/api/connections/import", json={"items": [{"id": ids[("claude", "blender")]}]}
    )
    assert [c["name"] for c in second.json()["created"]] == ["blender-2"]


def test_an_entry_that_cannot_be_imported_does_not_stop_the_others(
    client: TestClient, settings: Settings, tmp_path: Path
):
    data = _setup(client, settings, tmp_path)
    ids = {
        (f["source"], f["name"]): f["id"] for f in client.get("/api/connections/import/scan").json()
    }
    response = client.post(
        "/api/connections/import",
        json={
            "items": [
                {"id": "no-such-entry"},
                {
                    "id": ids[("claude", "blender")],
                    "scope": "project",
                    "project_id": "no-such-project",
                },
                {"id": ids[("agy", "gem")]},
            ]
        },
    )
    result = response.json()
    assert [c["name"] for c in result["created"]] == ["gem"]
    assert len(result["problems"]) == 2
    assert client.get("/api/connections").json()[0]["name"] == "gem"
    assert data["claude"].exists()


def test_unreadable_or_missing_files_are_just_empty(client: TestClient, settings: Settings):
    settings.claude_config_file.write_text("{not json", encoding="utf-8")
    assert client.get("/api/connections/import/scan").json() == []
