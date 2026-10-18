"""The Git tab's API, end to end on real repositories (phase 12, bloque 2)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gitrepos import commit_file, make_bare, make_repo, sh, write

from agentic_os.models import Task, TaskRepo
from agentic_os.services.gitx.backup import BACKUP_REFS


def make_project(client: TestClient, folder: Path, **extra) -> dict:
    response = client.post("/api/projects", json={"name": "Shop", "path": str(folder), **extra})
    assert response.status_code == 201, response.text
    return response.json()


def repo_ids(client: TestClient, project: dict) -> dict[str, str]:
    return {r["name"]: r["id"] for r in client.get(f"/api/projects/{project['id']}/repos").json()}


@pytest.fixture
def shop(client: TestClient, tmp_path: Path) -> tuple[dict, dict[str, str], Path, Path]:
    """A project folder with two repositories: backend and frontend."""
    folder = tmp_path / "shop"
    backend = make_repo(folder / "backend", files={"api.py": "uno\ndos\ntres\n"})
    frontend = make_repo(folder / "frontend")
    project = make_project(client, folder)
    return project, repo_ids(client, project), backend, frontend


def wait_job(client: TestClient, job: dict, seconds: float = 30) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = client.get(f"/api/git/jobs/{job['id']}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


# ------------------------------------------------------------------------------- state
def test_overview_lists_every_repository_with_its_state(client: TestClient, shop):
    project, ids, backend, _frontend = shop
    write(backend, "api.py", "uno\nDOS\ntres\n")
    write(backend, "nuevo.py", "n\n")

    items = client.get(f"/api/projects/{project['id']}/git/overview").json()

    by_name = {i["name"]: i for i in items}
    assert set(by_name) == {"backend", "frontend"}
    assert by_name["backend"]["status"]["branch"] == "main"
    assert not by_name["backend"]["status"]["clean"]
    assert [f["path"] for f in by_name["backend"]["status"]["unstaged"]] == ["api.py", "nuevo.py"]
    assert by_name["frontend"]["status"]["clean"]
    assert by_name["backend"]["repo_id"] == ids["backend"]


def test_overview_survives_a_repository_that_disappears(client: TestClient, shop):
    project, ids, backend, _frontend = shop
    (backend / ".git").rename(backend / ".git-off")
    client.post(f"/api/projects/{project['id']}/repos/scan")

    items = {i["name"]: i for i in client.get(f"/api/projects/{project['id']}/git/overview").json()}

    assert items["backend"]["missing"] and items["backend"]["status"] is None
    assert client.get(f"/api/repos/{ids['backend']}/status").status_code == 409
    assert items["frontend"]["status"]["clean"]


def test_unknown_and_foreign_ids_are_404(client: TestClient, shop):
    assert client.get("/api/repos/nope/status").status_code == 404
    assert client.get("/api/projects/nope/git/overview").status_code == 404
    assert client.get("/api/git/jobs/nope").status_code == 404
    assert client.delete("/api/git/jobs/nope").status_code == 404


def test_branches_know_their_tasks(client: TestClient, shop):
    project, ids, backend, _frontend = shop
    sh(backend, "checkout", "-q", "-b", "agentic/T-7")
    commit_file(backend, "t.py", "t\n")
    sh(backend, "checkout", "-q", "main")
    sh(backend, "branch", "otra")
    with client.app.state.sessionmaker() as db:
        task = Task(
            workspace_id="default",
            number=7,
            project_id=project["id"],
            title="Login",
            branch="agentic/T-7",
            status="review",
        )
        db.add(task)
        db.flush()
        db.add(TaskRepo(task_id=task.id, repo_id=ids["backend"], branch="agentic/T-7"))
        db.commit()

    branches = {b["name"]: b for b in client.get(f"/api/repos/{ids['backend']}/branches").json()}

    assert set(branches) == {"main", "agentic/T-7", "otra"}
    task_branch = branches["agentic/T-7"]
    assert (task_branch["task_code"], task_branch["task_title"], task_branch["task_status"]) == (
        "T-7",
        "Login",
        "review",
    )
    assert task_branch["base_ahead"] == 1 and not task_branch["integrated"]
    assert branches["otra"]["task_code"] is None and branches["otra"]["integrated"]
    assert branches["main"]["current"]


def test_history_commit_detail_and_blame(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    for index in range(1, 6):
        commit_file(backend, f"f{index}.py", f"{index}\n", message=f"commit {index}")
    url = f"/api/repos/{ids['backend']}"

    page = client.get(f"{url}/log", params={"limit": 3}).json()
    assert [c["subject"] for c in page["commits"]] == ["commit 5", "commit 4", "commit 3"]
    assert page["more"]
    rest = client.get(f"{url}/log", params={"skip": 3, "limit": 10}).json()
    assert rest["commits"][-1]["subject"] == "init" and not rest["more"]
    assert client.get(f"{url}/log", params={"grep": "commit 2"}).json()["commits"][0][
        "subject"
    ] == ("commit 2")

    sha = page["commits"][0]["sha"]
    detail = client.get(f"{url}/commits/{sha}").json()
    assert detail["subject"] == "commit 5" and detail["short"] == sha[:7]
    assert client.get(f"{url}/commits/{sha[:8]}").json()["sha"] == sha  # a short sha works
    assert client.get(f"{url}/commits/deadbeef").status_code == 404

    blame = client.get(f"{url}/blame", params={"path": "api.py"}).json()
    assert [(g["start"], g["lines"]) for g in blame] == [(1, 3)]
    assert client.get(f"{url}/blame", params={"path": "../x"}).status_code in (404, 409, 422)


# ------------------------------------------------------------------------------- diffs
def test_diffs_of_the_work_tree_a_commit_and_two_branches(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"
    write(backend, "api.py", "uno\nDOS\ntres\n")
    write(backend, "nuevo.py", "a\nb\n")

    unstaged = client.get(f"{url}/diff", params={"kind": "worktree"}).json()
    files = {f["path"]: f for f in unstaged["repos"][0]["files"]}
    assert set(files) == {"api.py", "nuevo.py"} and files["nuevo.py"]["status"] == "added"
    assert unstaged["repos"][0]["to_ref"]["kind"] == "worktree"
    file_diff = client.get(
        f"{url}/diff/file", params={"kind": "worktree", "path": "nuevo.py"}
    ).json()
    assert [line["text"] for line in file_diff["hunks"][0]["lines"]] == ["a", "b"]

    client.post(f"{url}/stage", json={"paths": ["api.py"]})
    staged = client.get(f"{url}/diff", params={"kind": "worktree", "staged": True}).json()
    assert [f["path"] for f in staged["repos"][0]["files"]] == ["api.py"]

    sha = commit_file(backend, "api.py", "uno\nDOS\ntres\ncuatro\n", message="añade cuatro")
    shown = client.get(f"{url}/diff", params={"kind": "commit", "sha": sha}).json()
    assert shown["repos"][0]["files"][0]["additions"] == 2  # DOS (was staged) and cuatro
    lines = client.get(
        f"{url}/diff/lines",
        params={"kind": "commit", "sha": sha[:7], "path": "api.py", "start": 1, "end": 2},
    ).json()
    assert [line["text"] for line in lines["lines"]] == ["uno", "DOS"]

    sh(backend, "checkout", "-q", "-b", "feature", "HEAD~1")
    commit_file(backend, "f.py", "f\n")
    compared = client.get(
        f"{url}/diff",
        params={"kind": "compare", "from": "main", "to": "feature", "merge_base": True},
    ).json()
    assert [f["path"] for f in compared["repos"][0]["files"]] == ["f.py"]
    bad = client.get(f"{url}/diff", params={"kind": "compare", "from": "main"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "bad_diff_request"
    assert client.get(f"{url}/diff", params={"kind": "commit", "sha": "zzzz"}).status_code == 404


# ------------------------------------------------------------------------------- staging
def test_stage_unstage_and_commit_through_the_api(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"
    write(backend, "api.py", "uno\nDOS\ntres\n")
    write(backend, "nuevo.py", "n\n")

    assert client.post(f"{url}/stage", json={"paths": ["api.py", "nuevo.py"]}).status_code == 204
    assert client.post(f"{url}/unstage", json={"paths": ["nuevo.py"]}).status_code == 204
    status = client.get(f"{url}/status").json()
    assert [f["path"] for f in status["staged"]] == ["api.py"]

    commit = client.post(f"{url}/commit", json={"message": "feat: dos\n\ncon cuerpo"})
    assert commit.status_code == 200, commit.text
    assert commit.json()["subject"] == "feat: dos" and commit.json()["body"] == "con cuerpo"
    assert [f["path"] for f in client.get(f"{url}/status").json()["unstaged"]] == ["nuevo.py"]

    nothing = client.post(f"{url}/commit", json={"message": "otra"})
    assert nothing.status_code == 409 and nothing.json()["detail"]["code"] == "nothing_to_commit"
    empty = client.post(f"{url}/commit", json={"message": ""})
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "empty_message"


def test_paths_that_leave_the_repository_are_refused(client: TestClient, shop):
    _project, ids, _backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"
    for path in ("../fuera", "/etc/passwd", "C:\\Windows", "a/../../b"):
        for action in ("stage", "unstage"):
            assert client.post(f"{url}/{action}", json={"paths": [path]}).status_code == 404, path
        assert (
            client.post(f"{url}/discard", json={"paths": [path], "confirm": True}).status_code
            == 404
        )
    assert client.post(f"{url}/stage", json={"paths": []}).status_code == 422


def test_discard_needs_confirmation_and_keeps_a_backup(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"
    write(backend, "api.py", "perdido\n")
    write(backend, "nuevo.py", "tambien\n")

    refused = client.post(f"{url}/discard", json={"paths": ["api.py", "nuevo.py"]})
    assert (
        refused.status_code == 428 and refused.json()["detail"]["code"] == "confirmation_required"
    )
    assert (backend / "api.py").read_text("utf-8") == "perdido\n"  # nothing happened

    done = client.post(f"{url}/discard", json={"paths": ["api.py", "nuevo.py"], "confirm": True})
    assert done.status_code == 204
    assert (backend / "api.py").read_text("utf-8") == "uno\ndos\ntres\n"
    assert not (backend / "nuevo.py").exists()
    (ref,) = sh(backend, "for-each-ref", "--format=%(refname)", BACKUP_REFS).splitlines()
    assert ref.endswith("-discard")
    # The copy has the lost work: restoring it brings it back.
    assert sh(backend, "show", f"{ref}:api.py") == "perdido"
    assert sh(backend, "show", f"{ref}:nuevo.py") == "tambien"


def test_stage_and_discard_lines_through_the_api(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"
    write(backend, "api.py", "uno\nDOS\ntres\ncuatro\n")  # dos → DOS, and a new line 4

    staged = client.post(
        f"{url}/apply",
        json={"action": "stage", "path": "api.py", "lines": [{"kind": "add", "no": 4}]},
    )
    assert staged.status_code == 204, staged.text
    assert sh(backend, "diff", "--cached", "--unified=0").count("+cuatro") == 1

    needs = client.post(
        f"{url}/apply",
        json={"action": "discard", "path": "api.py", "lines": [{"kind": "add", "no": 2}]},
    )
    assert needs.status_code == 428

    stale = client.post(
        f"{url}/apply",
        json={"action": "stage", "path": "api.py", "lines": [{"kind": "add", "no": 99}]},
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_diff"
    nothing = client.post(f"{url}/apply", json={"action": "stage", "path": "api.py"})
    assert nothing.status_code == 422 and nothing.json()["detail"]["code"] == "nothing_selected"


# ------------------------------------------------------------------------------- branches
def test_branch_operations_through_the_api(client: TestClient, shop):
    _project, ids, backend, _frontend = shop
    url = f"/api/repos/{ids['backend']}"

    assert client.post(f"{url}/branches", json={"name": "feature/x"}).status_code == 204
    assert client.post(f"{url}/branches", json={"name": "otra", "switch": True}).status_code == 204
    assert client.get(f"{url}/status").json()["branch"] == "otra"
    dup = client.post(f"{url}/branches", json={"name": "feature/x"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "branch_exists"
    bad = client.post(f"{url}/branches", json={"name": "no vale .."})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_ref"

    assert client.post(f"{url}/switch", json={"name": "main"}).status_code == 204
    assert (
        client.post(f"{url}/branches/rename", json={"old": "otra", "new": "tercera"}).status_code
        == 204
    )
    commit_file(backend, "x.py", "x\n")
    sh(backend, "checkout", "-q", "tercera")
    commit_file(backend, "t.py", "t\n")
    sh(backend, "checkout", "-q", "main")

    gone = client.post(f"{url}/branches/delete", json={"names": ["feature/x", "tercera"]}).json()
    assert gone["failed"] == {"tercera": "not_merged"}  # feature/x had nothing unmerged
    needs = client.post(f"{url}/branches/delete", json={"names": ["tercera"], "force": True})
    assert needs.status_code == 428
    forced = client.post(
        f"{url}/branches/delete", json={"names": ["tercera"], "force": True, "confirm": True}
    )
    assert forced.json() == {"failed": {}}
    names = {b["name"] for b in client.get(f"{url}/branches").json()}
    assert names == {"main"}


# ------------------------------------------------------------------------------- network
@pytest.fixture
def with_remote(client: TestClient, shop, tmp_path: Path):
    project, ids, backend, frontend = shop
    bare = make_bare(tmp_path / "backend-remote.git")
    sh(backend, "remote", "add", "origin", str(bare))
    sh(backend, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(bare), str(other))
    sh(other, "config", "user.name", "Otro")
    sh(other, "config", "user.email", "otro@example.com")
    sh(other, "config", "core.autocrlf", "false")
    return project, ids, backend, frontend, bare, other


def test_fetch_pull_and_push_as_jobs_with_live_events(client: TestClient, with_remote):
    _project, ids, backend, _frontend, bare, other = with_remote
    url = f"/api/repos/{ids['backend']}"
    commit_file(other, "remoto.py", "r\n")
    sh(other, "push", "-q")

    with client.websocket_connect("/api/git/events") as events:
        job = client.post(f"{url}/fetch", json={})
        assert job.status_code == 202
        done = wait_job(client, job.json())
        assert done["status"] == "succeeded" and done["kind"] == "fetch"
        seen = []
        while True:
            event = events.receive_json()
            seen.append(event["type"])
            if event["type"] == "repo_changed":
                assert event["repo_id"] == ids["backend"]
                break
        assert seen[0] == "job"
    assert client.get(f"{url}/status").json()["behind"] == 1

    pulled = wait_job(client, client.post(f"{url}/pull", json={}).json())
    assert pulled["status"] == "succeeded" and (backend / "remoto.py").exists()

    commit_file(backend, "local.py", "l\n")
    pushed = wait_job(client, client.post(f"{url}/push", json={}).json())
    assert pushed["status"] == "succeeded"
    assert sh(bare, "rev-parse", "main") == sh(backend, "rev-parse", "main")

    sh(backend, "reset", "-q", "--hard", "HEAD~1")
    commit_file(backend, "otro.py", "o\n")
    rejected = wait_job(client, client.post(f"{url}/push", json={}).json())
    assert rejected["status"] == "failed" and rejected["error_code"] == "non_fast_forward"


def test_a_running_job_can_be_cancelled_and_listed(client: TestClient, shop, monkeypatch):
    from agentic_os.services.gitx import remote

    _project, ids, _backend, _frontend = shop
    monkeypatch.setattr(remote, "fetch_args", lambda *a, **k: ["-c", "alias.zz=!sleep 60", "zz"])
    url = f"/api/repos/{ids['backend']}"

    job = client.post(f"{url}/fetch", json={}).json()
    time.sleep(0.5)
    assert [j["id"] for j in client.get(f"{url}/jobs").json()] == [job["id"]]
    assert client.delete(f"/api/git/jobs/{job['id']}").status_code == 204

    assert wait_job(client, job, seconds=15)["status"] == "cancelled"
    assert client.get(f"{url}/jobs").json() == []


def test_push_without_a_remote_says_so(client: TestClient, shop):
    _project, ids, _backend, _frontend = shop
    response = client.post(f"/api/repos/{ids['backend']}/push", json={})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "no_remote"


# ------------------------------------------------------------------------------- several repos
def test_batch_runs_the_action_in_each_repository_on_its_own(client: TestClient, with_remote):
    project, ids, backend, frontend, _bare, _other = with_remote
    url = f"/api/projects/{project['id']}/git/batch"
    write(backend, "b.py", "b\n")
    write(frontend, "f.py", "f\n")
    for name in ("backend", "frontend"):
        client.post(
            f"/api/repos/{ids[name]}/stage",
            json={"paths": ["b.py" if name == "backend" else "f.py"]},
        )

    commits = client.post(
        url, json={"action": "commit", "repo_ids": list(ids.values()), "message": "feat: lote"}
    ).json()
    assert all(item["ok"] and item["sha"] for item in commits)
    assert (
        sh(backend, "log", "-1", "--format=%s")
        == sh(frontend, "log", "-1", "--format=%s")
        == "feat: lote"
    )

    again = client.post(
        url, json={"action": "commit", "repo_ids": list(ids.values()), "message": "otra vez"}
    ).json()
    assert [i["error_code"] for i in again] == ["nothing_to_commit", "nothing_to_commit"]

    created = client.post(
        url, json={"action": "create_branch", "repo_ids": list(ids.values()), "name": "release"}
    ).json()
    assert all(i["ok"] for i in created)
    assert (
        sh(backend, "branch", "--show-current")
        == sh(frontend, "branch", "--show-current")
        == "release"
    )

    # Only the backend has a remote: the frontend's push fails alone.
    pushes = client.post(url, json={"action": "push", "repo_ids": list(ids.values())}).json()
    by_repo = {i["repo_id"]: i for i in pushes}
    assert by_repo[ids["backend"]]["ok"] and by_repo[ids["backend"]]["job"]["kind"] == "push"
    assert (
        not by_repo[ids["frontend"]]["ok"] and by_repo[ids["frontend"]]["error_code"] == "no_remote"
    )
    wait_job(client, by_repo[ids["backend"]]["job"])

    unknown = client.post(url, json={"action": "fetch", "repo_ids": ["nope"]}).json()
    assert unknown[0]["error_code"] == "repo_not_found"
    needs_name = client.post(url, json={"action": "switch", "repo_ids": [ids["backend"]]}).json()
    assert needs_name[0]["error_code"] == "bad_batch"
