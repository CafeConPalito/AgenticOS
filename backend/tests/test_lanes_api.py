"""The API of forked tasks (phase 13): lanes in the lists, decisions, adding and cancelling
branches. The scheduler is paused; the forks are reached by finishing the stage in the database."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.models import Run, RunKind, RunStatus, Task, TaskStatus
from agentic_os.services import decider
from agentic_os.services import tasks as task_ops
from agentic_os.services.decider import DecisionService


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        yield client


def setup(api: TestClient, tmp_path: Path) -> dict:
    """A project in worktree mode with Requisitos → (Backend | Frontend) → QA."""
    folder = tmp_path / "web"
    folder.mkdir()
    agents = [api.post("/api/agents", json={"name": n}).json()["id"] for n in "ABCD"]
    project = api.post(
        "/api/projects", json={"name": "Web", "path": str(folder), "workspace_mode": "direct"}
    ).json()["id"]
    pipeline = api.put(
        f"/api/projects/{project}/pipeline",
        json={
            "stages": [
                {"name": "Requisitos", "agent_id": agents[0]},
                {"name": "Backend", "agent_id": agents[1]},
                {"name": "Frontend", "agent_id": agents[2]},
                {"name": "QA", "agent_id": agents[3], "reject_to": 1, "reject_also": [2]},
            ],
            "links": [
                {"source": 0, "target": 1, "name": "Backend", "condition": "toca la API"},
                {"source": 0, "target": 2, "name": "Frontend", "condition": "toca la UI"},
                {"source": 1, "target": 3},
                {"source": 2, "target": 3},
            ],
        },
    ).json()
    start = pipeline["stages"][0]["id"]
    links = {x["name"]: x["id"] for x in pipeline["links"] if x["from_stage_id"] == start}
    return {"project": project, "agents": agents, "links": links, "start": start}


def finish_first_stage(api: TestClient, task_id: str) -> None:
    sessions = api.app.state.sessionmaker
    with sessions() as db:
        task = db.get(Task, task_id)
        task.status = TaskStatus.RUNNING
        task_ops.stage_completed(db, task, "requisitos claros", None)
        db.commit()


def create(api: TestClient, ctx: dict, **extra) -> dict:
    body = {"project_id": ctx["project"], "title": "Filtro de pedidos", **extra}
    response = api.post("/api/tasks", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def test_lanes_show_inside_their_task_and_on_their_own_only_when_asked(
    api: TestClient, tmp_path: Path
):
    ctx = setup(api, tmp_path)
    task = create(api, ctx, preset_lanes={ctx["start"]: [ctx["links"]["Backend"]]})
    finish_first_stage(api, task["id"])

    listed = api.get("/api/tasks").json()
    assert [t["code"] for t in listed] == ["T-1"]
    mother = listed[0]
    assert mother["phase"] == "forked" and mother["status"] == "queued"  # its lane's state
    assert [(x["code"], x["name"], x["stage_name"]) for x in mother["lanes"]] == [
        ("T-1·backend", "Backend", "Backend")
    ]
    both = api.get("/api/tasks", params={"lanes": "include"}).json()
    assert {t["code"] for t in both} == {"T-1", "T-1·backend"}
    lane = next(t for t in both if t["lane_of_id"])
    assert (lane["lane_name"], lane["fork_stage_id"], lane["title"]) == (
        "Backend",
        ctx["start"],
        "Filtro de pedidos",
    )
    # an agent's tasks are its lanes' work too
    queue = api.get(f"/api/agents/{ctx['agents'][1]}/queue").json()
    assert [t["code"] for t in queue["queued"]] == ["T-1·backend"]
    assert [
        t["code"] for t in api.get("/api/tasks", params={"agent_id": ctx["agents"][1]}).json()
    ] == ["T-1·backend"]
    decisions = api.get(f"/api/tasks/{task['id']}/decisions").json()
    assert [(d["decided_by"], d["chosen"]) for d in decisions] == [
        ("preset", [ctx["links"]["Backend"]])
    ]


def test_editing_a_task_updates_its_lanes(api: TestClient, tmp_path: Path):
    ctx = setup(api, tmp_path)
    task = create(api, ctx, preset_lanes={ctx["start"]: list(ctx["links"].values())})
    finish_first_stage(api, task["id"])
    api.patch(f"/api/tasks/{task['id']}", json={"title": "Nuevo título", "priority": "high"})
    lanes = [
        t for t in api.get("/api/tasks", params={"lanes": "include"}).json() if t["lane_of_id"]
    ]
    assert {(t["title"], t["priority"]) for t in lanes} == {("Nuevo título", "high")}


def test_the_person_chooses_the_branches_of_a_task_that_waits_and_can_add_one(
    api: TestClient, tmp_path: Path
):
    ctx = setup(api, tmp_path)
    task = create(api, ctx)
    finish_first_stage(api, task["id"])
    with api.app.state.sessionmaker() as db:  # the scheduler is paused: nobody decided
        DecisionService.give_up(db, db.get(Task, task["id"]), "no hay decisor")
        db.commit()
    waiting = api.get(f"/api/tasks/{task['id']}").json()
    assert (waiting["status"], waiting["waiting_reason"]) == ("waiting_human", "choose_branch")
    assert api.post(f"/api/tasks/{task['id']}/complete", json={"summary": "x"}).status_code == 409
    assert (
        api.post(f"/api/tasks/{task['id']}/decision", json={"chosen": ["nope"]}).status_code == 422
    )

    chosen = api.post(
        f"/api/tasks/{task['id']}/decision", json={"chosen": [ctx["links"]["Frontend"]]}
    )
    assert chosen.status_code == 200, chosen.json()
    assert chosen.json()["phase"] == "forked"
    assert [x["name"] for x in chosen.json()["lanes"]] == ["Frontend"]
    assert (
        api.post(
            f"/api/tasks/{task['id']}/decision", json={"chosen": [ctx["links"]["Frontend"]]}
        ).status_code
        == 409
    )

    added = api.post(f"/api/tasks/{task['id']}/lanes", json={"link_id": ctx["links"]["Backend"]})
    assert added.status_code == 201 and added.json()["code"] == "T-1·backend"
    again = api.post(f"/api/tasks/{task['id']}/lanes", json={"link_id": ctx["links"]["Backend"]})
    assert again.status_code == 409
    assert {x["name"] for x in api.get(f"/api/tasks/{task['id']}").json()["lanes"]} == {
        "Frontend",
        "Backend",
    }


def test_cancelling_a_lane_leaves_the_others_and_cancelling_the_task_cancels_all(
    api: TestClient, tmp_path: Path
):
    ctx = setup(api, tmp_path)
    task = create(api, ctx, preset_lanes={ctx["start"]: list(ctx["links"].values())})
    finish_first_stage(api, task["id"])
    lanes = {x["name"]: x["id"] for x in api.get(f"/api/tasks/{task['id']}").json()["lanes"]}

    assert api.post(f"/api/tasks/{lanes['Backend']}/cancel").json()["status"] == "cancelled"
    after = api.get(f"/api/tasks/{task['id']}").json()
    assert after["phase"] == "forked" and after["status"] != "cancelled"

    cancelled = api.post(f"/api/tasks/{task['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert {x["status"] for x in cancelled["lanes"]} == {"cancelled"}


def test_decision_runs_are_not_listed_as_sessions(api: TestClient, tmp_path: Path):
    ctx = setup(api, tmp_path)
    task = create(api, ctx)
    with api.app.state.sessionmaker() as db:
        db_task = db.get(Task, task["id"])
        from agentic_os.models import Project

        request = decider.DecisionRequest(
            "t", "f", "t", "", (), (), (), decider.Cli.CLAUDE, "a", "haiku", ("x",), {}
        )
        result = decider.DecisionResult(model="haiku")
        decider.record_run(db, db.get(Project, ctx["project"]), db_task, None, request, result)
        db.commit()
        assert (
            db.scalar(select(Run).where(Run.kind == RunKind.DECISION)).status == RunStatus.COMPLETED
        )
    assert api.get("/api/runs").json() == []
    assert api.get(f"/api/tasks/{task['id']}").json()["last_run_id"] is None
    assert api.get(f"/api/tasks/{task['id']}/tree").json() == []


def test_try_the_conditions_asks_the_decider_without_creating_a_task(
    settings: Settings, tmp_path: Path, monkeypatch
):
    taken = decider.DecisionResult(
        taken={"0": True, "1": False},
        reasons={"0": "toca la API", "1": "no hay UI"},
        usage=decider.Usage(output_tokens=120, cost_usd=0.0003),
        model="claude-haiku-5-5",
        seconds=1.234,
    )
    monkeypatch.setattr(decider, "call", lambda request, runner=None: taken)
    configured = settings.model_copy(update={"cli_command_overrides": {"claude": ["fake"]}})
    with TestClient(create_app(configured)) as api:
        api.post("/api/scheduler/pause")
        ctx = setup(api, tmp_path)
        response = api.post(
            f"/api/projects/{ctx['project']}/pipeline/decide-preview",
            json={
                "title": "Nuevo endpoint",
                "branches": [
                    {"name": "Backend", "condition": "toca la API"},
                    {"name": "Frontend", "condition": "toca la UI"},
                ],
            },
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert [(b["name"], b["take"], b["reason"]) for b in body["branches"]] == [
            ("Backend", True, "toca la API"),
            ("Frontend", False, "no hay UI"),
        ]
        assert (body["cli"], body["model"], body["cost_usd"], body["seconds"]) == (
            "claude",
            "claude-haiku-5-5",
            0.0003,
            1.2,
        )
        assert api.get("/api/tasks").json() == []
        with api.app.state.sessionmaker() as db:  # it was recorded like any other call
            assert db.scalar(select(Run).where(Run.kind == RunKind.DECISION)).task_id is None
        too_few = api.post(
            f"/api/projects/{ctx['project']}/pipeline/decide-preview",
            json={"title": "x", "branches": [{"name": "A", "condition": "b"}]},
        )
        assert too_few.status_code == 422


def test_the_join_endpoints_only_work_while_the_branches_clash(api: TestClient, tmp_path: Path):
    ctx = setup(api, tmp_path)
    task = create(api, ctx)
    assert api.get(f"/api/tasks/{task['id']}/join").json() == []
    for path in ("join/editor",):
        assert api.post(f"/api/tasks/{task['id']}/{path}").status_code == 409
    agent = ctx["agents"][0]
    refused = api.post(f"/api/tasks/{task['id']}/join/agent", json={"agent_id": agent})
    assert refused.status_code == 409
    finish = api.post(f"/api/tasks/{task['id']}/join/editor/finish", json={"repo_id": "x"})
    assert finish.status_code == 409
