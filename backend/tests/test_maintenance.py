"""Cleanup (phase 08): task branches on a real repository, and the terminal logs' retention."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from test_worktrees import make_repo, sh

from agentic_os.db.base import utcnow
from agentic_os.models import Run, RunStatus, Task, TaskStatus


def setup_branches(client: TestClient, tmp_path: Path) -> tuple[str, dict[str, str]]:
    """A project whose repository has the branches of four tasks:
    T-1 done and merged, T-2 done with unmerged work, T-3 still running (its worktree has the
    branch), and a branch whose task no longer exists."""
    repo = make_repo(tmp_path / "web app")
    project = client.post("/api/projects", json={"name": "Web", "path": str(repo)}).json()
    agent = client.post("/api/agents", json={"name": "Dev"}).json()
    ids = {}
    for title in ("uno", "dos", "tres"):
        task = client.post(
            "/api/tasks",
            json={"project_id": project["id"], "agent_id": agent["id"], "title": title},
        ).json()
        ids[title] = task["id"]
    sh(repo, "branch", "agentic/T-1")
    sh(repo, "checkout", "-q", "-b", "agentic/T-2")
    (repo / "dos.txt").write_text("dos", "utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "dos")
    sh(repo, "checkout", "-q", "main")
    sh(repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "agentic/T-3")
    sh(repo, "branch", "agentic/T-9")
    with client.app.state.sessionmaker() as db:
        for title, code, status in (
            ("uno", "T-1", TaskStatus.DONE),
            ("dos", "T-2", TaskStatus.CANCELLED),
            ("tres", "T-3", TaskStatus.RUNNING),
        ):
            task = db.get(Task, ids[title])
            task.branch, task.status = f"agentic/{code}", status
        db.commit()
    return project["id"], ids


def branches_of(client: TestClient) -> dict[str, dict]:
    (project,) = client.get("/api/maintenance/branches").json()
    return {b["name"]: b for b in project["branches"]}


def test_lists_the_task_branches(client: TestClient, tmp_path: Path):
    setup_branches(client, tmp_path)
    branches = branches_of(client)
    assert set(branches) == {"agentic/T-1", "agentic/T-2", "agentic/T-3", "agentic/T-9"}
    assert (branches["agentic/T-1"]["merged"], branches["agentic/T-1"]["in_use"]) == (True, False)
    assert (branches["agentic/T-2"]["merged"], branches["agentic/T-2"]["in_use"]) == (False, False)
    assert branches["agentic/T-3"]["in_use"] is True  # running, and checked out
    assert branches["agentic/T-9"]["task_id"] is None
    assert branches["agentic/T-2"]["task_code"] == "T-2"


def test_merged_branches_go_unmerged_ones_need_force(client: TestClient, tmp_path: Path):
    project, _ = setup_branches(client, tmp_path)
    delete = "/api/maintenance/branches/delete"

    response = client.post(delete, json={"project_id": project, "branches": ["agentic/T-2"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "branch_not_merged"
    response = client.post(delete, json={"project_id": project, "branches": ["agentic/T-3"]})
    assert response.json()["detail"]["code"] == "branch_in_use"

    deleted = client.post(
        delete, json={"project_id": project, "branches": ["agentic/T-1", "agentic/T-9"]}
    ).json()
    assert deleted == {"deleted": ["agentic/T-1", "agentic/T-9"]}
    forced = client.post(
        delete, json={"project_id": project, "branches": ["agentic/T-2"], "force": True}
    ).json()
    assert forced == {"deleted": ["agentic/T-2"]}
    assert set(branches_of(client)) == {"agentic/T-3"}


def test_projects_without_git_or_task_branches_are_not_listed(client: TestClient, tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    client.post("/api/projects", json={"name": "Plain", "path": str(folder)})
    assert client.get("/api/maintenance/branches").json() == []


# ---------------------------------------------------------------- logs
def add_run(client: TestClient, run_id: str, days_ago: int, status=RunStatus.COMPLETED) -> Path:
    data = Path(client.app.state.settings.data_dir)
    log = data / "runs" / f"{run_id}.log"
    (data / "runs" / run_id).mkdir(parents=True)
    (data / "runs" / run_id / "mcp.json").write_text("{}", "utf-8")
    log.write_text("x" * 100, "utf-8")
    with client.app.state.sessionmaker() as db:
        db.add(
            Run(
                id=run_id,
                workspace_id="default",
                agent_name="Dev",
                agent_color="#fff",
                project_name="Web",
                cli="claude",
                prompt="hola",
                cwd=str(data),
                status=status,
                log_path=str(log),
                input_tokens=500,
                ended_at=utcnow() - timedelta(days=days_ago),
            )
        )
        db.commit()
    return log


def test_retention_defaults_to_90_days_and_can_be_turned_off(client: TestClient):
    assert client.get("/api/settings/maintenance").json() == {"log_retention_days": 90}
    client.put("/api/settings/maintenance", json={"log_retention_days": None})
    assert client.get("/api/settings/maintenance").json() == {"log_retention_days": None}
    response = client.put("/api/settings/maintenance", json={"log_retention_days": 0})
    assert response.status_code == 422


def test_cleanup_deletes_old_logs_and_keeps_the_runs(client: TestClient):
    old = add_run(client, "old", days_ago=100)
    recent = add_run(client, "recent", days_ago=5)

    result = client.post("/api/maintenance/logs/cleanup").json()

    assert result == {"runs": 1, "freed_bytes": 102}
    assert not old.exists() and not (old.parent / "old").exists()
    assert recent.exists()
    run = client.get("/api/runs/old").json()
    assert run["log_purged"] is True
    assert run["usage"]["input_tokens"] == 500
    assert client.post("/api/maintenance/logs/cleanup").json() == {"runs": 0, "freed_bytes": 0}


def test_without_retention_nothing_is_deleted(client: TestClient):
    log = add_run(client, "old", days_ago=1000)
    client.put("/api/settings/maintenance", json={"log_retention_days": None})
    assert client.post("/api/maintenance/logs/cleanup").json() == {"runs": 0, "freed_bytes": 0}
    assert log.exists()
