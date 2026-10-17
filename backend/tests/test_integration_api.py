"""Integrating a task through the API (phase 12, block 5)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from gitrepos import commit_file, make_repo, sh
from test_git_api import make_project
from test_integration import work_on

from agentic_os.models import Project, Task


def setup_task(client: TestClient, tmp_path: Path, files: dict[str, str], **project) -> tuple:
    folder = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    created = make_project(client, folder, workspace_mode="worktree")
    if project:
        client.patch(f"/api/projects/{created['id']}", json=project).raise_for_status()
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(Project, created["id"])
        task = work_on(db, row, files)
        db.commit()
        return folder, task.id, created["id"]


def test_check_integrate_and_undo(client: TestClient, tmp_path: Path):
    folder, task_id, _ = setup_task(client, tmp_path, {"login.py": "login\n"})

    checked = client.get(f"/api/tasks/{task_id}/integration").json()
    assert checked["can_integrate"] and checked["repos"][0]["state"] == "clean"

    before = sh(folder, "rev-parse", "main")
    done = client.post(f"/api/tasks/{task_id}/integrate", json={"mode": "squash"})
    assert done.status_code == 200, done.text
    assert done.json()["integrated"] == 1 and (folder / "login.py").exists()
    assert client.get(f"/api/tasks/{task_id}/integration").json()["repos"][0]["state"] == (
        "integrated"
    )

    undone = client.post(f"/api/tasks/{task_id}/integration/undo")
    assert undone.status_code == 200 and undone.json() == {"undone": 1}
    assert sh(folder, "rev-parse", "main") == before


def test_the_project_decides_how_when_no_mode_is_given(client: TestClient, tmp_path: Path):
    folder, task_id, _ = setup_task(
        client, tmp_path, {"login.py": "login\n"}, integration_mode="squash"
    )
    assert client.post(f"/api/tasks/{task_id}/integrate", json={}).status_code == 200
    assert len(sh(folder, "log", "-1", "--format=%P").split()) == 1  # squash: one parent


def test_a_conflict_is_a_result_not_an_error_and_a_resolver_task_can_be_made(
    client: TestClient, tmp_path: Path
):
    folder, task_id, _ = setup_task(client, tmp_path, {"a.txt": "task\n"})
    commit_file(folder, "a.txt", "main\n", message="main edits a")

    result = client.post(f"/api/tasks/{task_id}/integrate", json={})
    assert result.status_code == 200
    body = result.json()
    assert body["stopped"] and body["repos"][0]["status"] == "conflicts"

    agent = client.post("/api/agents", json={"name": "Fixer"}).json()
    fix = client.post(f"/api/tasks/{task_id}/resolve-conflicts", json={"agent_id": agent["id"]})
    assert fix.status_code == 201, fix.text
    assert fix.json()["title"].startswith("Resolver conflictos de T-")
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.get(Task, fix.json()["id"]).resolves_task_id == task_id  # type: ignore[union-attr]


def test_resolving_here_through_the_api(client: TestClient, tmp_path: Path):
    folder, task_id, _ = setup_task(client, tmp_path, {"a.txt": "task\n"})
    commit_file(folder, "a.txt", "main\n", message="main edits a")
    repo_id = client.get(f"/api/tasks/{task_id}/integration").json()["repos"][0]["repo_id"]

    started = client.post(f"/api/tasks/{task_id}/integration/resolution", json={"repo_id": repo_id})
    assert started.status_code == 200 and started.json()["conflicts"] == ["a.txt"]
    path = Path(started.json()["path"])
    early = client.post(
        f"/api/tasks/{task_id}/integration/resolution/finish", json={"repo_id": repo_id}
    )
    assert early.status_code == 409 and early.json()["detail"]["code"] == "conflicts_unresolved"

    (path / "a.txt").write_text("both\n", "utf-8", newline="\n")
    sh(path, "add", "a.txt")
    finished = client.post(
        f"/api/tasks/{task_id}/integration/resolution/finish", json={"repo_id": repo_id}
    )
    assert finished.status_code == 204
    assert client.get(f"/api/tasks/{task_id}/integration").json()["can_integrate"]


def test_a_task_without_branches_has_nothing_to_integrate(client: TestClient, tmp_path: Path):
    folder = make_repo(tmp_path / "web")
    project = make_project(client, folder)
    agent = client.post("/api/agents", json={"name": "Dev"}).json()
    task = client.post(
        "/api/tasks",
        json={"project_id": project["id"], "title": "x", "agent_id": agent["id"], "enqueue": False},
    ).json()
    assert client.get(f"/api/tasks/{task['id']}/integration").json()["repos"] == []
    response = client.post(f"/api/tasks/{task['id']}/integrate", json={})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "no_branches"
