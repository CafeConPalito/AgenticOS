"""Merge, rebase, conflicts and undo through the API (phase 12, bloque 3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gitrepos import commit_file, make_repo, sh, write
from test_git_api import make_project, repo_ids


@pytest.fixture
def web(client: TestClient, tmp_path: Path) -> tuple[str, Path]:
    """One repository with `main`, a `feature` branch of two commits and a `clash` branch."""
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    sh(path, "checkout", "-q", "-b", "feature")
    commit_file(path, "f1.txt", "1\n", message="feature 1")
    commit_file(path, "f2.txt", "2\n", message="feature 2")
    sh(path, "checkout", "-q", "-b", "clash", "main")
    commit_file(path, "a.txt", "clash\n", message="clash edit")
    sh(path, "checkout", "-q", "main")
    project = make_project(client, path)
    return repo_ids(client, project)[path.name], path


def post(client: TestClient, repo: str, route: str, **body):
    return client.post(f"/api/repos/{repo}/{route}", json=body)


def operations(client: TestClient, repo: str) -> list[dict]:
    return client.get(f"/api/repos/{repo}/operations").json()


def test_merge_through_the_api_and_undo_it(client: TestClient, web):
    repo, path = web
    commit_file(path, "m.txt", "m\n", message="main moves")
    before = sh(path, "rev-parse", "main")

    done = post(client, repo, "merge", ref="feature", message="Merge de feature")
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert sh(path, "log", "-1", "--format=%s") == "Merge de feature"

    (entry,) = operations(client, repo)
    assert (entry["kind"], entry["label"], entry["blocked_by"]) == (
        "merge",
        "Merge de feature",
        None,
    )
    assert not entry["lost_files"] and not entry["in_progress"]

    assert client.post(f"/api/repos/{repo}/operations/{entry['id']}/undo").status_code == 204
    assert sh(path, "rev-parse", "main") == before and not (path / "f1.txt").exists()
    (after,) = operations(client, repo)
    assert after["undone"] and after["blocked_by"] == "already_undone"
    again = client.post(f"/api/repos/{repo}/operations/{entry['id']}/undo")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "not_the_last"


def test_a_merge_with_nothing_new_leaves_no_entry(client: TestClient, web):
    repo, _path = web
    post(client, repo, "merge", ref="feature", mode="ff")
    again = post(client, repo, "merge", ref="feature", mode="no_ff")

    assert again.json()["status"] == "up_to_date"
    assert len(operations(client, repo)) == 1  # only the first one


def test_conflicts_are_resolved_through_the_api(client: TestClient, web):
    repo, path = web
    commit_file(path, "a.txt", "main\n", message="main edit")

    stopped = post(client, repo, "merge", ref="clash")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "conflicts" and stopped.json()["conflicts"] == ["a.txt"]
    status = client.get(f"/api/repos/{repo}/status").json()
    assert status["operation"] == "merge" and [f["path"] for f in status["conflicts"]] == ["a.txt"]
    (open_entry,) = operations(client, repo)
    assert open_entry["in_progress"] and open_entry["blocked_by"] == "operation_in_progress"

    detail = client.get(f"/api/repos/{repo}/conflicts/file", params={"path": "a.txt"}).json()
    assert (detail["base"], detail["ours"], detail["theirs"]) == ("base\n", "main\n", "clash\n")
    early = client.post(f"/api/repos/{repo}/operation/continue")
    assert early.status_code == 409 and early.json()["detail"]["code"] == "conflicts_unresolved"

    resolved = post(client, repo, "conflicts/resolve", path="a.txt", content="main + clash\n")
    assert resolved.status_code == 204
    done = client.post(f"/api/repos/{repo}/operation/continue")
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert (path / "a.txt").read_text("utf-8") == "main + clash\n"

    (entry,) = operations(client, repo)
    assert not entry["in_progress"] and entry["blocked_by"] is None  # now it can be undone


def test_aborting_a_conflict_leaves_nothing_to_undo(client: TestClient, web):
    repo, path = web
    commit_file(path, "a.txt", "main\n", message="main edit")
    head = sh(path, "rev-parse", "HEAD")
    post(client, repo, "merge", ref="clash")

    aborted = client.post(f"/api/repos/{repo}/operation/abort")

    assert aborted.status_code == 200 and sh(path, "rev-parse", "HEAD") == head
    assert operations(client, repo) == []
    nothing = client.post(f"/api/repos/{repo}/operation/abort")
    assert nothing.status_code == 409 and nothing.json()["detail"]["code"] == "no_operation"


def test_taking_a_side_and_the_conflict_guards(client: TestClient, web):
    repo, path = web
    commit_file(path, "a.txt", "main\n", message="main edit")
    post(client, repo, "merge", ref="clash")

    clean = client.get(f"/api/repos/{repo}/conflicts/file", params={"path": "README.md"})
    assert clean.status_code == 404 and clean.json()["detail"]["code"] == "not_conflicted"
    outside = post(client, repo, "conflicts/resolve", path="../fuera", content="x")
    assert outside.status_code == 404

    assert post(client, repo, "conflicts/take", path="a.txt", side="theirs").status_code == 204
    assert (path / "a.txt").read_text("utf-8") == "clash\n"
    assert client.post(f"/api/repos/{repo}/operation/continue").json()["status"] == "done"


def test_rebase_cherry_pick_and_revert_through_the_api(client: TestClient, web):
    repo, path = web
    commit_file(path, "m.txt", "m\n", message="main moves")
    sha = sh(path, "rev-parse", "feature~1")

    picked = post(client, repo, "cherry-pick", shas=[sha[:8]])
    assert picked.json()["status"] == "done" and (path / "f1.txt").exists()
    reverted = post(client, repo, "revert", shas=["HEAD"])
    assert reverted.json()["status"] == "done" and not (path / "f1.txt").exists()
    bad = post(client, repo, "cherry-pick", shas=["nope"])
    assert bad.status_code == 404

    sh(path, "checkout", "-q", "feature")
    rebased = post(client, repo, "rebase", onto="main")
    assert rebased.json()["status"] == "done"
    # `feature 1` was already in main (picked), so git leaves it out of the replay.
    assert sh(path, "log", "--format=%s", "-1") == "feature 2"
    kinds = [o["kind"] for o in operations(client, repo)]
    assert kinds == ["rebase", "revert", "cherry-pick"]  # newest first


def test_reset_hard_needs_confirmation_and_can_be_undone(client: TestClient, web):
    repo, path = web
    write(path, "a.txt", "work in progress\n")
    head = sh(path, "rev-parse", "HEAD")
    commit_file(path, "b.txt", "b\n", message="one more")
    write(path, "b.txt", "b\nunsaved\n")

    refused = post(client, repo, "reset", ref=head, mode="hard")
    assert refused.status_code == 428 and (path / "b.txt").exists()

    done = post(client, repo, "reset", ref=head, mode="hard", confirm=True)
    assert done.status_code == 200 and not (path / "b.txt").exists()
    (entry,) = operations(client, repo)
    assert entry["lost_files"]

    assert client.post(f"/api/repos/{repo}/operations/{entry['id']}/undo").status_code == 204
    assert (path / "b.txt").read_text("utf-8") == "b\nunsaved\n"
    assert sh(path, "log", "-1", "--format=%s") == "one more"


def test_discard_and_branch_deletes_and_amend_can_be_undone(client: TestClient, web):
    repo, path = web
    write(path, "a.txt", "precious\n")
    assert post(client, repo, "discard", paths=["a.txt"], confirm=True).status_code == 204
    assert (path / "a.txt").read_text("utf-8") == "base\n"
    (discard,) = operations(client, repo)
    assert discard["kind"] == "discard" and discard["lost_files"]
    client.post(f"/api/repos/{repo}/operations/{discard['id']}/undo")
    assert (path / "a.txt").read_text("utf-8") == "precious\n"

    sh(path, "checkout", "--", "a.txt")
    feature = sh(path, "rev-parse", "feature")
    gone = post(client, repo, "branches/delete", names=["feature"], force=True, confirm=True)
    assert gone.json() == {"failed": {}}
    top = operations(client, repo)[0]
    assert top["kind"] == "delete_branch"
    client.post(f"/api/repos/{repo}/operations/{top['id']}/undo")
    assert sh(path, "rev-parse", "feature") == feature

    old = sh(path, "rev-parse", "HEAD")
    reworded = post(client, repo, "commit", message="otro mensaje", amend=True)
    assert reworded.status_code == 200 and sh(path, "rev-parse", "HEAD") != old
    last = operations(client, repo)[0]
    assert last["kind"] == "amend"
    client.post(f"/api/repos/{repo}/operations/{last['id']}/undo")
    assert sh(path, "rev-parse", "HEAD") == old


def test_only_the_last_operation_can_be_undone_and_not_after_new_work(client: TestClient, web):
    repo, path = web
    post(client, repo, "merge", ref="feature", mode="ff")
    first = operations(client, repo)[0]
    sh(path, "checkout", "-q", "clash")
    post(client, repo, "rebase", onto="main")
    second = operations(client, repo)[0]

    not_last = client.post(f"/api/repos/{repo}/operations/{first['id']}/undo")
    assert not_last.status_code == 409 and not_last.json()["detail"]["code"] == "not_the_last"
    listed = {o["id"]: o for o in operations(client, repo)}
    assert listed[first["id"]]["blocked_by"] == "not_the_last"
    assert listed[second["id"]]["blocked_by"] is None

    commit_file(path, "later.txt", "l\n", message="new work")
    moved = client.post(f"/api/repos/{repo}/operations/{second['id']}/undo")
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "moved_since"
    assert (path / "later.txt").exists()
    assert client.post(f"/api/repos/{repo}/operations/nope/undo").status_code == 404


def test_interactive_rebase_through_the_api(client: TestClient, web):
    repo, path = web
    sh(path, "checkout", "-q", "feature")
    plan = client.get(f"/api/repos/{repo}/rebase/plan", params={"base": "main"}).json()
    assert [c["subject"] for c in plan] == ["feature 1", "feature 2"]
    first, second = (c["sha"] for c in plan)

    done = post(
        client,
        repo,
        "rebase/interactive",
        base="main",
        items=[
            {"action": "pick", "sha": second},
            {"action": "reword", "sha": first, "message": "feature uno"},
        ],
    )

    assert done.status_code == 200 and done.json()["status"] == "done"
    assert sh(path, "log", "--format=%s", "-2").splitlines() == ["feature uno", "feature 2"]
    stale = post(
        client, repo, "rebase/interactive", base="main", items=[{"action": "pick", "sha": first}]
    )
    assert stale.status_code in (409, 422)
    assert client.get(f"/api/repos/{repo}/rebase/plan").status_code == 422  # base is required
