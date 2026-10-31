"""The pipeline API with forks (phase 13): saving the graph, its problems and the templates."""

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


FORK = {
    "stages": [
        {"name": "Requisitos"},
        {"name": "Backend"},
        {"name": "Frontend"},
        {"name": "QA", "reject_to": 1, "reject_also": [2]},
    ],
    "links": [
        {"source": 0, "target": 1, "name": "Backend", "condition": "toca la API"},
        {"source": 0, "target": 2, "name": "Frontend", "always": True},
        {"source": 1, "target": 3},
        {"source": 2, "target": 3},
    ],
}


def test_a_pipeline_without_links_is_a_chain(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    saved = api.put(
        f"/api/projects/{project_id}/pipeline",
        json={"stages": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
    ).json()
    ids = [s["id"] for s in saved["stages"]]
    assert [(x["from_stage_id"], x["to_stage_id"]) for x in saved["links"]] == [
        (ids[0], ids[1]),
        (ids[1], ids[2]),
    ]
    xs = [s["x"] for s in saved["stages"]]
    assert xs == sorted(xs) and len(set(xs)) == 3  # laid out in columns


def test_a_fork_is_saved_with_its_branches_join_and_reject_targets(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    saved = api.put(f"/api/projects/{project_id}/pipeline", json=FORK)
    assert saved.status_code == 200, saved.json()
    pipeline = saved.json()
    start, backend, frontend, qa = pipeline["stages"]
    assert start["join_stage_id"] == qa["id"] and qa["join_stage_id"] is None
    assert qa["reject_to_stage_id"] == backend["id"]
    assert qa["reject_extra_stage_ids"] == [frontend["id"]]
    branches = [x for x in pipeline["links"] if x["from_stage_id"] == start["id"]]
    assert [(x["name"], x["always"], x["position"]) for x in branches] == [
        ("Backend", False, 0),
        ("Frontend", True, 1),
    ]
    assert branches[0]["condition"] == "toca la API"
    # Backend and Frontend sit in different rows of the same column
    assert backend["x"] == frontend["x"] and backend["y"] != frontend["y"]


def test_saving_again_keeps_the_ids_of_the_links_that_stay(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"
    first = api.put(url, json=FORK).json()
    stages = [{**s} for s in FORK["stages"]]
    for stage, saved in zip(stages, first["stages"], strict=True):
        stage["id"] = saved["id"]
    second = api.put(url, json={**FORK, "stages": stages}).json()
    assert {x["id"] for x in first["links"]} == {x["id"] for x in second["links"]}
    # dropping the Frontend branch removes only its links
    shrunk = api.put(
        url,
        json={
            "stages": [stages[0], stages[1], {"id": stages[3]["id"], "name": "QA"}],
            "links": [{"source": 0, "target": 1}, {"source": 1, "target": 2}],
        },
    ).json()
    assert len(shrunk["links"]) == 2
    assert all(x["id"] in {y["id"] for y in first["links"]} for x in shrunk["links"])


def test_a_badly_built_graph_is_refused_with_its_problems(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"

    crossing = {
        "stages": [{"name": n} for n in "ABCD"],
        "links": [
            {"source": 0, "target": 1, "condition": "x"},
            {"source": 0, "target": 2, "condition": "y"},
            {"source": 1, "target": 3, "condition": "z"},
            {"source": 1, "target": 2, "condition": "w"},
            {"source": 2, "target": 3},
        ],
    }
    found = {i["code"] for i in api.put(url, json=crossing).json()["detail"]["issues"]}
    assert "unstructured" in found
    cycle = {
        "stages": [{"name": n} for n in "ABC"],
        "links": [
            {"source": 0, "target": 1},
            {"source": 1, "target": 2},
            {"source": 2, "target": 1},
        ],
    }
    assert {i["code"] for i in api.put(url, json=cycle).json()["detail"]["issues"]} == {"cycle"}
    self_link = {"stages": [{"name": "A"}], "links": [{"source": 0, "target": 0}]}
    assert api.put(url, json=self_link).json()["detail"]["code"] == "invalid_link"
    outside = {"stages": [{"name": "A"}], "links": [{"source": 0, "target": 4}]}
    assert api.put(url, json=outside).json()["detail"]["code"] == "invalid_link"
    assert api.get(url).json() is None  # nothing was saved

    # Phase 21: a branch without a condition is fine, it is always taken.
    no_condition = {**FORK, "links": [{**FORK["links"][0], "condition": ""}, *FORK["links"][1:]]}
    assert api.put(url, json=no_condition).status_code == 200


def test_a_stage_inside_a_branch_cannot_reject_to_before_the_fork(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"
    stages = [{**s} for s in FORK["stages"]]
    stages[1]["reject_to"] = 0
    refused = api.put(url, json={**FORK, "stages": stages})
    assert refused.json()["detail"]["code"] == "invalid_reject_to"
    assert refused.json()["detail"]["issues"][0]["code"] == "reject_outside_path"
    stages[1].pop("reject_to")
    stages[3]["reject_to"] = 0  # after the join it can
    stages[3]["reject_also"] = []
    assert api.put(url, json={**FORK, "stages": stages}).status_code == 200


def test_validate_reports_problems_without_saving(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline/validate"
    assert api.post(url, json=FORK).json() == []
    two_starts = {
        "stages": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
        "links": [{"source": 0, "target": 2}, {"source": 1, "target": 2}],
    }
    assert api.post(url, json=two_starts).json() == [
        {"code": "many_starts", "stage": 1, "link": None}
    ]
    assert api.get(f"/api/projects/{project_id}/pipeline").json() is None


def test_the_decider_is_saved_with_the_pipeline(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    url = f"/api/projects/{project_id}/pipeline"
    body = {**FORK, "decider_cli": "agy", "decider_model": " gemini-3.8-flash-low "}
    saved = api.put(url, json=body).json()
    assert (saved["decider_cli"], saved["decider_model"]) == ("agy", "gemini-3.8-flash-low")
    unknown = api.put(url, json={**body, "decider_account_id": "nope"})
    assert unknown.json()["detail"]["code"] == "unknown_account"
    assert api.put(url, json={**body, "decider_cli": "gemini"}).status_code == 422


def test_the_split_template_forks_and_lets_qa_reject_to_either_branch(
    api: TestClient, tmp_path: Path
):
    analyst = api.post("/api/agents", json={"template": "analyst"}).json()["id"]
    dev = api.post("/api/agents", json={"template": "developer"}).json()["id"]
    qa_agent = api.post("/api/agents", json={"template": "qa"}).json()["id"]
    project_id = project(api, tmp_path)
    created = api.post(
        f"/api/projects/{project_id}/pipeline/template", json={"template": "web_split"}
    )
    assert created.status_code == 201, created.json()
    pipeline = created.json()
    start, backend, frontend, qa = pipeline["stages"]
    assert [s["agent_id"] for s in pipeline["stages"]] == [analyst, dev, dev, qa_agent]
    assert start["join_stage_id"] == qa["id"]
    assert (qa["reject_to_stage_id"], qa["reject_extra_stage_ids"]) == (
        backend["id"],
        [frontend["id"]],
    )
    branches = [x for x in pipeline["links"] if x["from_stage_id"] == start["id"]]
    assert [x["name"] for x in branches] == ["Backend", "Frontend"]
    assert all(x["condition"] for x in branches)
