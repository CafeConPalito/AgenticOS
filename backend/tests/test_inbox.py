"""The Inbox API and its sync with the tasks (phase 06). The scheduler is paused: tasks change
state through task_ops, as the scheduler would."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.models import Task, WaitingReason
from agentic_os.services import tasks as task_ops


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        yield client


def project_with_review(api: TestClient, tmp_path: Path) -> tuple[str, str]:
    folder = tmp_path / "web"
    folder.mkdir()
    dev = api.post("/api/agents", json={"name": "Dev"}).json()["id"]
    project = api.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()["id"]
    api.put(
        f"/api/projects/{project}/pipeline",
        json={"stages": [{"name": "Desarrollo", "agent_id": dev, "requires_review": True}]},
    )
    return project, dev


def run_stage(api: TestClient, task_id: str, summary: str) -> None:
    with api.app.state.sessionmaker() as db:
        task = db.get(Task, task_id)
        task.status = "running"
        task_ops.stage_completed(db, task, summary, None)
        db.commit()


def test_review_and_delivery_items_follow_the_task(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Login"}).json()
    run_stage(api, task["id"], "login hecho")

    [review] = api.get("/api/inbox").json()
    assert (review["kind"], review["title"], review["detail"]) == (
        "review",
        f"{task['code']} · Login",
        "login hecho",
    )
    assert (review["task_code"], review["agent_name"], review["project_name"]) == (
        task["code"],
        "Dev",
        "Web",
    )
    approved = api.post(f"/api/inbox/{review['id']}/review", json={"approve": True}).json()
    assert approved["resolution"] == "approved"
    assert api.get(f"/api/tasks/{task['id']}").json()["status"] == "done"

    [delivery] = api.get("/api/inbox").json()
    assert (delivery["kind"], delivery["detail"]) == ("delivery", "login hecho")
    seen = api.post(f"/api/inbox/{delivery['id']}/dismiss").json()
    assert seen["resolution"] == "reviewed"
    assert api.get("/api/inbox/summary").json()["pending"] == 0
    resolved = api.get("/api/inbox?status=resolved").json()
    assert {i["kind"] for i in resolved} == {"review", "delivery"}


def test_reviewing_from_the_task_resolves_the_inbox_item(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Pagos"}).json()
    run_stage(api, task["id"], "pagos hechos")
    api.post(f"/api/tasks/{task['id']}/review", json={"action": "reject", "reason": "Falta móvil"})
    [item] = api.get("/api/inbox?status=resolved").json()
    assert (item["resolution"], item["response"]) == ("rejected", "Falta móvil")
    conflict = api.post(f"/api/inbox/{item['id']}/review", json={"approve": True})
    assert (conflict.status_code, conflict.json()["detail"]["code"]) == (409, "inbox_resolved")


def test_a_task_waiting_for_the_person_shows_up_until_it_moves(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Falla"}).json()
    with api.app.state.sessionmaker() as db:
        row = db.get(Task, task["id"])
        task_ops.wait_for_human(db, row, WaitingReason.RUN_EXITED, "exit code 3")
        task_ops.wait_for_human(db, row, WaitingReason.RUN_FAILED)  # replaces the first one
        db.commit()
    [item] = api.get("/api/inbox").json()
    assert (item["kind"], item["detail"]) == ("attention", "La ejecución falló")

    api.post(f"/api/tasks/{task['id']}/retry")
    assert api.get("/api/inbox").json() == []
    assert api.get("/api/inbox?status=resolved").json()[-1]["resolution"] == "dismissed"


def test_cancelling_a_task_dismisses_what_was_pending(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Cancelar"}).json()
    run_stage(api, task["id"], "hecho")
    api.post(f"/api/tasks/{task['id']}/cancel")
    assert api.get("/api/inbox").json() == []


def test_notifications_bookkeeping_and_settings(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Avisos"}).json()
    run_stage(api, task["id"], "hecho")
    summary = api.get("/api/inbox/summary").json()
    assert summary["pending"] == 1 and len(summary["unnotified"]) == 1
    item_id = summary["unnotified"][0]["id"]
    assert api.post(f"/api/inbox/{item_id}/notified").json()["notified_at"]
    assert api.get("/api/inbox/summary").json()["unnotified"] == []

    defaults = api.get("/api/settings/notifications").json()
    assert defaults == {
        "approval": True,
        "question": True,
        "review": True,
        "stalled": True,
        "delivery": False,
        "sound": True,
    }
    changed = api.put(
        "/api/settings/notifications", json={**defaults, "review": False, "sound": False}
    ).json()
    assert (changed["review"], changed["sound"]) == (False, False)
    assert api.get("/api/settings/notifications").json() == changed
    assert api.put("/api/settings/notifications", json={"nope": True}).status_code == 422


def test_wrong_actions_per_kind(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Tipos"}).json()
    run_stage(api, task["id"], "hecho")
    [review] = api.get("/api/inbox").json()
    for path, body in (("answer", {"text": "hola"}), ("approve", None), ("reject", None)):
        response = api.post(f"/api/inbox/{review['id']}/{path}", json=body)
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "inbox_kind")
    assert api.post("/api/inbox/nope/dismiss").status_code == 404
