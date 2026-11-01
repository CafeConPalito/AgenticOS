"""The pipeline API: template, validation, editing without breaking the tasks in flight."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")  # nothing is launched in these tests
        yield client


def project(api: TestClient, tmp_path: Path, name: str = "Web") -> str:
    folder = tmp_path / name
    folder.mkdir()
    return api.post("/api/projects", json={"name": name, "path": str(folder)}).json()["id"]


def test_template_assigns_agents_made_from_the_agent_templates(api: TestClient, tmp_path: Path):
    analyst = api.post("/api/agents", json={"template": "analyst"}).json()
    qa = api.post("/api/agents", json={"template": "qa"}).json()
    project_id = project(api, tmp_path)
    assert api.get(f"/api/projects/{project_id}/pipeline").json() is None

    url = f"/api/projects/{project_id}/pipeline/template"
    created = api.post(url, json={"template": "development"})
    assert created.status_code == 201
    pipeline = created.json()
    assert pipeline["name"] == "Desarrollo"
    stages = {s["name"]: s for s in pipeline["stages"]}
    assert stages["Toma de requisitos"]["agent_id"] == analyst["id"]
    assert stages["QA"]["agent_id"] == qa["id"]
    assert stages["Arquitectura"]["agent_id"] is None  # no agent made from that template
    assert stages["Toma de requisitos"]["agent_name"] == analyst["name"]
    again = api.post(url, json={"template": "development"})
    assert again.json()["detail"]["code"] == "pipeline_exists"
    # Phase 24: the old templates are gone.
    for old in ("web", "web_split"):
        assert api.post(url, json={"template": old}).status_code == 422


def test_validation(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"

    def code(body: dict) -> str:
        response = api.put(url, json=body)
        assert response.status_code == 422, response.json()
        return response.json()["detail"]["code"]

    assert code({"stages": [{"name": "A", "reject_to": 0}]}) == "invalid_reject_to"
    assert code({"stages": [{"name": "A"}, {"name": "B", "reject_to": 2}]}) == "invalid_reject_to"
    assert code({"stages": [{"name": "A", "agent_id": "nope"}]}) == "unknown_agent"
    assert code({"stages": [{"name": "A", "id": "nope"}]}) == "unknown_stage"
    assert api.put(url, json={"stages": []}).status_code == 422
    assert api.put(url, json={"stages": [{"name": " "}]}).status_code == 422


def test_editing_keeps_stage_ids_and_protects_stages_with_tasks(api: TestClient, tmp_path: Path):
    dev = api.post("/api/agents", json={"name": "Dev"}).json()["id"]
    qa = api.post("/api/agents", json={"name": "QA"}).json()["id"]
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"
    saved = api.put(
        url,
        json={
            "name": "Simple",
            "max_rejections": 2,
            "stages": [
                {"name": "Desarrollo", "agent_id": dev},
                {"name": "QA", "agent_id": qa, "reject_to": 0, "requires_review": True},
            ],
        },
    ).json()
    desarrollo, qa_stage = saved["stages"]
    assert (saved["max_rejections"], qa_stage["requires_review"]) == (2, True)

    # A task enters at the first stage, with its agent: no agent needed in the request.
    task = api.post("/api/tasks", json={"project_id": project_id, "title": "Login"}).json()
    assert (task["stage_name"], task["agent_id"], task["stage_index"], task["stage_count"]) == (
        "Desarrollo",
        dev,
        1,
        2,
    )
    assert api.get(url).json()["stages"][0]["active_tasks"] == 1

    # Reorder and rename: ids are kept, the task still points at its stage.
    reordered = api.put(
        url,
        json={
            "stages": [
                {"id": qa_stage["id"], "name": "Revisión", "agent_id": qa},
                {"id": desarrollo["id"], "name": "Dev", "agent_id": dev},
            ]
        },
    ).json()
    assert [s["id"] for s in reordered["stages"]] == [qa_stage["id"], desarrollo["id"]]
    assert api.get(f"/api/tasks/{task['id']}").json()["stage_name"] == "Dev"

    # A stage with unfinished tasks cannot go, nor can the pipeline.
    removed = api.put(url, json={"stages": [{"id": qa_stage["id"], "name": "Revisión"}]})
    assert (removed.status_code, removed.json()["detail"]["code"]) == (409, "stage_in_use")
    assert api.delete(url).json()["detail"]["code"] == "stage_in_use"

    api.post(f"/api/tasks/{task['id']}/cancel")
    assert api.delete(url).status_code == 204
    assert api.get(url).json() is None
