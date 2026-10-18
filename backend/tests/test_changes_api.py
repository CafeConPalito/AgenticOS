"""The changes API: runs, tasks, agents, and the +/- on runs and Inbox items (phase 11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_changes import commit, make_run, run_in, write
from test_worktrees import make_repo

from agentic_os.models import Agent, InboxItem, InboxKind, Project, Task


@pytest.fixture
def api(client: TestClient) -> TestClient:
    client.post("/api/scheduler/pause")
    return client


def setup(api: TestClient, tmp_path: Path) -> tuple[Path, str, str, str]:
    """A direct-folder project on a real repository, an agent and a task whose run changed
    api.py (committed) and ui.py (left uncommitted). Returns the repo and the three ids."""
    repo = make_repo(tmp_path / "web app")
    project_id = api.post("/api/projects", json={"name": "Web", "path": str(repo)}).json()["id"]
    agent_id = api.post("/api/agents", json={"name": "Dev"}).json()["id"]
    task_id = api.post(
        "/api/tasks", json={"project_id": project_id, "agent_id": agent_id, "title": "Login"}
    ).json()["id"]

    def dev(folder: Path) -> None:
        write(folder, "api.py", "def login():\n    return 1\n")
        commit(folder, "feat: login")
        write(folder, "ui.py", "pendiente\n")

    with api.app.state.sessionmaker() as db:
        project, task, agent = db.get(Project, project_id), db.get(Task, task_id), None
        agent = db.get(Agent, agent_id)
        run = run_in(db, project, repo, task, dev)
        run.agent_id = agent.id
        db.commit()
    return repo, project_id, agent_id, task_id


def only_run_id(api: TestClient, task_id: str) -> str:
    (run,) = api.get("/api/runs", params={"task_id": task_id}).json()
    return run["id"]


def test_the_changes_of_a_run_and_of_its_task(api: TestClient, tmp_path: Path):
    _, _, _, task_id = setup(api, tmp_path)
    run_id = only_run_id(api, task_id)

    for url in (f"/api/runs/{run_id}/changes", f"/api/tasks/{task_id}/changes"):
        body = api.get(url).json()
        assert body["state"] == "ok" and not body["live"]
        assert body["totals"] == {"files": 2, "additions": 3, "deletions": 0}
        files = {f["path"]: f for f in body["repos"][0]["files"]}
        assert files["api.py"]["status"] == "added" and files["api.py"]["additions"] == 2
        assert files["ui.py"]["additions"] == 1
    task_body = api.get(f"/api/tasks/{task_id}/changes").json()
    assert [r["id"] for r in task_body["runs"]] == [run_id]
    assert task_body["runs"][0]["totals"]["files"] == 2


def test_the_diff_of_a_file_and_more_lines(api: TestClient, tmp_path: Path):
    _, _, _, task_id = setup(api, tmp_path)
    run_id = only_run_id(api, task_id)

    diff = api.get(f"/api/runs/{run_id}/changes/file", params={"path": "api.py"}).json()
    assert diff["binary"] is False and diff["too_large"] is False
    assert [line["text"] for line in diff["hunks"][0]["lines"]] == ["def login():", "    return 1"]
    lines = api.get(
        f"/api/tasks/{task_id}/changes/lines", params={"path": "api.py", "start": 2, "end": 9}
    ).json()
    assert [(line["new_no"], line["text"]) for line in lines["lines"]] == [(2, "    return 1")]


def test_paths_that_did_not_change_are_not_found(api: TestClient, tmp_path: Path):
    _, _, _, task_id = setup(api, tmp_path)
    run_id = only_run_id(api, task_id)

    for path in ("README.md", "*.py", "../x", "no-existe.txt"):
        response = api.get(f"/api/runs/{run_id}/changes/file", params={"path": path})
        assert response.status_code == 404, path
        response = api.get(
            f"/api/tasks/{task_id}/changes/lines", params={"path": path, "start": 1, "end": 5}
        )
        assert response.status_code == 404, path
    assert api.get(f"/api/runs/{run_id}/changes/file").status_code == 422  # path is required
    assert api.get("/api/runs/nope/changes").status_code == 404
    assert api.get("/api/tasks/nope/changes").status_code == 404


def test_runs_carry_their_summary_and_old_runs_have_none(api: TestClient, tmp_path: Path):
    _, project_id, agent_id, task_id = setup(api, tmp_path)
    run_id = only_run_id(api, task_id)
    assert api.get(f"/api/runs/{run_id}").json()["changes"] == {
        "files": 2,
        "additions": 3,
        "deletions": 0,
    }
    with api.app.state.sessionmaker() as db:
        old = make_run(db, db.get(Project, project_id), tmp_path / "web app")
        old.agent_id = agent_id
        db.commit()
        old_id = old.id
    assert api.get(f"/api/runs/{old_id}").json()["changes"] is None
    assert api.get(f"/api/runs/{old_id}/changes").json()["state"] == "no_snapshots"


def test_the_changes_of_an_agent(api: TestClient, tmp_path: Path):
    _, _project_id, agent_id, task_id = setup(api, tmp_path)
    run_id = only_run_id(api, task_id)

    listed = api.get(f"/api/agents/{agent_id}/changes").json()

    assert [r["run_id"] for r in listed] == [run_id]
    assert listed[0]["task_code"] == "T-1" and listed[0]["task_title"] == "Login"
    assert listed[0]["project_name"] == "Web"
    assert listed[0]["totals"] == {"files": 2, "additions": 3, "deletions": 0}
    other = api.get(f"/api/agents/{agent_id}/changes", params={"project_id": "otro"}).json()
    assert other == []
    assert api.get("/api/agents/nope/changes").status_code == 404


def test_review_and_delivery_items_carry_the_tasks_changes(api: TestClient, tmp_path: Path):
    _, project_id, agent_id, task_id = setup(api, tmp_path)
    with api.app.state.sessionmaker() as db:
        for kind in (InboxKind.REVIEW, InboxKind.DELIVERY, InboxKind.ATTENTION):
            db.add(
                InboxItem(
                    workspace_id="default",
                    kind=kind,
                    task_id=task_id,
                    agent_id=agent_id,
                    project_id=project_id,
                    title=kind.value,
                )
            )
        db.commit()

    items = {i["kind"]: i for i in api.get("/api/inbox").json()}

    expected = {"files": 2, "additions": 3, "deletions": 0}
    assert items["review"]["changes"] == expected
    assert items["delivery"]["changes"] == expected
    assert items["attention"]["changes"] is None  # only reviews and deliveries show them
