"""Testing a connection (phase 18, block 3): CA4 (the tools of a stdio and an HTTP server with
their schema, and a sentence in Spanish for a missing command, a crash, a timeout, a 401 and an
unreachable URL), what the API keeps of a test, cancelling one, and no secret in the answers."""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from http_server import Running  # tests/fixtures/mcp_servers (conftest puts it on the path)

from agentic_os.services.connections import probe
from agentic_os.services.connections.render import Rendered

SERVER = str(Path(__file__).parent / "fixtures" / "mcp_servers" / "stdio_server.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stdio(client: TestClient, name: str = "probe", env: dict | None = None, **extra) -> dict:
    payload = {"name": name, "command": sys.executable, "args": [SERVER], "env": env or {}, **extra}
    response = client.post("/api/connections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()[0]


def _test(client: TestClient, connection_id: str) -> dict:
    response = client.post(f"/api/connections/{connection_id}/test", params={"wait": True})
    assert response.status_code == 202, response.text
    return response.json()


def _http(client: TestClient, url: str, key: str) -> dict:
    response = client.post(
        "/api/connections",
        json={
            "name": "web",
            "transport": "http",
            "url": url,
            "headers": {"X-Probe-Key": "${secret:KEY}"},
            "secrets": {"KEY": key},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


# -- CA4 ----------------------------------------------------------------------------------------
def test_a_stdio_server_lists_its_tools_with_their_schema(client: TestClient):
    created = _stdio(client)
    done = _test(client, created["id"])
    assert done["state"] == "done" and done["result"]["ok"] is True
    tools = {t["name"]: t for t in done["result"]["tools"]}
    assert set(tools) == {"read_note", "write_note", "show_env"}
    assert tools["read_note"]["read_only"] is True and tools["write_note"]["destructive"] is True
    assert "topic" in tools["read_note"]["input_schema"]["properties"]
    assert tools["read_note"]["description"] == "Read the note about a topic."
    assert done["result"]["server"]["name"] == "probe-stdio"
    kept = done["connection"]
    assert kept["tested_at"] and kept["test_error"] is None and len(kept["tools"]) == 3


def test_an_http_server_with_a_secret_header(client: TestClient):
    with Running("the-key-123", _free_port()) as server:
        created = _http(client, server.url, "the-key-123")
        done = _test(client, created["id"])
        assert done["result"]["ok"] is True, done["result"]
        assert [t["name"] for t in done["result"]["tools"]] == ["ping"]


def test_a_rejected_key_says_401_in_words(client: TestClient):
    with Running("the-key-123", _free_port()) as server:
        created = _http(client, server.url, "WRONG-key-999")
        done = _test(client, created["id"])
        error = done["result"]["error"]
        assert done["result"]["ok"] is False and error["code"] == "unauthorized"
        assert "rechaza las credenciales" in error["message"] and "401" in error["message"]
        assert "WRONG-key-999" not in json.dumps(done)
        assert done["connection"]["test_error"]["code"] == "unauthorized"


def test_an_unreachable_url(client: TestClient):
    created = client.post(
        "/api/connections",
        json={"name": "nada", "transport": "http", "url": f"http://127.0.0.1:{_free_port()}/mcp"},
    ).json()[0]
    error = _test(client, created["id"])["result"]["error"]
    assert error["code"] == "unreachable" and "No se puede conectar" in error["message"]


def test_a_command_that_does_not_exist(client: TestClient):
    created = client.post(
        "/api/connections", json={"name": "raro", "command": "programa-que-no-existe-xyz"}
    ).json()[0]
    error = _test(client, created["id"])["result"]["error"]
    assert error["code"] == "command_not_found"
    assert "programa-que-no-existe-xyz" in error["message"]


@pytest.mark.parametrize(
    ("command", "expected"),
    [("npx", "Node.js"), ("uvx", "uv"), ("docker", "Docker"), ("python3", "Python")],
)
def test_a_missing_runtime_says_what_to_install(client: TestClient, monkeypatch, command, expected):
    monkeypatch.setattr(probe.shutil, "which", lambda name: None)
    created = client.post("/api/connections", json={"name": "rt", "command": command}).json()[0]
    error = _test(client, created["id"])["result"]["error"]
    assert error["code"] == "command_not_found" and f"Falta {expected}" in error["message"]


def test_a_server_that_crashes_shows_what_it_wrote(client: TestClient):
    created = _stdio(client, env={"PROBE_MODE": "crash"})
    error = _test(client, created["id"])["result"]["error"]
    assert error["code"] == "crashed"
    assert "cannot open database (simulated)" in error["message"]


def test_a_secret_the_server_prints_is_hidden(client: TestClient):
    created = _stdio(
        client,
        env={"PROBE_MODE": "leak", "LEAK": "${secret:TOKEN}"},
        secrets={"TOKEN": "tok-9f8e7d6c5b"},
    )
    done = _test(client, created["id"])
    assert done["result"]["error"]["code"] == "crashed"
    assert "tok-9f8e7d6c5b" not in json.dumps(done)
    assert "•••" in done["result"]["error"]["message"]


def test_a_server_that_does_not_answer_in_time(client: TestClient):
    client.put("/api/settings/connections", json={"probe_timeout": 5})
    created = _stdio(client, env={"PROBE_MODE": "slow", "PROBE_DELAY": "30"})
    error = _test(client, created["id"])["result"]["error"]
    assert error["code"] == "timeout" and "no ha respondido a tiempo" in error["message"]


def test_a_missing_secret_is_explained_before_anything_starts(client: TestClient):
    created = _stdio(client, env={"TOKEN": "${secret:TOKEN}"})
    response = client.post(f"/api/connections/{created['id']}/test")
    assert response.status_code == 422 and response.json()["detail"]["code"] == "secret_missing"


# -- what is kept -------------------------------------------------------------------------------
def test_a_failed_test_keeps_the_tools_of_the_last_good_one(client: TestClient):
    created = _stdio(client)
    _test(client, created["id"])
    client.patch(f"/api/connections/{created['id']}", json={"env": {"PROBE_MODE": "crash"}})
    done = _test(client, created["id"])
    assert done["connection"]["test_error"]["code"] == "crashed"
    assert len(done["connection"]["tools"]) == 3  # still there


def test_new_tools_are_noticed_and_stay_out_of_a_selection(client: TestClient):
    created = _stdio(client)
    url = f"/api/connections/{created['id']}"
    first = _test(client, created["id"])["connection"]
    assert first["tools_changed"] is False  # the first test is not a change
    client.patch(url, json={"tool_mode": "selected", "allowed_tools": ["read_note"]})
    client.patch(url, json={"env": {"PROBE_EXTRA_TOOL": "1"}})
    changed = _test(client, created["id"])["connection"]
    assert changed["tools_changed"] is True and len(changed["tools"]) == 4
    assert changed["allowed_tools"] == ["read_note"]  # «extra» is not allowed by itself
    seen = client.patch(url, json={"tools_changed": False}).json()
    assert seen["tools_changed"] is False


def test_allowed_tools_have_to_exist(client: TestClient):
    created = _stdio(client)
    url = f"/api/connections/{created['id']}"
    ok = client.patch(url, json={"allowed_tools": ["whatever"]})  # nothing to compare with yet
    assert ok.status_code == 200
    client.patch(url, json={"allowed_tools": []})
    _test(client, created["id"])
    bad = client.patch(url, json={"tool_mode": "selected", "allowed_tools": ["nope"]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "tool_unknown"
    good = client.patch(
        url,
        json={
            "tool_mode": "selected",
            "allowed_tools": ["read_note"],
            "preapproved_tools": ["read_note"],
        },
    )
    assert good.status_code == 200 and good.json()["preapproved_tools"] == ["read_note"]


# -- background ---------------------------------------------------------------------------------
def test_a_test_can_be_followed_and_cancelled(client: TestClient):
    created = _stdio(client, env={"PROBE_MODE": "slow", "PROBE_DELAY": "30"})
    started = client.post(f"/api/connections/{created['id']}/test").json()
    assert started["state"] == "running"
    assert client.get(f"/api/connections/tests/{started['id']}").json()["state"] == "running"
    assert client.delete(f"/api/connections/tests/{started['id']}").status_code == 204
    running = client.app.state.connection_probes.get(started["id"])
    assert running.done.wait(10)
    assert client.get(f"/api/connections/tests/{started['id']}").json()["state"] == "cancelled"
    assert client.get("/api/connections/tests/none").status_code == 404


def test_requirements_say_which_programs_are_installed(client: TestClient):
    found = {r["program"]: r for r in client.get("/api/connections/requirements").json()}
    assert {"node", "npx", "uvx", "python", "docker"} <= set(found)
    assert isinstance(found["python"]["found"], bool)


def test_the_probe_never_raises_even_with_nonsense():
    result = asyncio.run(probe.probe(Rendered(name="x", transport="http", url="not a url"), 5))
    assert result.ok is False and result.error is not None


@pytest.mark.skipif(
    not os.environ.get("AGENTIC_OS_REAL_NPX"),
    reason="needs Node and the network (set AGENTIC_OS_REAL_NPX=1)",
)
def test_a_real_npx_server(client: TestClient, tmp_path: Path):
    """The filesystem server by `npx`: on Windows `npx` is a .cmd (spike S1)."""
    client.put("/api/settings/connections", json={"probe_timeout": 180})
    created = client.post(
        "/api/connections",
        json={
            "name": "fs",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem@2.0.0", str(tmp_path)],
        },
    ).json()[0]
    done = _test(client, created["id"])
    assert done["result"]["ok"] is True, done["result"]
    assert "list_allowed_directories" in {t["name"] for t in done["result"]["tools"]}
