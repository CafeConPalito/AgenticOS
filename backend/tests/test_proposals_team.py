"""Teams and pipelines designed by the Architect (phase 19, block 10; CA15, CA16, CA17): a team
with new and reused agents and a project's pipeline, approved in one go or leaving an agent
out; changes to an existing pipeline, reviewed against the project's as it is now."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_architect_session import FixedClis

from agentic_os.errors import ApiError
from agentic_os.services import proposals as proposal_ops
from agentic_os.services.architect.service import Live


@pytest.fixture
def api(client: TestClient) -> TestClient:
    client.app.state.architect.clis = FixedClis()
    return client


def _project(api: TestClient, tmp_path: Path, name: str = "Blog") -> dict:
    folder = tmp_path / name.lower()
    folder.mkdir()
    return api.post("/api/projects", json={"name": name, "path": str(folder)}).json()


def _agent(api: TestClient, name: str, role: str) -> dict:
    return api.post("/api/agents", json={"name": name, "role": role, "instructions": "x"}).json()


def _tools(api: TestClient, conversation_id: str):
    """The Architect's tools for a conversation, as its CLI would call them."""
    service = api.app.state.architect
    run = f"run-{conversation_id}"
    service._live[conversation_id] = Live(conversation_id, run, "claude", 1)
    service._by_run[run] = conversation_id

    def call(tool_name: str, /, **args) -> dict:
        return json.loads(service.call_tool(run, tool_name, args))

    return call


def _writer(ref: str, role: str) -> dict:
    return {
        "name": ref.capitalize(),
        "role": role,
        "cli": "claude",
        "instructions": f"Eres el {role}.",
    }


def _team_proposal(api: TestClient, tmp_path: Path) -> tuple[dict, dict, dict]:
    project = _project(api, tmp_path)
    qa = _agent(api, "QA", "QA")
    conversation = api.post("/api/architect/conversations", json={"mode": "team"}).json()
    tool = _tools(api, conversation["id"])
    tool("set_team", name="Contenidos", description="Posts del blog")
    tool("update_sheet", patch=_writer("redactor", "Redactor"), agent_ref="redactor")
    tool("update_sheet", patch=_writer("revisor", "Revisor"), agent_ref="revisor")
    tool("use_existing_agent", name="QA")
    answer = tool(
        "set_pipeline",
        project="Blog",
        stages=[
            {"name": "Redacción", "agent": "redactor"},
            {"name": "Revisión", "agent": "revisor", "reject_to": 0},
            {"name": "Publicación", "agent": "QA", "requires_review": True},
        ],
    )
    assert answer["issues"] == [], answer
    proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose")
    assert proposal.status_code == 201, proposal.text
    return proposal.json(), project, qa


def test_a_team_is_proposed_with_its_drafts_and_its_pipeline(api: TestClient, tmp_path: Path):
    """CA15: one conversation, a team, new and reused agents, a project's pipeline."""
    proposal, project, qa = _team_proposal(api, tmp_path)
    assert proposal["kind"] == "team"
    review = proposal["team"]
    assert review["team"]["name"] == "Contenidos"
    assert [a["name"] for a in review["new_agents"]] == ["Redactor", "Revisor"]
    assert [a["name"] for a in review["existing_agents"]] == ["QA"]
    assert review["pipeline"]["added"] == ["Redacción", "Revisión", "Publicación"]
    assert review["pipeline"]["conflict"] is False
    drafts = [a for a in api.get("/api/agents").json() if a["status"] == "draft"]
    assert sorted(a["name"] for a in drafts) == ["Redactor", "Revisor"]
    assert api.get(f"/api/projects/{project['id']}/pipeline").status_code in (200, 404)

    applied = api.post(f"/api/proposals/{proposal['id']}/approve", json={}).json()
    assert applied["proposal"]["status"] == "applied"
    team = next(t for t in api.get("/api/teams").json() if t["name"] == "Contenidos")
    agents = {a["name"]: a for a in api.get("/api/agents").json()}
    assert {agents[n]["team_id"] for n in ("Redactor", "Revisor", "QA")} == {team["id"]}
    assert agents["Redactor"]["status"] == "active"
    pipeline = api.get(f"/api/projects/{project['id']}/pipeline").json()
    assert [(s["name"], s["agent_id"]) for s in pipeline["stages"]] == [
        ("Redacción", agents["Redactor"]["id"]),
        ("Revisión", agents["Revisor"]["id"]),
        ("Publicación", qa["id"]),
    ]


