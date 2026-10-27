"""The Architect's API (phase 19, block 5; CA5, CA6, CA12): conversations and their sheet, the
proposals they make (review, approve whole or in part, reject), drafts in the agents' API, the
live events and Ajustes › Arquitecto. The CLI itself is covered by test_architect_session.py."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_architect_session import FixedClis


@pytest.fixture
def api(client: TestClient) -> TestClient:
    client.app.state.architect.clis = FixedClis()
    return client


def _conversation(api: TestClient, **body) -> dict:
    response = api.post("/api/architect/conversations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _fill(api: TestClient, conversation_id: str, **patch) -> dict:
    values = {
        "name": "Redactor",
        "role": "Redactor del blog",
        "cli": "claude",
        "instructions": "Escribe.",
        **patch,
    }
    response = api.patch(
        f"/api/architect/conversations/{conversation_id}/sheet", json={"patch": values}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_settings_have_defaults_and_can_be_changed(api: TestClient):
    settings = api.get("/api/settings/architect").json()
    assert settings["cli"] == "" and settings["idle_minutes"] == 15 and settings["max_live"] == 2
    assert (
        settings["instructions"] == "" and "Agente Arquitecto" in settings["default_instructions"]
    )
    changed = api.put("/api/settings/architect", json={"cli": "agy", "idle_minutes": 30}).json()
    assert (changed["cli"], changed["idle_minutes"]) == ("agy", 30)
    assert api.put("/api/settings/architect", json={"max_live": 9}).status_code == 422


def test_a_conversation_starts_empty_and_asleep_and_is_listed(api: TestClient):
    created = _conversation(api)
    assert (created["mode"], created["status"], created["state"]) == ("agent", "open", "asleep")
    assert created["messages"] == [] and created["sheet"]["ready"] is False
    listed = api.get("/api/architect/conversations").json()
    assert [c["id"] for c in listed] == [created["id"]]
    assert api.delete(f"/api/architect/conversations/{created['id']}").status_code == 204
    assert api.get(f"/api/architect/conversations/{created['id']}").status_code == 404


def test_improving_an_agent_starts_from_it(api: TestClient):
    agent = api.post(
        "/api/agents", json={"name": "QA", "role": "QA", "instructions": "Prueba."}
    ).json()
    created = _conversation(api, mode="improve_agent", agent_id=agent["id"])
    main = created["sheet"]["sheet"]["agents"]["main"]
    assert (main["name"], main["id"]) == ("QA", agent["id"])
    assert created["sheet"]["sheet"]["base"]["agents"]["main"]["role"] == "QA"
    assert (
        api.post("/api/architect/conversations", json={"mode": "improve_agent"}).status_code == 422
    )


def test_an_edit_by_hand_is_locked_and_can_be_released(api: TestClient):
    created = _conversation(api)
    sheet = _fill(api, created["id"], color="#FF0000", model="gpt-5")
    assert "main.color" in sheet["locked"] and "main.model" not in sheet["locked"]
    assert "Disponibles" in sheet["refused"]["main.model"]
    released = api.post(
        f"/api/architect/conversations/{created['id']}/unlock", json={"fields": ["main.color"]}
    ).json()
    assert "main.color" not in released["locked"]


def test_a_new_agent_is_proposed_reviewed_and_approved(api: TestClient):
    """CA5: «Crear borrador» → a draft that receives no tasks → approved, it is active."""
    created = _conversation(api)
    assert api.post(f"/api/architect/conversations/{created['id']}/propose").status_code == 422
    _fill(api, created["id"])
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    assert (proposal["kind"], proposal["status"]) == ("new_agent", "pending")
    draft = api.get(f"/api/agents/{proposal['target_agent_id']}").json()
    assert (draft["status"], draft["proposal_id"]) == ("draft", proposal["id"])
    conversation = api.get(f"/api/architect/conversations/{created['id']}").json()
    assert (conversation["status"], conversation["proposal_id"]) == ("proposed", proposal["id"])
    # The draft cannot be switched on by hand: its proposal is approved instead.
    switched = api.patch(f"/api/agents/{draft['id']}", json={"status": "active"})
    assert switched.status_code == 409 and switched.json()["detail"]["code"] == "pending_proposal"
    items = [i for i in api.get("/api/inbox").json() if i.get("kind") == "proposal"]
    assert len(items) == 1
    applied = api.post(f"/api/proposals/{proposal['id']}/approve", json={}).json()
    assert applied["proposal"]["status"] == "applied" and applied["notes"] == []
    assert api.get(f"/api/agents/{draft['id']}").json()["status"] == "active"
    again = api.post(f"/api/proposals/{proposal['id']}/approve", json={})
    assert again.status_code == 409


def test_a_rejected_draft_can_be_archived_out_of_the_lists(api: TestClient):
    created = _conversation(api)
    _fill(api, created["id"])
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    rejected = api.post(f"/api/proposals/{proposal['id']}/reject", json={"archive": True}).json()
    assert rejected["status"] == "rejected"
    assert proposal["target_agent_id"] not in [a["id"] for a in api.get("/api/agents").json()]
    conversation = api.get(f"/api/architect/conversations/{created['id']}").json()
    assert conversation["status"] == "discarded"


def test_deleting_a_draft_rejects_its_proposal(api: TestClient):
    created = _conversation(api)
    _fill(api, created["id"])
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    assert api.delete(f"/api/agents/{proposal['target_agent_id']}").status_code == 204
    assert api.get(f"/api/proposals/{proposal['id']}").json()["status"] == "rejected"
    assert not [i for i in api.get("/api/inbox").json() if i.get("kind") == "proposal"]


def test_changes_to_an_agent_are_reviewed_field_by_field(api: TestClient):
    """CA12: the agent keeps working as it is; only the chosen fields change."""
    agent = api.post(
        "/api/agents", json={"name": "QA", "role": "QA", "instructions": "Prueba."}
    ).json()
    created = _conversation(api, mode="improve_agent", agent_id=agent["id"])
    api.patch(
        f"/api/architect/conversations/{created['id']}/sheet",
        json={"patch": {"role": "QA estricto", "instructions": "Prueba.\nRechaza sin tests."}},
    )
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    assert proposal["kind"] == "agent_changes"
    fields = {c["field"]: c for c in proposal["changes"]}
    assert set(fields) == {"role", "instructions"}
    assert "+Rechaza sin tests." in fields["instructions"]["diff"]
    assert api.get(f"/api/agents/{agent['id']}").json()["role"] == "QA"  # nothing applied yet
    applied = api.post(f"/api/proposals/{proposal['id']}/approve", json={"fields": ["role"]}).json()
    assert applied["proposal"]["status"] == "partial"
    after = api.get(f"/api/agents/{agent['id']}").json()
    assert (after["role"], after["instructions"]) == ("QA estricto", "Prueba.")


def test_a_conflict_needs_a_choice(api: TestClient):
    agent = api.post(
        "/api/agents", json={"name": "QA", "role": "QA", "instructions": "Prueba."}
    ).json()
    created = _conversation(api, mode="improve_agent", agent_id=agent["id"])
    api.patch(
        f"/api/architect/conversations/{created['id']}/sheet",
        json={"patch": {"role": "QA estricto"}},
    )
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    api.patch(f"/api/agents/{agent['id']}", json={"role": "QA manual"})
    conflicted = api.post(f"/api/proposals/{proposal['id']}/approve", json={})
    assert conflicted.status_code == 409 and conflicted.json()["detail"]["code"] == "conflicts"
    review = api.get(f"/api/proposals/{proposal['id']}").json()
    assert review["changes"][0]["conflict"] and review["changes"][0]["current"] == "QA manual"
    ok = api.post(
        f"/api/proposals/{proposal['id']}/approve", json={"choices": {"role": "proposed"}}
    )
    assert ok.status_code == 200
    assert api.get(f"/api/agents/{agent['id']}").json()["role"] == "QA estricto"


def test_the_events_of_a_conversation_reach_only_its_viewers(api: TestClient):
    one, other = _conversation(api), _conversation(api)
    with api.websocket_connect(f"/api/architect/conversations/{one['id']}/events") as socket:
        _fill(api, other["id"])  # not this one's
        _fill(api, one["id"], name="Uno")
        event = socket.receive_json()
    assert (event["type"], event["conversation_id"]) == ("sheet", one["id"])
    assert event["sheet"]["agents"]["main"]["name"] == "Uno"


def test_an_agent_lists_its_pending_changes_and_its_configuration_history(api: TestClient):
    """CA12: what was applied stays in the History tab, next to the edits by hand."""
    agent = api.post(
        "/api/agents", json={"name": "QA", "role": "QA", "instructions": "Prueba."}
    ).json()
    created = _conversation(api, mode="improve_agent", agent_id=agent["id"])
    api.patch(
        f"/api/architect/conversations/{created['id']}/sheet",
        json={"patch": {"role": "QA estricto"}},
    )
    proposal = api.post(f"/api/architect/conversations/{created['id']}/propose").json()
    pending = api.get(f"/api/proposals?target_agent_id={agent['id']}&status=pending").json()
    assert [p["id"] for p in pending] == [proposal["id"]]
    api.post(f"/api/proposals/{proposal['id']}/approve", json={})
    assert api.get(f"/api/proposals?target_agent_id={agent['id']}&status=pending").json() == []
    api.patch(f"/api/agents/{agent['id']}", json={"description": "A mano"})
    history = api.get(f"/api/agents/{agent['id']}/config-history").json()
    assert [h["source"] for h in history] == ["user", "architect"]
    assert history[1]["fields"]["role"] == {"before": "QA", "after": "QA estricto"}
    assert history[1]["conversation_id"] == created["id"]
