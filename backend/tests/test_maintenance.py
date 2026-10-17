"""Cleanup (phase 08): task branches on a real repository, and the terminal logs' retention."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from test_worktrees import make_repo, sh

from agentic_os.db.base import utcnow
from agentic_os.models import Project, Run, RunRepo, RunStatus, Task, TaskStatus
from agentic_os.services import changes, snapshots


def setup_branches(client: TestClient, tmp_path: Path) -> tuple[str, dict[str, str]]:
    """A project whose repository has the branches of four tasks:
    T-1 done and merged, T-2 done with unmerged work, T-3 still running (its worktree has the
    branch), and a branch whose task no longer exists."""
    repo = make_repo(tmp_path / "web app")
    client.post("/api/scheduler/pause")  # the scheduler must not launch these tasks
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
    assert deleted == {"deleted": ["agentic/T-1", "agentic/T-9"], "failed": {}}
    forced = client.post(
        delete, json={"project_id": project, "branches": ["agentic/T-2"], "force": True}
    ).json()
    assert forced == {"deleted": ["agentic/T-2"], "failed": {}}
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


def test_merged_into_the_base_branch_whatever_is_checked_out(client: TestClient, tmp_path: Path):
    project, _ = setup_branches(client, tmp_path)
    repo = tmp_path / "web app"
    sh(repo, "checkout", "-q", "-b", "feature-x", "main~0")
    (repo / "x.txt").write_text("x", "utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "x")
    deleted = client.post(
        "/api/maintenance/branches/delete",
        json={"project_id": project, "branches": ["agentic/T-1"]},
    ).json()
    assert deleted == {"deleted": ["agentic/T-1"], "failed": {}}


def test_a_locked_log_is_tried_again_later(client: TestClient, monkeypatch):
    log = add_run(client, "old", days_ago=100)
    real_unlink = Path.unlink

    def locked(self, missing_ok=False):
        if self == log:
            raise PermissionError("in use")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)
    assert client.post("/api/maintenance/logs/cleanup").json()["runs"] == 0
    assert client.get("/api/runs/old").json()["log_purged"] is False
    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert client.post("/api/maintenance/logs/cleanup").json()["runs"] == 1


# ---------------------------------------------------------------- snapshots (phase 11)
def snapshot_project(client: TestClient, tmp_path: Path) -> tuple[Path, str]:
    """A project on a real repository with two old runs and one recent run that have snapshots."""
    repo = make_repo(tmp_path / "web app")
    project = client.post("/api/projects", json={"name": "Web", "path": str(repo)}).json()["id"]
    repo_id = client.get(f"/api/projects/{project}/repos").json()[0]["id"]
    for run_id, days in (("old1", 100), ("old2", 120), ("recent", 5)):
        add_run(client, run_id, days_ago=days)
        start = snapshots.take(str(repo), run_id, "start")
        (repo / f"{run_id}.txt").write_text("a\nb\n", "utf-8")
        end = snapshots.take(str(repo), run_id, "end")
        with client.app.state.sessionmaker() as db:
            run = db.get(Run, run_id)
            run.project_id = project
            db.add(
                RunRepo(
                    run_id=run_id,
                    repo_id=repo_id,
                    repo_name="web app",
                    path=str(repo),
                    snapshot_start=start.sha,
                    snapshot_end=end.sha,
                )
            )
            run.changes_files, run.changes_added, run.changes_deleted = 1, 2, 0
            db.commit()
    return repo, project


def refs_of(repo: Path) -> set[str]:
    out = sh(repo, "for-each-ref", "--format=%(refname)", "refs/agentic-os/")
    return {ref.split("/")[3] for ref in out.splitlines()}


def test_purging_the_logs_drops_the_snapshots_but_keeps_the_summary(
    client: TestClient, tmp_path: Path
):
    repo, _ = snapshot_project(client, tmp_path)
    assert refs_of(repo) == {"old1", "old2", "recent"}

    assert client.post("/api/maintenance/logs/cleanup").json()["runs"] == 2

    assert refs_of(repo) == {"recent"}
    old = client.get("/api/runs/old1").json()
    assert old["changes"] == {"files": 1, "additions": 2, "deletions": 0}  # the summary stays
    assert client.get("/api/runs/old1/changes").json()["state"] == "snapshot_missing"
    assert client.get("/api/runs/recent/changes").json()["state"] == "ok"


def test_lists_and_deletes_the_snapshots_of_a_project(client: TestClient, tmp_path: Path):
    repo, project = snapshot_project(client, tmp_path)

    listed = client.get("/api/maintenance/snapshots").json()
    assert listed == [{"project_id": project, "project_name": "Web", "runs": 3}]

    deleted = client.post(f"/api/maintenance/snapshots/{project}/delete").json()

    assert deleted == {"runs": 3} and refs_of(repo) == set()
    assert client.get("/api/maintenance/snapshots").json() == []
    assert client.get("/api/runs/recent/changes").json()["state"] == "snapshot_missing"
    assert client.get("/api/runs/recent").json()["changes"]["files"] == 1
    assert client.post("/api/maintenance/snapshots/nope/delete").status_code == 404


def test_deleting_a_project_deletes_its_snapshots(client: TestClient, tmp_path: Path):
    repo, project = snapshot_project(client, tmp_path)

    assert client.delete(f"/api/projects/{project}").status_code == 204

    assert refs_of(repo) == set()
    assert sh(repo, "status", "--porcelain").count("txt") == 3  # the folder is never touched


def test_a_task_whose_first_run_was_purged_has_no_complete_diff(client: TestClient, tmp_path: Path):
    _repo, project = snapshot_project(client, tmp_path)
    client.post("/api/scheduler/pause")
    agent = client.post("/api/agents", json={"name": "Dev"}).json()["id"]
    task_id = client.post(
        "/api/tasks", json={"project_id": project, "agent_id": agent, "title": "Login"}
    ).json()["id"]
    with client.app.state.sessionmaker() as db:
        for run_id in ("old1", "recent"):  # two runs of the same task; the first is old
            run = db.get(Run, run_id)
            run.task_id, run.started_at = task_id, run.ended_at
        db.commit()
    assert client.get(f"/api/tasks/{task_id}/changes").json()["state"] == "ok"

    client.post("/api/maintenance/logs/cleanup")

    # old1 lost its snapshots: a diff starting at `recent` would pass for the whole task
    assert client.get(f"/api/tasks/{task_id}/changes").json()["state"] == "snapshot_missing"
    with client.app.state.sessionmaker() as db:
        assert changes.task_range(db, db.get(Task, task_id)).state == "snapshot_missing"
        assert db.get(Project, project) is not None


def test_forgetting_a_projects_snapshots_leaves_another_projects_in_the_same_repo(
    client: TestClient, tmp_path: Path
):
    repo, project = snapshot_project(client, tmp_path)  # old1, old2, recent
    with client.app.state.sessionmaker() as db:
        twin = Project(
            workspace_id="default",
            name="Gemelo",
            path=str(repo),
            path_key=f"{repo}-twin",  # the same repository registered a second time
        )
        db.add(twin)
        db.flush()
        mine = snapshots.take(str(repo), "mine", "start")
        run = Run(
            id="mine",
            workspace_id="default",
            agent_name="Dev",
            agent_color="#fff",
            project_name="Gemelo",
            project_id=twin.id,
            cli="claude",
            prompt="x",
            cwd=str(repo),
            status=RunStatus.COMPLETED,
        )
        db.add(run)
        db.flush()
        db.add(RunRepo(run_id="mine", repo_name="web app", path=str(repo), snapshot_start=mine.sha))
        db.commit()
        twin_id = twin.id

    assert client.post(f"/api/maintenance/snapshots/{project}/delete").json() == {"runs": 3}

    assert refs_of(repo) == {"mine"}  # the twin's own run keeps its snapshot
    with client.app.state.sessionmaker() as db:
        assert db.query(RunRepo).filter_by(run_id="mine").one().snapshot_start == mine.sha
    listed = client.get("/api/maintenance/snapshots").json()
    assert listed == [{"project_id": twin_id, "project_name": "Gemelo", "runs": 1}]
