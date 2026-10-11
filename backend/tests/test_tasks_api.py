"""The tasks, queues and scheduler API. The scheduler is paused: nothing is launched here (the
end-to-end tests run tasks with the fake CLI)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.models import Task, TaskStatus
from agentic_os.services import tasks as task_ops


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/scheduler/pause").json()["paused"] is True
        yield client


def seed(api: TestClient, tmp_path: Path, name: str = "Web") -> tuple[str, str]:
    folder = tmp_path / name
    folder.mkdir()
    agent = api.post("/api/agents", json={"name": f"Dev {name}"}).json()
    project = api.post("/api/projects", json={"name": name, "path": str(folder)}).json()
    return agent["id"], project["id"]


def create(api: TestClient, project_id: str, agent_id: str | None, title: str, **extra) -> dict:
    body = {"project_id": project_id, "agent_id": agent_id, "title": title, **extra}
    response = api.post("/api/tasks", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def test_create_list_and_read(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    first = create(api, project_id, agent_id, "Login con Google", description="OAuth")
    assert first["code"] == "T-1"
    assert (first["status"], first["agent_name"], first["project_name"]) == (
        "queued",
        "Dev Web",
        "Web",
    )
    assert (first["stage_id"], first["stage_index"], first["stage_count"]) == (None, 0, 0)
    second = create(api, project_id, agent_id, "Pagos", enqueue=False, priority="high")
    assert (second["code"], second["status"], second["priority"]) == ("T-2", "backlog", "high")

    assert [t["code"] for t in api.get("/api/tasks").json()] == ["T-2", "T-1"]
    assert [t["code"] for t in api.get("/api/tasks?status=backlog").json()] == ["T-2"]
    assert [t["code"] for t in api.get(f"/api/tasks?agent_id={agent_id}&status=queued").json()] == [
        "T-1"
    ]
    events = api.get(f"/api/tasks/{first['id']}/events").json()
    assert [e["kind"] for e in events] == ["created", "queued"]

    agent = api.get(f"/api/agents/{agent_id}").json()
    assert (agent["queued_count"], agent["running_count"]) == (1, 0)
    state = api.get("/api/scheduler").json()
    assert state == {"paused": True, "queued": 1, "running": 0, "waiting_human": 0, "review": 0}


def test_validation(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    no_agent = api.post("/api/tasks", json={"project_id": project_id, "title": "x"})
    assert (no_agent.status_code, no_agent.json()["detail"]["code"]) == (422, "agent_required")
    assert api.post("/api/tasks", json={"project_id": project_id, "title": " "}).status_code == 422
    missing = api.post(
        "/api/tasks", json={"project_id": "nope", "agent_id": agent_id, "title": "x"}
    )
    assert missing.status_code == 404
    task = create(api, project_id, agent_id, "x")
    assert api.patch(f"/api/tasks/{task['id']}", json={"title": None}).status_code == 422
    assert api.get("/api/tasks/nope").status_code == 404


def test_edit_priority_and_agent(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    other = api.post("/api/agents", json={"name": "QA"}).json()["id"]
    a = create(api, project_id, agent_id, "a")
    b = create(api, project_id, agent_id, "b")
    queue = api.get(f"/api/agents/{agent_id}/queue").json()
    assert [t["code"] for t in queue["queued"]] == ["T-1", "T-2"]

    edited = api.patch(f"/api/tasks/{b['id']}", json={"priority": "high", "title": "B"}).json()
    assert (edited["title"], edited["priority"]) == ("B", "high")
    queue = api.get(f"/api/agents/{agent_id}/queue").json()
    assert [t["code"] for t in queue["queued"]] == ["T-2", "T-1"]

    moved = api.patch(f"/api/tasks/{a['id']}", json={"agent_id": other}).json()
    assert moved["agent_name"] == "QA" and moved["status"] == "queued"
    assert [t["code"] for t in api.get(f"/api/agents/{other}/queue").json()["queued"]] == ["T-1"]


def test_reorder_queue(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    ids = [create(api, project_id, agent_id, t)["id"] for t in ("a", "b", "c")]
    reordered = api.put(f"/api/agents/{agent_id}/queue", json={"task_ids": ids[::-1]})
    assert [t["code"] for t in reordered.json()["queued"]] == ["T-3", "T-2", "T-1"]
    stale = api.put(f"/api/agents/{agent_id}/queue", json={"task_ids": ids[:2]})
    assert (stale.status_code, stale.json()["detail"]["code"]) == (409, "queue_changed")


def test_actions_check_the_status(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    queued = create(api, project_id, agent_id, "en cola")
    backlog = create(api, project_id, agent_id, "backlog", enqueue=False)

    for action, body in (("retry", None), ("enqueue", None), ("complete", {"summary": "x"})):
        response = api.post(f"/api/tasks/{queued['id']}/{action}", json=body)
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "task_status")
    review = api.post(f"/api/tasks/{queued['id']}/review", json={"action": "approve"})
    assert review.status_code == 409

    assert api.post(f"/api/tasks/{backlog['id']}/enqueue").json()["status"] == "queued"
    assert api.delete(f"/api/tasks/{backlog['id']}").status_code == 409  # cancel it first
    cancelled = api.post(f"/api/tasks/{backlog['id']}/cancel").json()
    assert cancelled["status"] == "cancelled" and cancelled["finished_at"]
    assert api.post(f"/api/tasks/{backlog['id']}/cancel").status_code == 409
    assert api.delete(f"/api/tasks/{backlog['id']}").status_code == 204


def test_waiting_task_retry_and_manual_completion(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    task = create(api, project_id, agent_id, "falló")
    with api.app.state.sessionmaker() as db:
        row = db.get(Task, task["id"])
        task_ops.wait_for_human(db, row, task_ops.WaitingReason.RUN_EXITED, "exit code 1")
        db.commit()
    waiting = api.get(f"/api/tasks/{task['id']}").json()
    assert (waiting["status"], waiting["waiting_reason"], waiting["waiting_detail"]) == (
        "waiting_human",
        "run_exited",
        "exit code 1",
    )
    assert api.post(f"/api/tasks/{task['id']}/retry").json()["status"] == "queued"

    with api.app.state.sessionmaker() as db:
        task_ops.wait_for_human(db, db.get(Task, task["id"]), task_ops.WaitingReason.RUN_EXITED)
        db.commit()
    done = api.post(f"/api/tasks/{task['id']}/complete", json={"summary": "Hecho a mano"}).json()
    assert done["status"] == "done"
    kinds = [e["kind"] for e in api.get(f"/api/tasks/{task['id']}/events").json()]
    assert kinds[-2:] == ["completed_manually", "done"]


def test_busy_agents_and_projects_cannot_be_deleted(api: TestClient, tmp_path: Path):
    agent_id, project_id = seed(api, tmp_path)
    task = create(api, project_id, agent_id, "trabajando")
    queued = create(api, project_id, agent_id, "esperando")
    with api.app.state.sessionmaker() as db:
        db.get(Task, task["id"]).status = TaskStatus.RUNNING
        db.commit()
    assert api.delete(f"/api/agents/{agent_id}").json()["detail"]["code"] == "agent_busy"
    assert api.delete(f"/api/projects/{project_id}").json()["detail"]["code"] == "project_busy"

    with api.app.state.sessionmaker() as db:
        db.get(Task, task["id"]).status = TaskStatus.DONE
        db.commit()
    assert api.delete(f"/api/agents/{agent_id}").status_code == 204
    orphan = api.get(f"/api/tasks/{queued['id']}").json()
    assert (orphan["status"], orphan["waiting_reason"], orphan["agent_id"]) == (
        "waiting_human",
        "no_agent",
        None,
    )
    assert api.delete(f"/api/projects/{project_id}").status_code == 204
    assert api.get(f"/api/tasks/{queued['id']}").status_code == 404  # tasks go with the project


def test_pause_switch(api: TestClient):
    assert api.post("/api/scheduler/resume").json()["paused"] is False
    assert api.get("/api/scheduler").json()["paused"] is False
