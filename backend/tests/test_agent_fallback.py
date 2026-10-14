"""The secondary CLI of an agent (phase 10 amendment): API validation and the way back."""

from datetime import timedelta

from fastapi.testclient import TestClient

from agentic_os.db.base import utcnow
from agentic_os.models import Agent


def account_of(client: TestClient, cli: str) -> dict:
    return next(a for a in client.get("/api/accounts").json() if a["cli"] == cli)


def set_switch(client: TestClient, agent_id: str, until) -> None:
    with client.app.state.sessionmaker() as db:
        db.get(Agent, agent_id).using_fallback_until = until
        db.commit()


def new_agent(client: TestClient, **extra) -> dict:
    res = client.post("/api/agents", json={"name": "Dev", **extra})
    assert res.status_code == 201, res.text
    return res.json()


def test_agent_without_secondary_by_default(client):
    agent = new_agent(client)
    assert agent["fallback_account_id"] is None
    assert agent["fallback_model"] == ""
    assert agent["using_fallback"] is False


def test_set_and_clear_the_secondary(client):
    agy = account_of(client, "agy")
    agent = new_agent(client)
    res = client.patch(
        f"/api/agents/{agent['id']}",
        json={"fallback_account_id": agy["id"], "fallback_model": "gemini-3"},
    )
    assert res.status_code == 200
    assert res.json()["fallback_account_id"] == agy["id"]
    assert res.json()["fallback_model"] == "gemini-3"
    # An empty id (what the select emits for «none») removes it, and the model with it.
    res = client.patch(f"/api/agents/{agent['id']}", json={"fallback_account_id": ""})
    assert res.json()["fallback_account_id"] is None
    assert res.json()["fallback_model"] == ""


def test_secondary_cannot_be_the_main_account(client):
    claude = account_of(client, "claude")
    agent = new_agent(client)
    res = client.patch(f"/api/agents/{agent['id']}", json={"fallback_account_id": claude["id"]})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "fallback_same_account"


def test_secondary_must_exist(client):
    agent = new_agent(client)
    res = client.patch(f"/api/agents/{agent['id']}", json={"fallback_account_id": "nope"})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "account_not_found"


def test_clear_goes_back_to_the_main_cli(client):
    agy = account_of(client, "agy")
    agent = new_agent(client, fallback_account_id=agy["id"])
    set_switch(client, agent["id"], utcnow() + timedelta(hours=2))
    assert client.get(f"/api/agents/{agent['id']}").json()["using_fallback"] is True
    res = client.post(f"/api/agents/{agent['id']}/fallback/clear")
    assert res.status_code == 200
    assert res.json()["using_fallback"] is False


def test_a_past_switch_no_longer_counts(client):
    agy = account_of(client, "agy")
    agent = new_agent(client, fallback_account_id=agy["id"])
    set_switch(client, agent["id"], utcnow() - timedelta(minutes=1))
    assert client.get(f"/api/agents/{agent['id']}").json()["using_fallback"] is False


def test_an_account_used_as_secondary_cannot_be_deleted(client):
    second = client.post("/api/accounts", json={"cli": "claude", "label": "Second"}).json()
    agent = new_agent(client, cli="agy")
    res = client.patch(f"/api/agents/{agent['id']}", json={"fallback_account_id": second["id"]})
    assert res.status_code == 200
    res = client.delete(f"/api/accounts/{second['id']}")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "account_in_use"


def test_duplicate_keeps_the_secondary(client):
    agy = account_of(client, "agy")
    agent = new_agent(client, fallback_account_id=agy["id"], fallback_model="m")
    copy = client.post(f"/api/agents/{agent['id']}/duplicate").json()
    assert copy["fallback_account_id"] == agy["id"]
    assert copy["fallback_model"] == "m"
