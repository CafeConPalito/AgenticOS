"""What each run changed, end to end: a real backend, its scheduler and the fake CLI in a real
ConPTY, on real git repositories (phase 11, ADR 0015)."""

from __future__ import annotations

from pathlib import Path

import httpx
from live_server import live_server
from test_changes import commit, make_run, write
from test_scheduler import db_factory, make_project  # noqa: F401 - pytest fixture
from test_scheduler_e2e import Api, settings_for
from test_worktrees import make_repo, sh

from agentic_os.config import Settings
from agentic_os.models import Run, RunStatus, WorkspaceMode
from agentic_os.services import snapshots
from agentic_os.services.runs.manager import RunManager

# (A title starts with a plain word: the prompt is `T-1 · <title>`.)
# Dev commits halfway and leaves b.py uncommitted; every stage of the task runs the same title.
WORK = "trabajo; ANADE: a.py=x; COMMIT: feat a; ANADE: b.py=y"


def runs_of(api: Api, task_id: str) -> list[dict]:
    return sorted(api.get(f"/api/runs?task_id={task_id}"), key=lambda r: r["created_at"])


def listed(body: dict) -> dict[str, tuple[int, int]]:
    return {f["path"]: (f["additions"], f["deletions"]) for f in body["files"]}


def pipeline(server_url: str, project: str, dev: str, qa: str) -> None:
    response = httpx.put(
        f"{server_url}/api/projects/{project}/pipeline",
        json={
            "name": "Dev y QA",
            "stages": [
                {"name": "Desarrollo", "agent_id": dev},
                {"name": "QA", "agent_id": qa, "reject_to": 0},
            ],
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text


def test_a_worktree_task_with_a_rejection_shows_each_runs_own_changes(tmp_path: Path):
    repo = make_repo(tmp_path / "mi web")
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.post("/api/scheduler/pause")
        project = api.post(
            "/api/projects", {"name": "Mi web", "path": str(repo), "workspace_mode": "worktree"}
        )["id"]
        dev = api.post("/api/agents", {"name": "Dev", "cli": "claude"})["id"]
        qa = api.post("/api/agents", {"name": "Gema", "cli": "claude"})["id"]
        pipeline(server.url, project, dev, qa)
        task = api.post(
            "/api/tasks",
            {"project_id": project, "title": f"{WORK}; RECHAZA1: falta el test; TERMINA: hecho"},
        )
        api.post("/api/scheduler/resume")

        done = api.wait_status(task["id"], "done", "waiting_human", timeout=240)
        assert done["status"] == "done" and done["rejections"] == 1, done
        base = sh(repo, "rev-parse", "main")
        assert done["worktree_path"] is None and not (tmp_path / "mi web.wt" / "T-1").exists()

        # Dev, QA (which rejects), Dev again and QA: four runs, one folder.
        runs = runs_of(api, task["id"])
        assert len(runs) == 4
        per_run = [api.get(f"/api/runs/{r['id']}/changes") for r in runs]
        assert all(body["state"] == "ok" and not body["live"] for body in per_run)
        # Every run appends one line to a.py (committed) and b.py (left uncommitted); the
        # rejecting QA run also leaves the CLI's marker file.
        assert [listed(b) for b in per_run] == [
            {"a.py": (1, 0), "b.py": (1, 0)},
            {"a.py": (1, 0), "b.py": (1, 0), ".fake-rejected": (1, 0)},
            {"a.py": (1, 0), "b.py": (1, 0)},
            {"a.py": (1, 0), "b.py": (1, 0)},
        ]
        assert [r["changes"]["files"] for r in runs] == [2, 3, 2, 2]  # the +/- on the run list

        whole = api.get(f"/api/tasks/{task['id']}/changes")
        assert whole["state"] == "ok" and whole["from_ref"]["kind"] == "base"
        assert whole["to_ref"] == {"kind": "branch", "name": "agentic/T-1"}
        assert listed(whole) == {"a.py": (4, 0), "b.py": (4, 0), ".fake-rejected": (1, 0)}
        # The same numbers as `git diff` on the branch the worktree left behind (CA1).
        expected = {
            path: (int(added), int(deleted))
            for added, deleted, path in (
                line.split("\t")
                for line in sh(repo, "diff", "--numstat", base, "agentic/T-1").splitlines()
            )
        }
        assert listed(whole) == expected
        assert [r["attempt"] for r in whole["runs"]] == [1, 1, 2, 2]
        assert [r["stage_name"] for r in whole["runs"]] == ["Desarrollo", "QA", "Desarrollo", "QA"]

        # The snapshots live in the project's repository and the checkout is untouched (CA4).
        for run in runs:
            for label in ("start", "end"):
                assert sh(repo, "rev-parse", snapshots.ref_name(run["id"], label))
        assert sh(repo, "status", "--porcelain") == ""
        assert sh(repo, "branch", "--show-current") == "main"
        diff = api.get(f"/api/tasks/{task['id']}/changes/file?path=a.py")
        assert [line["text"] for h in diff["hunks"] for line in h["lines"]] == ["x"] * 4


def test_a_direct_folder_leaves_out_what_the_user_had_before(tmp_path: Path):
    repo = make_repo(tmp_path / "web")
    write(repo, "notas.md", "mias\n")  # the user's own work, not committed
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        project = api.post("/api/projects", {"name": "Web", "path": str(repo)})["id"]
        dev = api.post("/api/agents", {"name": "Dev", "cli": "claude"})["id"]
        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": dev, "title": f"{WORK}; TERMINA: hecho"},
        )

        api.wait_status(task["id"], "done", "waiting_human", timeout=120)

        (run,) = runs_of(api, task["id"])
        body = api.get(f"/api/runs/{run['id']}/changes")
        # The agent's COMMIT also committed notas.md, but it was already in the starting snapshot.
        assert listed(body) == {"a.py": (1, 0), "b.py": (1, 0)}
        whole = api.get(f"/api/tasks/{task['id']}/changes")
        assert whole["direct_folder"] is True and whole["from_ref"]["kind"] == "task_start"
        assert listed(whole) == listed(body)


def test_a_folder_without_git_has_no_changes(tmp_path: Path):
    folder = tmp_path / "plano"
    folder.mkdir()
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        project = api.post("/api/projects", {"name": "Plano", "path": str(folder)})["id"]
        dev = api.post("/api/agents", {"name": "Dev", "cli": "claude"})["id"]
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": dev,
                "title": "trabajo; ESCRIBE: a.txt=1; TERMINA: ok",
            },
        )

        api.wait_status(task["id"], "done", "waiting_human", timeout=120)

        (run,) = runs_of(api, task["id"])
        assert run["changes"] is None
        assert api.get(f"/api/runs/{run['id']}/changes")["state"] == "no_git"
        assert api.get(f"/api/tasks/{task['id']}/changes")["state"] == "no_git"
        assert (folder / "a.txt").exists()


def test_recovery_closes_the_changes_of_an_interrupted_run(
    db_factory,  # noqa: F811
    tmp_path: Path,
):
    repo = make_repo(tmp_path / "mi web")
    manager = RunManager(db_factory, Settings(_env_file=None, data_dir=tmp_path / "data"))
    with db_factory() as db:
        project = make_project(db, "Web", WorkspaceMode.DIRECT)
        project.path = str(repo)
        start = snapshots.take(str(repo), "r1", "start")
        write(repo, "a.py", "1\n2\n")
        commit(repo, "feat")
        write(repo, "b.py", "sin commitear\n")
        run = make_run(db, project, repo, status=RunStatus.RUNNING, start=start.sha)
        db.commit()
        run_id = run.id

    assert manager.recover() == 1  # the backend died with the run open

    with db_factory() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.INTERRUPTED and run.snapshot_end
        assert (run.changes_files, run.changes_added, run.changes_deleted) == (2, 3, 0)
