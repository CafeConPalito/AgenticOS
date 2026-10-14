"""GET /api/home: the agents' state, their sessions, the projects and the counters."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import InboxKind, Run, Task
from agentic_os.services import inbox


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        yield client


def make_agent(api: TestClient, name: str, **extra) -> str:
    return api.post("/api/agents", json={"name": name, "role": "Dev", **extra}).json()["id"]


def make_project(api: TestClient, tmp_path: Path, name: str = "Web") -> str:
    folder = tmp_path / name
    folder.mkdir()
    return api.post("/api/projects", json={"name": name, "path": str(folder)}).json()["id"]


def make_task(api: TestClient, project: str, agent: str | None, title: str, **extra) -> dict:
    body = {"project_id": project, "agent_id": agent, "title": title, **extra}
    return api.post("/api/tasks", json=body).json()


def make_run(api: TestClient, task_id: str | None, agent_id: str, project_id: str, **fields) -> str:
    agent = api.get(f"/api/agents/{agent_id}").json()
    project = api.get(f"/api/projects/{project_id}").json()
    with api.app.state.sessionmaker() as db:
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_id=agent_id,
            project_id=project_id,
            agent_name=agent["name"],
            agent_color=agent["color"],
            project_name=project["name"],
            cli="claude",
            prompt="x",
            cwd=project["path"],
            task_id=task_id,
            **fields,
        )
        db.add(run)
        db.commit()
        return run.id


def set_status(api: TestClient, task_id: str, status: str) -> None:
    with api.app.state.sessionmaker() as db:
        db.get(Task, task_id).status = status
        db.commit()


def agent_of(home: dict, agent_id: str) -> dict:
    return next(a for a in home["agents"] if a["id"] == agent_id)


def test_empty_home(api: TestClient):
    assert api.get("/api/home").json() == {
        "agents": [],
        "projects": [],
        "counts": {"sessions": 0, "agents_working": 0, "open_tasks": 0, "active_runs": 0},
    }


def test_agent_states_and_queues(api: TestClient, tmp_path: Path):
    project = make_project(api, tmp_path)
    idle = make_agent(api, "Idle")
    busy = make_agent(api, "Busy")
    asks = make_agent(api, "Asks")
    stuck = make_agent(api, "Stuck")
    draft = make_agent(api, "Draft", status="draft")

    make_task(api, project, idle, "Una")
    make_task(api, project, idle, "Dos")
    running = make_task(api, project, busy, "En curso")
    make_run(api, running["id"], busy, project, status="running")
    set_status(api, make_task(api, project, stuck, "Atascada")["id"], "waiting_human")
    question = make_task(api, project, asks, "Pregunta")
    with api.app.state.sessionmaker() as db:
        inbox.create(db, InboxKind.QUESTION, "¿Cuál?", task=db.get(Task, question["id"]))
        db.commit()

    home = api.get("/api/home").json()
    assert {a["name"]: a["state"] for a in home["agents"]} == {
        "Idle": "idle",
        "Busy": "running",
        "Asks": "waiting",  # a pending request
        "Stuck": "waiting",  # a task waiting for the person
        "Draft": "draft",
    }
    assert agent_of(home, idle)["queued"] == 2
    assert agent_of(home, asks)["pending_requests"] == 1
    assert agent_of(home, draft)["queued"] == 0
    assert agent_of(home, busy)["sessions"][0]["task_code"] == running["code"]


def test_waiting_comes_before_running(api: TestClient, tmp_path: Path):
    project = make_project(api, tmp_path)
    agent = make_agent(api, "Dev", max_concurrency=2)
    running = make_task(api, project, agent, "A")
    make_run(api, running["id"], agent, project, status="running")
    set_status(api, make_task(api, project, agent, "B")["id"], "waiting_human")
    home = api.get("/api/home").json()
    assert agent_of(home, agent)["state"] == "waiting"
    assert home["counts"]["agents_working"] == 1


def test_sessions_live_and_resumable(api: TestClient, tmp_path: Path):
    project = make_project(api, tmp_path)
    agent = make_agent(api, "Dev")
    live_task = make_task(api, project, agent, "Viva")
    make_run(api, live_task["id"], agent, project, status="starting")
    cut = make_task(api, project, agent, "Cortada")
    make_run(api, cut["id"], agent, project, status="interrupted", cli_session_id="sess-1")
    set_status(api, cut["id"], "waiting_human")
    # Not resumable: no conversation to go back to.
    make_run(api, None, agent, project, status="stopped")
    # A subagent never shows as a session of its own.
    parent = make_run(api, None, agent, project, status="running")
    make_run(api, None, agent, project, status="running", parent_run_id=parent)

    sessions = agent_of(api.get("/api/home").json(), agent)["sessions"]
    by_status = {s["status"]: s for s in sessions}
    assert sorted(s["status"] for s in sessions) == ["interrupted", "running", "starting"]
    assert not by_status["starting"]["resumable"]
    assert by_status["starting"]["task_title"] == "Viva"
    assert by_status["interrupted"]["resumable"]
    assert by_status["interrupted"]["task_code"] == cut["code"]


def test_projects_workers_and_counters(api: TestClient, tmp_path: Path):
    web = make_project(api, tmp_path, "Web")
    docs = make_project(api, tmp_path, "Docs")
    dev = make_agent(api, "Dev")
    ana = make_agent(api, "Ana")
    working = make_task(api, web, dev, "Login")
    make_run(api, working["id"], dev, web, status="running")
    set_status(api, working["id"], "running")
    make_task(api, web, ana, "Pagos")
    make_task(api, web, ana, "Idea", enqueue=False)
    set_status(api, make_task(api, docs, ana, "Hecha")["id"], "done")

    home = api.get("/api/home").json()
    projects = {p["name"]: p for p in home["projects"]}
    assert projects["Web"]["open_tasks"] == 3  # backlog included, like the Board
    assert projects["Docs"]["open_tasks"] == 0
    assert projects["Web"]["workers"] == [
        {"agent_id": dev, "agent_name": "Dev", "task_code": working["code"], "task_title": "Login"}
    ]
    assert projects["Docs"]["workers"] == []
    assert home["counts"] == {
        "sessions": 1,
        "agents_working": 1,
        "open_tasks": 3,
        "active_runs": 1,
    }
