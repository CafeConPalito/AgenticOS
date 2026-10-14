"""The secondary CLI and the switch alert (phase 10 amendment): detection, the wait for the
person's decision, the choice and the way back."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from agentic_os.db.base import utcnow
from agentic_os.models import Agent, CliAccount, InboxItem, InboxKind, InboxStatus, SessionState
from agentic_os.services import accounts
from agentic_os.services.quota import QuotaWindow
from agentic_os.services.usage import switching


def account_of(client: TestClient, cli: str) -> dict:
    return next(a for a in client.get("/api/accounts").json() if a["cli"] == cli)


def set_quota(client: TestClient, account_id: str, pct: float, hours: int = 3) -> None:
    now = utcnow()
    with client.app.state.sessionmaker() as db:
        account = db.get(CliAccount, account_id)
        accounts.record_quota(
            account, [QuotaWindow("five_hour", pct, now + timedelta(hours=hours))], now
        )
        db.commit()


def sync(client: TestClient) -> None:
    with client.app.state.sessionmaker() as db:
        switching.sync_switch_items(db)
        db.commit()


def switch_items(client: TestClient) -> list[dict]:
    items = client.get("/api/inbox").json()
    items = items["items"] if isinstance(items, dict) else items
    return [i for i in items if i["kind"] == "switch"]


def agent_with_secondary(client: TestClient) -> tuple[dict, dict, dict]:
    claude, agy = account_of(client, "claude"), account_of(client, "agy")
    agent = client.post(
        "/api/agents",
        json={"name": "Dev", "fallback_account_id": agy["id"], "fallback_model": "g3"},
    ).json()
    return agent, claude, agy


def test_no_alert_below_the_threshold(client):
    _, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 89)
    sync(client)
    assert switch_items(client) == []


def test_alert_at_the_threshold_once_per_agent(client):
    agent, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 91)
    sync(client)
    sync(client)
    items = switch_items(client)
    assert len(items) == 1
    assert items[0]["agent_id"] == agent["id"]
    assert len(items[0]["options"]) == 2


def test_agent_without_secondary_gets_no_alert(client):
    claude = account_of(client, "claude")
    client.post("/api/agents", json={"name": "Dev"})
    set_quota(client, claude["id"], 99)
    sync(client)
    assert switch_items(client) == []


def test_threshold_is_adjustable(client):
    _, claude, _ = agent_with_secondary(client)
    assert client.get("/api/settings/switch-threshold").json() == {"threshold": 90}
    assert client.put("/api/settings/switch-threshold", json={"threshold": 70}).status_code == 200
    set_quota(client, claude["id"], 75)
    sync(client)
    assert len(switch_items(client)) == 1
    assert client.put("/api/settings/switch-threshold", json={"threshold": 20}).status_code == 422


def test_queued_tasks_wait_for_the_decision(client):
    agent, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 95)
    sync(client)
    with client.app.state.sessionmaker() as db:
        assert switching.decisions_pending(db) == {agent["id"]}


def test_switch_runs_the_agent_with_the_secondary_until_the_reset(client):
    agent, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 95, hours=3)
    sync(client)
    item = switch_items(client)[0]
    res = client.post(f"/api/inbox/{item['id']}/switch", json={"choice": "switch"})
    assert res.status_code == 200, res.text
    read = client.get(f"/api/agents/{agent['id']}").json()
    assert read["using_fallback"] is True
    with client.app.state.sessionmaker() as db:
        row = db.get(Agent, agent["id"])
        reset = accounts.highest_quota(db.get(CliAccount, claude["id"])).resets_at
        assert row.using_fallback_until == reset
        assert switching.decisions_pending(db) == set()
    # No new alert while it runs with the secondary.
    sync(client)
    assert switch_items(client) == []
    # Going back early.
    assert (
        client.post(f"/api/agents/{agent['id']}/fallback/clear").json()["using_fallback"] is False
    )


def test_stay_silences_the_alert_until_the_reset(client):
    agent, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 95)
    sync(client)
    item = switch_items(client)[0]
    assert (
        client.post(f"/api/inbox/{item['id']}/switch", json={"choice": "stay"}).status_code == 200
    )
    assert client.get(f"/api/agents/{agent['id']}").json()["using_fallback"] is False
    sync(client)
    assert switch_items(client) == []


def test_the_alert_goes_away_when_the_window_resets(client):
    _, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 95)
    sync(client)
    assert len(switch_items(client)) == 1
    set_quota(client, claude["id"], 10)
    sync(client)
    assert switch_items(client) == []


def test_unusable_secondary_is_explained_and_does_not_hold_the_queue(client):
    _, claude, agy = agent_with_secondary(client)
    with client.app.state.sessionmaker() as db:
        db.get(CliAccount, agy["id"]).session_state = SessionState.DOWN
        db.commit()
    set_quota(client, claude["id"], 95)
    sync(client)
    items = switch_items(client)
    assert len(items) == 1 and items[0]["options"] == []
    assert "sesión" in items[0]["detail"]
    with client.app.state.sessionmaker() as db:
        assert switching.decisions_pending(db) == set()
    res = client.post(f"/api/inbox/{items[0]['id']}/switch", json={"choice": "switch"})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "switch_unavailable"


def test_secondary_above_the_threshold_is_not_offered(client):
    _, claude, agy = agent_with_secondary(client)
    set_quota(client, agy["id"], 97)
    set_quota(client, claude["id"], 95)
    sync(client)
    assert switch_items(client)[0]["options"] == []


def test_expired_switch_is_cleared_by_the_housekeeping(client):
    agent, _, _ = agent_with_secondary(client)
    with client.app.state.sessionmaker() as db:
        db.get(Agent, agent["id"]).using_fallback_until = utcnow() - timedelta(minutes=1)
        db.commit()
    sync(client)
    with client.app.state.sessionmaker() as db:
        assert db.get(Agent, agent["id"]).using_fallback_until is None


def test_blocked_decision_in_the_task_api(client):
    agent, claude, _ = agent_with_secondary(client)
    set_quota(client, claude["id"], 95)
    sync(client)
    project = client.post(
        "/api/projects", json={"name": "P", "path": str(client.app.state.settings.data_dir)}
    )
    assert project.status_code == 201, project.text
    task = client.post(
        "/api/tasks",
        json={
            "project_id": project.json()["id"],
            "agent_id": agent["id"],
            "title": "t",
        },
    )
    assert task.status_code == 201, task.text
    tasks = client.get("/api/tasks").json()
    tasks = tasks["items"] if isinstance(tasks, dict) else tasks
    assert [t["blocked"] for t in tasks if t["id"] == task.json()["id"]] == ["decision"]


def test_item_kinds_are_registered():
    assert InboxKind.SWITCH == "switch" and InboxStatus.PENDING == "pending"
    assert InboxItem.__tablename__ == "inbox_items"
