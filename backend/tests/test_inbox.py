"""The Inbox API and its sync with the tasks (phase 06). The scheduler is paused: tasks change
state through task_ops, as the scheduler would."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import InboxKind, Run, RunStatus, Task, WaitingReason
from agentic_os.services import inbox
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
        "limits": True,
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


class FakeSession:
    alive = True

    def __init__(self) -> None:
        self.delivered: list[str] = []

    def deliver(self, message: str) -> None:
        self.delivered.append(message)


def add_run(db, task: Task, parent_id: str | None, status: str) -> Run:
    run = Run(
        workspace_id=DEFAULT_WORKSPACE,
        agent_name="Dev",
        agent_color="#fff",
        project_name="Web",
        cli="claude",
        prompt="p",
        cwd="x",
        status=status,
        task_id=task.id,
        parent_run_id=parent_id,
    )
    db.add(run)
    db.flush()
    return run


def test_an_answer_to_an_ended_subagent_reaches_its_parent(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Hija"}).json()
    parent = FakeSession()
    with api.app.state.sessionmaker() as db:
        row = db.get(Task, task["id"])
        row.status = "running"
        parent_run = add_run(db, row, None, RunStatus.RUNNING)
        child_run = add_run(db, row, parent_run.id, RunStatus.EXITED)
        inbox.create(db, InboxKind.QUESTION, "¿A o B?", task=row, run=child_run)
        task_ops.wait_for_human(db, row, WaitingReason.HUMAN_REQUEST, "¿A o B?")
        db.commit()
        api.app.state.run_manager._live[parent_run.id] = parent
    [item] = api.get("/api/inbox").json()
    api.post(f"/api/inbox/{item['id']}/answer", json={"text": "B"})
    assert parent.delivered == ["Respuesta de la persona a «¿A o B?»: B"]
    assert api.get(f"/api/tasks/{task['id']}").json()["status"] == "running"
    api.app.state.run_manager._live.clear()


def test_dismissing_a_question_lets_the_task_go_on(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Pregunta"}).json()
    with api.app.state.sessionmaker() as db:
        row = db.get(Task, task["id"])
        inbox.create(db, InboxKind.QUESTION, "¿A o B?", task=row)
        task_ops.wait_for_human(db, row, WaitingReason.QUESTION_PENDING, "¿A o B?")
        db.commit()
    question = next(i for i in api.get("/api/inbox").json() if i["kind"] == "question")
    dismissed = api.post(f"/api/inbox/{question['id']}/dismiss").json()
    assert dismissed["resolution"] == "dismissed"
    assert api.get(f"/api/tasks/{task['id']}").json()["status"] == "queued"  # no CLI: a new run


def test_the_task_shows_its_own_run_not_a_subagent(api: TestClient, tmp_path: Path):
    project, _ = project_with_review(api, tmp_path)
    task = api.post("/api/tasks", json={"project_id": project, "title": "Árbol"}).json()
    with api.app.state.sessionmaker() as db:
        row = db.get(Task, task["id"])
        row.status = "running"
        main = add_run(db, row, None, RunStatus.RUNNING)
        add_run(db, row, main.id, RunStatus.RUNNING)  # created later
        db.commit()
        main_id = main.id
    read = api.get(f"/api/tasks/{task['id']}").json()
    assert (read["active_run_id"], read["last_run_id"]) == (main_id, main_id)