def test_an_agent_used_by_a_stage_cannot_be_left_out(api: TestClient, tmp_path: Path):
    """CA16."""
    proposal, _, _ = _team_proposal(api, tmp_path)
    left_out = api.post(
        f"/api/proposals/{proposal['id']}/approve", json={"skip_agents": ["revisor"]}
    )
    assert left_out.status_code == 409
    assert left_out.json()["detail"]["stages"] == ["Revisión"]


def test_if_applying_fails_nothing_is_applied(api: TestClient, tmp_path: Path, monkeypatch):
    """CA16: one transaction."""
    proposal, _, _ = _team_proposal(api, tmp_path)

    def broken(*args, **kwargs):
        raise ApiError(409, "stage_in_use", "a removed stage still has tasks")

    monkeypatch.setattr(proposal_ops.pipeline_ops, "save", broken)
    failed = api.post(f"/api/proposals/{proposal['id']}/approve", json={})
    assert failed.status_code == 409
    assert not [t for t in api.get("/api/teams").json() if t["name"] == "Contenidos"]
    statuses = {a["name"]: a["status"] for a in api.get("/api/agents").json()}
    assert statuses["Redactor"] == "draft" and statuses["Revisor"] == "draft"
    assert api.get(f"/api/proposals/{proposal['id']}").json()["status"] == "pending"


def test_rejecting_a_team_discards_its_drafts(api: TestClient, tmp_path: Path):
    proposal, _, _ = _team_proposal(api, tmp_path)
    api.post(f"/api/proposals/{proposal['id']}/reject", json={})
    names = [a["name"] for a in api.get("/api/agents").json()]
    assert "Redactor" not in names and "QA" in names


def test_changes_to_a_pipeline_are_reviewed_against_the_project_now(
    api: TestClient, tmp_path: Path
):
    """CA17: stages added and kept by id; a pipeline changed meanwhile is a conflict."""
    project = _project(api, tmp_path, "Tienda")
    dev, qa = _agent(api, "Dev", "Desarrollador"), _agent(api, "QA", "QA")
    saved = api.put(
        f"/api/projects/{project['id']}/pipeline",
        json={
            "stages": [
                {"name": "Desarrollo", "agent_id": dev["id"]},
                {"name": "QA", "agent_id": qa["id"]},
            ]
        },
    ).json()
    ids = [s["id"] for s in saved["stages"]]
    conversation = api.post(
        "/api/architect/conversations",
        json={"mode": "improve_pipeline", "project_id": project["id"]},
    ).json()
    start = conversation["sheet"]["sheet"]["pipeline"]
    assert [s["id"] for s in start["stages"]] == ids
    assert conversation["sheet"]["pipeline_layout"]
    tool = _tools(api, conversation["id"])
    tool("update_sheet", patch=_writer("seguridad", "Revisor de seguridad"), agent_ref="seguridad")
    tool(
        "set_pipeline",
        project="Tienda",
        stages=[
            {"id": ids[0], "name": "Desarrollo", "agent": "Dev"},
            {"name": "Seguridad", "agent": "seguridad", "reject_to": 0},
            {"id": ids[1], "name": "QA", "agent": "QA"},
        ],
    )
    proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose").json()
    assert proposal["kind"] == "pipeline_changes"
    assert proposal["team"]["pipeline"]["added"] == ["Seguridad"]
    assert (
        proposal["team"]["pipeline"]["removed"] == []
        and not proposal["team"]["pipeline"]["conflict"]
    )

    # Meanwhile someone renames a stage in the editor.
    api.put(
        f"/api/projects/{project['id']}/pipeline",
        json={
            "stages": [
                {"id": ids[0], "name": "Desarrollo web", "agent_id": dev["id"]},
                {"id": ids[1], "name": "QA", "agent_id": qa["id"]},
            ]
        },
    )
    assert api.get(f"/api/proposals/{proposal['id']}").json()["team"]["pipeline"]["conflict"]
    refused = api.post(f"/api/proposals/{proposal['id']}/approve", json={})
    assert refused.status_code == 409 and refused.json()["detail"]["fields"] == ["pipeline"]
    applied = api.post(
        f"/api/proposals/{proposal['id']}/approve", json={"choices": {"pipeline": "proposed"}}
    )
    assert applied.status_code == 200, applied.text
    pipeline = api.get(f"/api/projects/{project['id']}/pipeline").json()
    assert [s["name"] for s in pipeline["stages"]] == ["Desarrollo", "Seguridad", "QA"]
    assert [pipeline["stages"][0]["id"], pipeline["stages"][2]["id"]] == ids  # kept by id
