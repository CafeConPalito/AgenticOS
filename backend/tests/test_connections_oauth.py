"""OAuth for the remote connections (phase 18, block 6): CA8 (the login with dynamic registration
and with a pasted client id, the tokens in the credential store, the header a run receives, a token
about to expire renewed before a run, a failed renewal that leaves the connection waiting for a new
login with a notice in the Inbox, and disconnecting)."""

import json
import socket
import time

import httpx
from fastapi.testclient import TestClient
from oauth_server import Running

from agentic_os.models import Cli
from agentic_os.services.connections import oauth, runtime, secrets


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _connection(client: TestClient, server: Running, name: str = "linear") -> dict:
    response = client.post(
        "/api/connections",
        json={
            "name": name,
            "transport": "http",
            "url": server.url,
            "auth": "oauth",
            "level": {"scope": "general"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def _login(client: TestClient, connection_id: str, **body) -> dict:
    """«Conectar» as the person does it: open the page the app gives, click Allow."""
    started = client.post(f"/api/connections/{connection_id}/oauth/start", json=body)
    assert started.status_code == 200, started.text
    flow = started.json()
    if flow["state"] == "waiting":
        httpx.get(flow["authorization_url"], follow_redirects=True, timeout=15)  # the browser
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            flow = client.get(f"/api/connections/oauth/flows/{flow['id']}").json()
            if flow["state"] not in ("waiting", "starting"):
                break
            time.sleep(0.2)
    return flow


def _tokens(connection_id: str) -> dict:
    return oauth.stored_tokens(connection_id) or {}


# -- connecting ---------------------------------------------------------------------------------
def test_connect_with_dynamic_registration_keeps_the_tokens_in_the_credential_store(
    client: TestClient,
):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        assert made["oauth"] is None
        flow = _login(client, made["id"])
        assert flow["state"] == "done", flow
        assert (
            flow["redirect_uri"].startswith("http://127.0.0.1:")
            and "/callback" in flow["redirect_uri"]
        )
        connected = flow["connection"]["oauth"]
        assert connected["status"] == "connected" and connected["client_pasted"] is False
        assert "oauth-probe" in connected["account_label"] and connected["expires_at"]
        assert server.auth.log[0].startswith("register dyn-")
        # the tokens are in the store and nowhere else
        tokens = _tokens(made["id"])
        assert tokens["access_token"].startswith("at-") and tokens["refresh_token"].startswith(
            "rt-"
        )
        everything = json.dumps(client.get("/api/connections").json()) + json.dumps(flow)
        assert (
            tokens["access_token"] not in everything and tokens["refresh_token"] not in everything
        )
        # and the connection can be tested with it
        tested = client.post(f"/api/connections/{made['id']}/test", params={"wait": True}).json()
        assert tested["result"]["ok"] is True, tested["result"]


def test_the_login_works_for_a_service_that_wants_a_pasted_client_id(client: TestClient):
    port = _free_port()
    client.put("/api/settings/connections", json={"oauth_port": port})
    with Running(_free_port(), pasted_redirect=f"http://127.0.0.1:{port}/callback") as server:
        made = _connection(client, server)
        flow = _login(client, made["id"], client_id="pasted-client")
        assert flow["state"] == "done", flow
        assert flow["redirect_uri"] == f"http://127.0.0.1:{port}/callback"
        login = flow["connection"]["oauth"]
        assert login["client_pasted"] is True
        assert not [line for line in server.auth.log if line.startswith("register")]  # no dynamic


def test_a_pasted_client_needs_its_port_and_says_so_when_it_is_taken(client: TestClient):
    port = _free_port()
    client.put("/api/settings/connections", json={"oauth_port": port})
    with Running(_free_port()) as server, socket.socket() as busy:
        busy.bind(("127.0.0.1", port))
        busy.listen()
        made = _connection(client, server)
        response = client.post(
            f"/api/connections/{made['id']}/oauth/start", json={"client_id": "pasted-client"}
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "oauth_port_busy"
        assert str(port) in response.json()["detail"]["message"]
        # with dynamic registration a busy port is just another one
        other = _login(client, made["id"])
        assert other["state"] == "done" and f":{port}/" not in other["redirect_uri"]


def test_a_refusal_in_the_browser_is_explained(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        started = client.post(f"/api/connections/{made['id']}/oauth/start", json={}).json()
        callback = started["redirect_uri"]
        httpx.get(f"{callback}?error=access_denied&error_description=Denegado", timeout=10)
        deadline = time.monotonic() + 20
        flow = started
        while time.monotonic() < deadline and flow["state"] in ("waiting", "starting"):
            time.sleep(0.2)
            flow = client.get(f"/api/connections/oauth/flows/{started['id']}").json()
        assert flow["state"] == "failed" and "Denegado" in flow["error"]
        assert _tokens(made["id"]) == {}


def test_a_login_can_be_cancelled(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        started = client.post(f"/api/connections/{made['id']}/oauth/start", json={}).json()
        assert started["state"] == "waiting"
        assert client.delete(f"/api/connections/oauth/flows/{started['id']}").status_code == 204
        running = client.app.state.oauth_flows.get(started["id"])
        assert running.done.wait(10) and running.state == "cancelled"
        assert client.delete("/api/connections/oauth/flows/none").status_code == 404


def test_only_remote_oauth_connections_can_log_in(client: TestClient):
    plain = client.post("/api/connections", json={"name": "local", "command": "x"}).json()[0]
    response = client.post(f"/api/connections/{plain['id']}/oauth/start", json={})
    assert (
        response.status_code == 422 and response.json()["detail"]["code"] == "oauth_not_applicable"
    )


# -- what a run gets ----------------------------------------------------------------------------
def test_a_run_gets_the_access_token_and_never_the_refresh_token(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        with client.app.state.sessionmaker() as db:
            prepared = runtime.prepare(db, Cli.CLAUDE.value, None, None, None)
            agy = runtime.prepare(db, Cli.AGY.value, None, None, None)
        tokens = _tokens(made["id"])
        item = prepared.items[0]
        assert item.sent and item.entry["headers"] == {
            "Authorization": "Bearer ${AOS_MCP_1_OAUTH_TOKEN}"
        }
        assert prepared.env == {"AOS_MCP_1_OAUTH_TOKEN": tokens["access_token"]}
        assert tokens["refresh_token"] not in json.dumps(item.entry) + json.dumps(prepared.env)
        assert agy.items[0].entry["headers"] == {
            "Authorization": f"Bearer {tokens['access_token']}"
        }
        assert tokens["access_token"] in prepared.secret_values  # hidden from the terminal


def test_a_token_about_to_expire_is_renewed_before_the_run(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        before = _tokens(made["id"])
        # it dies in 3 minutes: inside the margin
        secrets.put(
            made["id"], oauth.TOKENS_KEY, json.dumps({**before, "expires_at": time.time() + 180})
        )
        with client.app.state.sessionmaker() as db:
            prepared = runtime.prepare(db, Cli.CLAUDE.value, None, None, None)
        after = _tokens(made["id"])
        assert prepared.items[0].sent
        assert "refresh used" in server.auth.log
        assert after["access_token"] != before["access_token"]
        assert prepared.env["AOS_MCP_1_OAUTH_TOKEN"] == after["access_token"]
        assert after["expires_at"] > time.time() + 3000


def test_a_token_with_time_left_is_not_renewed(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        with client.app.state.sessionmaker() as db:
            runtime.prepare(db, Cli.CLAUDE.value, None, None, None)
        assert "refresh used" not in server.auth.log


def test_a_failed_renewal_waits_for_a_new_login_and_tells_the_inbox(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        server.auth.refuse_refresh = True
        tokens = _tokens(made["id"])
        secrets.put(
            made["id"], oauth.TOKENS_KEY, json.dumps({**tokens, "expires_at": time.time() + 60})
        )
        with client.app.state.sessionmaker() as db:
            prepared = runtime.prepare(db, Cli.CLAUDE.value, None, None, None)
            db.commit()
        item = prepared.items[0]
        assert item.status == "skipped" and "volver a conectar" in item.detail
        assert not prepared  # the run goes on without it
        listed = client.get(f"/api/connections/{made['id']}").json()
        assert listed["oauth"]["status"] == "needs_reauth"
        alerts = [i for i in client.get("/api/inbox").json() if i["kind"] == "connection"]
        assert len(alerts) == 1 and alerts[0]["connection_id"] == made["id"]
        assert "Vuelve a conectar «linear»" in alerts[0]["title"]
        # a second run does not pile up more notices
        with client.app.state.sessionmaker() as db:
            runtime.prepare(db, Cli.CLAUDE.value, None, None, None)
            db.commit()
        assert len([i for i in client.get("/api/inbox").json() if i["kind"] == "connection"]) == 1
        # connecting again fixes it and clears the notice
        server.auth.refuse_refresh = False
        flow = _login(client, made["id"])
        assert flow["state"] == "done" and flow["connection"]["oauth"]["status"] == "connected"
        assert not [
            i
            for i in client.get("/api/inbox").json()
            if i["kind"] == "connection" and i["status"] == "pending"
        ]
        with client.app.state.sessionmaker() as db:
            assert runtime.prepare(db, Cli.CLAUDE.value, None, None, None).items[0].sent


def test_the_background_renewer_renews_what_is_about_to_expire(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        before = _tokens(made["id"])
        secrets.put(
            made["id"], oauth.TOKENS_KEY, json.dumps({**before, "expires_at": time.time() + 900})
        )
        assert oauth.renew_expiring(client.app.state.sessionmaker, within=1800) == 1
        assert _tokens(made["id"])["access_token"] != before["access_token"]
        assert oauth.renew_expiring(client.app.state.sessionmaker, within=1800) == 0  # fresh now


def test_manual_renewal(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        ok = client.post(f"/api/connections/{made['id']}/oauth/refresh")
        assert ok.status_code == 200 and ok.json()["oauth"]["status"] == "connected"
        server.auth.refuse_refresh = True
        tokens = _tokens(made["id"])
        secrets.put(
            made["id"], oauth.TOKENS_KEY, json.dumps({**tokens, "expires_at": time.time() + 30})
        )
        bad = client.post(f"/api/connections/{made['id']}/oauth/refresh")
        assert bad.status_code == 422 and bad.json()["detail"]["code"] == "oauth_needs_login"


# -- disconnecting ------------------------------------------------------------------------------
def test_disconnecting_revokes_and_forgets(client: TestClient):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        tokens = _tokens(made["id"])
        done = client.post(f"/api/connections/{made['id']}/oauth/disconnect").json()
        assert done["oauth"]["status"] == "disconnected" and done["oauth"]["account_label"] == ""
        assert tokens["refresh_token"] in server.auth.revoked
        assert _tokens(made["id"]) == {} and oauth.stored_client(made["id"]) == {}
        with client.app.state.sessionmaker() as db:
            item = runtime.prepare(db, Cli.CLAUDE.value, None, None, None).items[0]
        assert item.status == "skipped" and "Conecta la cuenta" in item.detail


def test_deleting_the_connection_forgets_its_login(client: TestClient, credential_store):
    with Running(_free_port()) as server:
        made = _connection(client, server)
        _login(client, made["id"])
        assert credential_store.entries
        client.delete(f"/api/connections/{made['id']}")
        assert not credential_store.entries


def test_the_expiry_check(client: TestClient):
    secrets.put(
        "c1", oauth.TOKENS_KEY, json.dumps({"access_token": "a", "expires_at": time.time() + 100})
    )
    assert oauth.expires_soon("c1") and not oauth.expires_soon("c1", 10)
    assert oauth.expires_soon("nothing")


def test_the_login_page_is_opened_by_the_backend(client: TestClient, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("agentic_os.services.proc.open_url", lambda url: opened.append(url) or True)
    with Running(_free_port()) as server:
        made = _connection(client, server)
        started = client.post(f"/api/connections/{made['id']}/oauth/start", json={}).json()
        assert client.post(f"/api/connections/oauth/flows/{started['id']}/open").status_code == 204
        assert opened == [started["authorization_url"]]
        assert client.post("/api/connections/oauth/flows/none/open").status_code == 404
        client.delete(f"/api/connections/oauth/flows/{started['id']}")


def test_only_web_addresses_can_be_opened():
    import pytest as _pytest

    from agentic_os.services import proc

    with _pytest.raises(ValueError):
        proc.open_url("file:///etc/passwd")
