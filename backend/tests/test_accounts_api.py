"""The accounts and teams API (phase 10): CRUD, the links from agents, the per-account limits
and the session probe through the (fake) CLI."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings

FAKE = str(Path(__file__).parent / "fake_cli.py")


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    command = [sys.executable, FAKE]
    return settings.model_copy(
        update={"cli_command_overrides": {"claude": command, "agy": command}}
    )


@pytest.fixture
def fake_client(fake_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(fake_settings)) as client:
        yield client


def by_cli(client: TestClient, cli: str) -> dict:
    return next(a for a in client.get("/api/accounts").json() if a["cli"] == cli)


def new_account(client: TestClient, label: str = "Personal") -> dict:
    response = client.post("/api/accounts", json={"cli": "claude", "label": label})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- accounts
def test_a_fresh_install_has_the_two_system_accounts(client: TestClient):
    accounts = client.get("/api/accounts").json()
    assert {(a["cli"], a["is_system"], a["is_default"]) for a in accounts} == {
        ("claude", True, True),
        ("agy", True, True),
    }
    claude = by_cli(client, "claude")
    assert claude["name"] == "Cuenta del sistema" and claude["unit"] == "usd"
    assert claude["quota"] == [] and claude["agents"] == [] and claude["live_runs"] == 0
    assert by_cli(client, "agy")["unit"] == "tokens"


def test_create_edit_default_and_delete_an_account(client: TestClient, settings: Settings):
    account = new_account(client)
    assert (account["label"], account["name"], account["is_system"]) == (
        "Personal",
        "Personal",
        False,
    )
    assert (Path(settings.data_dir) / "accounts" / account["id"]).is_dir()

    edited = client.patch(f"/api/accounts/{account['id']}", json={"label": "Trabajo"}).json()
    assert edited["name"] == "Trabajo"
    limited = client.patch(f"/api/accounts/{account['id']}", json={"daily_limit": 12.5}).json()
    assert limited["daily_limit"] == 12.5 and limited["label"] == "Trabajo"  # untouched
    cleared = client.patch(f"/api/accounts/{account['id']}", json={"daily_limit": None}).json()
    assert cleared["daily_limit"] is None
    assert (
        client.patch(f"/api/accounts/{account['id']}", json={"daily_limit": 0}).status_code == 422
    )

    made = client.post(f"/api/accounts/{account['id']}/default").json()
    assert made["is_default"] is True
    system_claude = next(
        a for a in client.get("/api/accounts").json() if a["cli"] == "claude" and a["is_system"]
    )
    assert by_cli(client, "agy")["is_default"] and not system_claude["is_default"]

    assert client.delete(f"/api/accounts/{account['id']}").status_code == 204
    assert not (Path(settings.data_dir) / "accounts" / account["id"]).exists()
    assert by_cli(client, "claude")["is_system"] and by_cli(client, "claude")["is_default"]


def test_the_rules_of_accounts(client: TestClient):
    system = by_cli(client, "claude")
    assert (
        client.delete(f"/api/accounts/{system['id']}").json()["detail"]["code"] == "system_account"
    )
    refused = client.post("/api/accounts", json={"cli": "agy"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "accounts_unsupported"
    assert client.get("/api/accounts/nope").status_code in (404, 405)
    assert client.patch("/api/accounts/nope", json={}).status_code == 404
    assert client.delete("/api/accounts/nope").status_code == 404

    account = new_account(client)
    agent = client.post("/api/agents", json={"name": "Dev", "account_id": account["id"]}).json()
    in_use = client.delete(f"/api/accounts/{account['id']}")
    assert in_use.status_code == 409 and in_use.json()["detail"]["code"] == "account_in_use"
    client.patch(f"/api/agents/{agent['id']}", json={"account_id": None})
    assert client.delete(f"/api/accounts/{account['id']}").status_code == 204


def test_an_account_lists_the_agents_that_use_it(client: TestClient):
    account = new_account(client)
    own = client.post("/api/agents", json={"name": "Propio", "account_id": account["id"]}).json()
    plain = client.post("/api/agents", json={"name": "Normal"}).json()
    agy = client.post("/api/agents", json={"name": "Gema", "cli": "agy"}).json()
    names = lambda a: [x["name"] for x in a["agents"]]  # noqa: E731
    assert names(
        next(a for a in client.get("/api/accounts").json() if a["id"] == account["id"])
    ) == ["Propio"]
    # An agent without account counts for the default one of its CLI.
    assert names(by_cli(client, "claude")) == ["Normal"] and names(by_cli(client, "agy")) == [
        "Gema"
    ]
    assert {own["account_id"], plain["account_id"], agy["account_id"]} == {account["id"], None}


# ---------------------------------------------------------------- agents link to teams and accounts
def test_agents_point_to_a_team_and_an_account_of_their_cli(client: TestClient):
    team = client.post("/api/teams", json={"name": "Producto"}).json()
    account = new_account(client)
    agent = client.post(
        "/api/agents", json={"name": "Dev", "team_id": team["id"], "account_id": account["id"]}
    ).json()
    assert (agent["team_id"], agent["account_id"]) == (team["id"], account["id"])
    home = client.get("/api/home").json()["agents"][0]
    assert (home["team_id"], home["account_id"]) == (team["id"], account["id"])

    wrong = client.post(
        "/api/agents", json={"name": "Gema", "cli": "agy", "account_id": account["id"]}
    )
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "account_cli_mismatch"
    ghost = client.patch(f"/api/agents/{agent['id']}", json={"team_id": "nope"})
    assert ghost.status_code == 422 and ghost.json()["detail"]["code"] == "team_not_found"
    ghost = client.patch(f"/api/agents/{agent['id']}", json={"account_id": "nope"})
    assert ghost.json()["detail"]["code"] == "account_not_found"

    # Changing the CLI leaves the Claude account behind; the team stays.
    switched = client.patch(f"/api/agents/{agent['id']}", json={"cli": "agy"}).json()
    assert (switched["cli"], switched["team_id"], switched["account_id"]) == (
        "agy",
        team["id"],
        None,
    )
    # An explicit null takes the team away.
    assert (
        client.patch(f"/api/agents/{agent['id']}", json={"team_id": None}).json()["team_id"] is None
    )
    # Leaving the fields out changes nothing.
    client.patch(f"/api/agents/{agent['id']}", json={"team_id": team["id"]})
    assert (
        client.patch(f"/api/agents/{agent['id']}", json={"name": "Otro"}).json()["team_id"]
        == team["id"]
    )


# ---------------------------------------------------------------- teams
def test_teams_group_agents_and_an_agent_is_in_one(client: TestClient):
    a, b, c = (client.post("/api/agents", json={"name": n}).json()["id"] for n in "ABC")
    first = client.post("/api/teams", json={"name": " Producto ", "agent_ids": [a, b]}).json()
    assert (first["name"], first["agent_ids"], first["position"]) == ("Producto", [a, b], 0)
    second = client.post("/api/teams", json={"name": "Contenidos", "agent_ids": [b, c]}).json()
    assert second["position"] == 1 and second["agent_ids"] == [b, c]
    # B moved: it is no longer in the first team.
    assert client.get(f"/api/teams/{first['id']}").json()["agent_ids"] == [a]
    assert [t["name"] for t in client.get("/api/teams").json()] == ["Producto", "Contenidos"]

    renamed = client.patch(f"/api/teams/{first['id']}", json={"name": "Producto 2"}).json()
    assert renamed["name"] == "Producto 2" and renamed["agent_ids"] == [a]  # members untouched
    emptied = client.patch(f"/api/teams/{second['id']}", json={"agent_ids": [c]}).json()
    assert emptied["agent_ids"] == [c]
    assert client.get(f"/api/agents/{b}").json()["team_id"] is None  # left

    assert client.delete(f"/api/teams/{first['id']}").status_code == 204
    assert client.get(f"/api/agents/{a}").json()["team_id"] is None  # the agent stays
    assert client.get(f"/api/teams/{first['id']}").status_code == 404


def test_team_validation(client: TestClient):
    assert client.post("/api/teams", json={"name": "  "}).status_code == 422
    missing = client.post("/api/teams", json={"name": "X", "agent_ids": ["nope"]})
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "agent_not_found"
    assert client.get("/api/teams").json() == []  # nothing was half-created? (rolled back)


# ---------------------------------------------------------------- limits
def test_the_limits_are_set_per_account(client: TestClient):
    claude, agy = by_cli(client, "claude"), by_cli(client, "agy")
    other = new_account(client)
    states = client.put(
        "/api/settings/usage-limits",
        json={
            "limits": [
                {"account_id": claude["id"], "daily_limit": 25},
                {"account_id": agy["id"], "daily_limit": 2_000_000.7},
                {"account_id": other["id"], "daily_limit": None},
            ]
        },
    ).json()
    by_id = {s["account_id"]: s for s in states}
    assert by_id[claude["id"]]["limit"] == 25 and by_id[claude["id"]]["unit"] == "usd"
    assert by_id[agy["id"]]["limit"] == 2_000_001  # whole tokens
    assert by_id[other["id"]]["limit"] is None
    assert by_id[other["id"]]["account_name"] == "Personal" and by_id[claude["id"]]["is_default"]
    assert client.get("/api/settings/usage-limits").json() == states
    assert client.get("/api/usage/today").json()["limits"] == states

    unknown = client.put(
        "/api/settings/usage-limits", json={"limits": [{"account_id": "nope", "daily_limit": 1}]}
    )
    assert unknown.status_code == 404
    assert client.put("/api/settings/usage-limits", json={"claude_usd": 1}).status_code == 422


# ---------------------------------------------------------------- the session probe
def test_probing_an_account_reads_its_email_and_session(
    fake_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FAKE_CLI_EMAIL", "marta@estudio.es")
    monkeypatch.setenv("FAKE_CLI_PLAN", "max")
    account = new_account(fake_client)
    assert account["session_state"] == "unknown"
    probed = fake_client.post(f"/api/accounts/{account['id']}/probe").json()
    assert (probed["session_state"], probed["email"], probed["plan"]) == (
        "ok",
        "marta@estudio.es",
        "max",
    )
    assert probed["name"] == "marta@estudio.es" and probed["session_checked_at"]


def test_a_logged_out_account_raises_a_notice_that_goes_away_when_it_is_back(
    fake_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    account = new_account(fake_client)
    fake_client.post("/api/agents", json={"name": "Dev", "account_id": account["id"]})
    monkeypatch.setenv("FAKE_CLI_AUTH", "down")
    down = fake_client.post(f"/api/accounts/{account['id']}/probe").json()
    assert down["session_state"] == "down"
    notices = [i for i in fake_client.get("/api/inbox").json() if i["kind"] == "account"]
    assert len(notices) == 1 and notices[0]["title"].startswith("La sesión de Claude Code")

    fake_client.post(f"/api/accounts/{account['id']}/probe")  # still down: still one notice
    assert len([i for i in fake_client.get("/api/inbox").json() if i["kind"] == "account"]) == 1
    monkeypatch.delenv("FAKE_CLI_AUTH")
    assert fake_client.post(f"/api/accounts/{account['id']}/probe").json()["session_state"] == "ok"
    assert [i for i in fake_client.get("/api/inbox").json() if i["kind"] == "account"] == []


def test_probing_without_the_cli_installed_says_so(client: TestClient, monkeypatch):
    from agentic_os.services.runs import launcher

    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    response = client.post(f"/api/accounts/{by_cli(client, 'claude')['id']}/probe")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "cli_not_installed"


def test_a_token_limit_that_rounds_to_zero_is_refused_by_both_endpoints(client: TestClient):
    agy = by_cli(client, "agy")
    patched = client.patch(f"/api/accounts/{agy['id']}", json={"daily_limit": 0.4})
    assert patched.status_code == 422 and patched.json()["detail"]["code"] == "invalid_limit"
    put = client.put(
        "/api/settings/usage-limits",
        json={"limits": [{"account_id": agy["id"], "daily_limit": 0.4}]},
    )
    assert put.status_code == 422 and put.json()["detail"]["code"] == "invalid_limit"
    assert by_cli(client, "agy")["daily_limit"] is None  # nothing half-saved
    assert (
        client.patch(f"/api/accounts/{agy['id']}", json={"daily_limit": 1}).json()["daily_limit"]
        == 1
    )


def test_probing_a_missing_cli_is_refused_without_touching_the_account(
    client: TestClient, monkeypatch
):
    from agentic_os.services.runs import launcher

    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    claude = by_cli(client, "claude")
    refused = client.post(f"/api/accounts/{claude['id']}/probe")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "cli_not_installed"
