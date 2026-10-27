"""Regressions found by the review of phase 19 (block 12): a team's drafts, the settings of a
pipeline the Architect does not see, archived drafts, imported files, a conversation proposing
again, and the members a team improvement removes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_architect_session import FixedClis
from test_proposals_team import _agent, _project, _team_proposal, _tools, _writer


@pytest.fixture
def api(client: TestClient) -> TestClient:
    client.app.state.architect.clis = FixedClis()
    return client


def test_a_draft_of_a_team_proposal_is_not_deleted_alone(api: TestClient, tmp_path: Path):
    proposal, _, _ = _team_proposal(api, tmp_path)
    drafts = [a for a in api.get("/api/agents").json() if a["status"] == "draft"]
    refused = api.delete(f"/api/agents/{drafts[0]['id']}")
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "draft_in_team_proposal"
    assert len([a for a in api.get("/api/agents").json() if a["status"] == "draft"]) == 2
    assert api.get(f"/api/proposals/{proposal['id']}").json()["status"] == "pending"


def test_improving_a_pipeline_keeps_the_settings_the_architect_cannot_see(
    api: TestClient, tmp_path: Path
):
    project = _project(api, tmp_path, "Tienda")
    dev = _agent(api, "Dev", "Desarrollador")
    api.put(
        f"/api/projects/{project['id']}/pipeline",
        json={
            "name": "Mi flujo",
            "max_rejections": 5,
            "stages": [{"name": "Desarrollo", "agent_id": dev["id"]}],
        },
    )
    conversation = api.post(
        "/api/architect/conversations",
        json={"mode": "improve_pipeline", "project_id": project["id"]},
    ).json()
    tool = _tools(api, conversation["id"])
    tool(
        "set_pipeline",
        project="Tienda",
        stages=[
            {"name": "Desarrollo", "agent": "Dev"},
            {"name": "Pruebas", "agent": "Dev"},
        ],
    )
    proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose").json()
    assert api.post(f"/api/proposals/{proposal['id']}/approve", json={}).status_code == 200
    pipeline = api.get(f"/api/projects/{project['id']}/pipeline").json()
    assert (pipeline["name"], pipeline["max_rejections"]) == ("Mi flujo", 5)
    assert [s["name"] for s in pipeline["stages"]] == ["Desarrollo", "Pruebas"]


def test_an_archived_draft_is_out_of_every_list(api: TestClient, tmp_path: Path):
    proposal, _, _ = _team_proposal(api, tmp_path)
    api.post(f"/api/proposals/{proposal['id']}/reject", json={"archive": True})
    assert "Redactor" not in [a["name"] for a in api.get("/api/agents").json()]
    home = api.get("/api/home").json()
    assert "Redactor" not in str(home)


def test_an_imported_file_does_not_read_local_paths(api: TestClient, tmp_path: Path):
    secret = tmp_path / "secreto.txt"
    secret.write_text("clave privada", encoding="utf-8")
    payload = {
        "format": "agentic-os.agent",
        "version": 1,
        "agent": {"name": "Intruso", "role": "x", "instructions": "x", "cli": "claude"},
        "knowledge": [{"title": "Secreto", "kind": "file", "source": str(secret)}],
    }
    preview = api.post("/api/agents/import/preview", json={"payload": payload}).json()
    assert preview["missing_knowledge"] == ["Secreto"]
    imported = api.post("/api/agents/import", json={"payload": payload})
    assert imported.status_code == 201, imported.text
    assert any("no se importa" in note for note in imported.json()["notes"])
    docs = api.get(f"/api/knowledge/docs?agent_id={imported.json()['agent']['id']}")
    assert (
        docs.status_code != 200
        or docs.json() in ([], {"docs": []})
        or "Secreto" not in str(docs.json())
    )


@pytest.mark.parametrize(
    "agent_extra",
    [{"allowed_tools": 5}, {"allowed_tools": [["read"]]}, {"max_concurrency": "x"}],
)
def test_a_malformed_agent_file_is_not_a_server_error(api: TestClient, agent_extra: dict):
    payload = {
        "format": "agentic-os.agent",
        "version": 1,
        "agent": {"name": "Roto", "role": "x", "instructions": "x", "cli": "claude", **agent_extra},
        "skills": {"own": [{"name": "s", "files": 3}], "modes": "no"},
        "knowledge": "no",
    }
    assert api.post("/api/agents/import/preview", json={"payload": payload}).status_code < 500
    assert api.post("/api/agents/import", json={"payload": payload}).status_code < 500


def test_a_proposed_conversation_can_propose_again_and_replaces_the_first(api: TestClient):
    conversation = api.post("/api/architect/conversations", json={"mode": "agent"}).json()
    sheet = {"name": "Redactor", "role": "Redactor", "cli": "claude", "instructions": "Escribe."}
    url = f"/api/architect/conversations/{conversation['id']}"
    assert api.patch(f"{url}/sheet", json={"patch": sheet}).status_code == 200
    first = api.post(f"{url}/propose").json()
    api.patch(f"{url}/sheet", json={"patch": {"instructions": "Escribe mejor."}})
    second = api.post(f"{url}/propose")
    assert second.status_code == 201, second.text
    assert api.get(f"/api/proposals/{first['id']}").json()["status"] == "rejected"
    assert api.get(f"/api/proposals/{second.json()['id']}").json()["status"] == "pending"
    drafts = [a for a in api.get("/api/agents").json() if a["status"] == "draft"]
    assert len(drafts) == 1


def test_improving_a_team_takes_out_the_members_it_removes(api: TestClient):
    dev, qa = _agent(api, "Dev", "Desarrollador"), _agent(api, "QA", "QA")
    team = api.post(
        "/api/teams", json={"name": "Web", "description": "", "agent_ids": [dev["id"], qa["id"]]}
    ).json()
    conversation = api.post(
        "/api/architect/conversations", json={"mode": "improve_team", "team_id": team["id"]}
    ).json()
    tool = _tools(api, conversation["id"])
    tool("remove_agent", agent_ref=dev["id"])
    proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose").json()
    assert api.post(f"/api/proposals/{proposal['id']}/approve", json={}).status_code == 200
    agents = {a["name"]: a for a in api.get("/api/agents").json()}
    assert agents["Dev"]["team_id"] is None and agents["QA"]["team_id"] == team["id"]
    assert _writer  # the helper stays imported for the other tests of this file's family


def test_a_stale_reference_the_improvement_does_not_touch_does_not_block_it(api: TestClient):
    agent = api.post(
        "/api/agents",
        json={
            "name": "Viejo",
            "role": "Viejo",
            "instructions": "x",
            "model": "modelo-que-no-existe",
        },
    ).json()
    conversation = api.post(
        "/api/architect/conversations", json={"mode": "improve_agent", "agent_id": agent["id"]}
    ).json()
    url = f"/api/architect/conversations/{conversation['id']}"
    api.patch(f"{url}/sheet", json={"patch": {"instructions": "Mejor."}})
    proposed = api.post(f"{url}/propose")
    assert proposed.status_code == 201, proposed.text
