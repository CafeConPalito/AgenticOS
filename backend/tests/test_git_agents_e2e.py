"""What an agent did with git, end to end: a real backend, its scheduler and the fake CLI in a real
ConPTY, on real repositories with a bare remote (phase 12, block 7)."""

from __future__ import annotations

from pathlib import Path

import httpx
from gitrepos import make_bare, make_repo, sh
from live_server import live_server
from test_scheduler_e2e import Api, settings_for

# The agent commits, makes a branch, a tag and pushes its working branch: git as it would.
WORK = (
    "trabajo; ANADE: a.py=x; COMMIT: feat a; GITCMD: branch lateral; GITCMD: tag hito;"
    " GITCMD: push origin agentic/T-1; TERMINA: hecho"
)


def test_a_task_that_commits_branches_and_pushes_is_recorded_attributed_and_undone(
    tmp_path: Path,
):
    repo = make_repo(tmp_path / "mi web")
    bare = make_bare(tmp_path / "remote.git")
    sh(repo, "remote", "add", "origin", str(bare))
    sh(repo, "push", "-q", "-u", "origin", "main")
    base = sh(repo, "rev-parse", "main")

    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        project = api.post(
            "/api/projects", {"name": "Mi web", "path": str(repo), "workspace_mode": "worktree"}
        )["id"]
        dev = api.post("/api/agents", {"name": "Dev", "cli": "claude"})["id"]
        task = api.post("/api/tasks", {"project_id": project, "agent_id": dev, "title": WORK})

        done = api.wait_status(task["id"], "done", "waiting_human", timeout=240)
        assert done["status"] == "done", done
        (run,) = api.get(f"/api/runs?task_id={task['id']}")

        # What the run did, per repository.
        (part,) = api.get(f"/api/runs/{run['id']}/git")
        assert part["name"] == "mi web" and part["can_undo"] and part["pushed"]
        found = part["activity"]
        assert [c["subject"] for c in found["commits"]] == ["feat a"]
        assert {b["name"] for b in found["branches"]} == {"agentic/T-1", "lateral"}
        assert [t["name"] for t in found["tags"]] == ["hito"]
        (push,) = found["pushes"]
        assert (push["remote"], push["branch"], push["forced"]) == ("origin", "agentic/T-1", False)
        assert sh(bare, "rev-parse", "agentic/T-1") == found["commits"][0]["sha"]

        # The history, the detail and the task's own history say who made it.
        repo_id = api.get(f"/api/projects/{project}/repos")[0]["id"]
        page = api.get(f"/api/repos/{repo_id}/log?ref=agentic/T-1")
        mine = next(c for c in page["commits"] if c["subject"] == "feat a")
        assert (mine["agent_name"], mine["task_code"], mine["run_id"]) == (
            "Dev",
            "T-1",
            run["id"],
        )
        base_commit = next(c for c in page["commits"] if c["subject"] == "init")
        assert base_commit["agent_name"] is None
        events = api.get(f"/api/tasks/{task['id']}/events")
        assert any(e["kind"] == "git" and "1 commit(s)" in e["detail"] for e in events)

        # «Deshacer lo que hizo esta ejecución» needs confirming, puts the local branches back and
        # leaves what was pushed.
        refused = httpx.post(f"{server.url}/api/runs/{run['id']}/git/undo", json={}, timeout=30)
        assert refused.status_code == 428
        undone = api.post(f"/api/runs/{run['id']}/git/undo", {"confirm": True})
        (report,) = undone["repos"].values()
        assert {(i["branch"], i["result"]) for i in report["items"]} == {
            ("agentic/T-1", "reverted"),
            ("lateral", "deleted"),
        }
        assert sh(repo, "rev-parse", "agentic/T-1") == base
        assert sh(repo, "branch", "--list", "lateral") == ""
        assert sh(bare, "rev-parse", "agentic/T-1") == found["commits"][0]["sha"]  # pushed: stays
        assert not api.get(f"/api/runs/{run['id']}/git")[0]["can_undo"]
        again = httpx.post(
            f"{server.url}/api/runs/{run['id']}/git/undo", json={"confirm": True}, timeout=30
        )
        assert again.status_code == 409
