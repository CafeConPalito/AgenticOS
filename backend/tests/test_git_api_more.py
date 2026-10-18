"""Stash, tags, remotes, submodules, LFS, worktrees, upkeep, settings and cloning through the API
(phase 12, bloque 4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gitrepos import make_bare, make_repo, sh, write
from test_git_api import make_project, repo_ids, wait_job


@pytest.fixture
def web(client: TestClient, tmp_path: Path) -> tuple[str, Path, dict]:
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    project = make_project(client, path)
    return repo_ids(client, project)[path.name], path, project


def url(repo: str, route: str) -> str:
    return f"/api/repos/{repo}/{route}"


# ------------------------------------------------------------------------------- stash
def test_stash_through_the_api(client: TestClient, web):
    repo, path, _project = web
    write(path, "a.txt", "changed\n")
    write(path, "nuevo.txt", "n\n")

    pushed = client.post(url(repo, "stashes"), json={"message": "mi trabajo"})
    assert pushed.json() == {"stored": True} and (path / "a.txt").read_text("utf-8") == "base\n"
    nothing = client.post(url(repo, "stashes"), json={})
    assert nothing.json() == {"stored": False}

    (entry,) = client.get(url(repo, "stashes")).json()
    assert entry["ref"] == "stash@{0}" and "mi trabajo" in entry["message"]
    diff = client.get(url(repo, "stashes/diff"), params={"ref": entry["ref"]}).json()
    assert {f["path"] for f in diff["repos"][0]["files"]} == {"a.txt"}
    assert entry["has_untracked"]  # nuevo.txt lives in the stash's third parent
    extra = client.get(url(repo, "diff"), params={"kind": "commit", "sha": f"{entry['sha']}^3"})
    assert {f["path"] for f in extra.json()["repos"][0]["files"]} == {"nuevo.txt"}

    applied = client.post(url(repo, "stashes/apply"), json={"ref": entry["ref"]})
    assert applied.json()["status"] == "done" and (path / "nuevo.txt").exists()
    refused = client.post(url(repo, "stashes/drop"), json={"ref": entry["ref"]})
    assert refused.status_code == 428
    dropped = client.post(url(repo, "stashes/drop"), json={"ref": entry["ref"], "confirm": True})
    assert dropped.status_code == 204 and client.get(url(repo, "stashes")).json() == []
    ghost = client.post(url(repo, "stashes/apply"), json={"ref": "stash@{9}"})
    assert ghost.status_code == 404


def test_a_stash_into_a_branch(client: TestClient, web):
    repo, path, _project = web
    write(path, "a.txt", "changed\n")
    client.post(url(repo, "stashes"), json={})

    done = client.post(url(repo, "stashes/branch"), json={"ref": "stash@{0}", "name": "wip"})

    assert done.status_code == 204
    assert client.get(url(repo, "status")).json()["branch"] == "wip"


# ------------------------------------------------------------------------------- tags
def test_tags_through_the_api(client: TestClient, web, tmp_path: Path):
    repo, path, _project = web
    bare = make_bare(tmp_path / "remote.git")
    sh(path, "remote", "add", "origin", str(bare))
    sh(path, "push", "-q", "-u", "origin", "main")

    assert (
        client.post(url(repo, "tags"), json={"name": "v1", "message": "primera"}).status_code == 204
    )
    dup = client.post(url(repo, "tags"), json={"name": "v1"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "tag_exists"
    (tag,) = client.get(url(repo, "tags")).json()
    assert tag["name"] == "v1" and tag["annotated"] and tag["message"] == "primera"

    job = client.post(url(repo, "tags/remote"), json={"name": "v1"})
    assert job.status_code == 202 and wait_job(client, job.json())["status"] == "succeeded"
    assert sh(bare, "tag") == "v1"
    gone = client.post(url(repo, "tags/remote"), json={"name": "v1", "delete": True})
    assert wait_job(client, gone.json())["status"] == "succeeded" and sh(bare, "tag") == ""

    assert client.delete(url(repo, "tags/v1")).status_code == 204
    assert client.get(url(repo, "tags")).json() == []


# ------------------------------------------------------------------------------- remotes
def test_remotes_and_the_forced_push(client: TestClient, web, tmp_path: Path):
    repo, path, _project = web
    bare = make_bare(tmp_path / "remote.git")

    added = client.post(url(repo, "remotes"), json={"name": "origin", "url": str(bare)})
    assert added.status_code == 204
    bad = client.post(url(repo, "remotes"), json={"name": "x y", "url": str(bare)})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_remote"
    evil = client.post(url(repo, "remotes"), json={"name": "evil", "url": "--upload-pack=calc"})
    assert evil.status_code == 422 and evil.json()["detail"]["code"] == "invalid_url"
    assert client.post(url(repo, "remotes/origin/test")).json()["ok"] is True

    assert wait_job(client, client.post(url(repo, "push"), json={}).json())["status"] == "succeeded"
    sh(path, "commit", "-q", "--amend", "-m", "rewritten")
    rejected = wait_job(client, client.post(url(repo, "push"), json={}).json())
    assert rejected["error_code"] == "non_fast_forward"

    lost = client.get(url(repo, "push/overwrites")).json()
    assert len(lost) == 1 and lost[0].endswith("init")
    needs = client.post(url(repo, "push/force"), json={})
    assert needs.status_code == 428
    forced = client.post(url(repo, "push/force"), json={"confirm": True})
    assert forced.status_code == 202 and wait_job(client, forced.json())["status"] == "succeeded"
    assert sh(bare, "rev-parse", "main") == sh(path, "rev-parse", "main")

    renamed = client.patch(url(repo, "remotes/origin"), json={"rename_to": "upstream"})
    assert renamed.status_code == 204
    assert [r["name"] for r in client.get(url(repo, "remotes")).json()] == ["upstream"]
    assert client.delete(url(repo, "remotes/upstream")).status_code == 204


# ------------------------------------------------------------------------------- submodules
def test_submodules_through_the_api(client: TestClient, web, tmp_path: Path):
    repo, path, _project = web
    library = make_repo(tmp_path / "library", files={"lib.py": "x = 1\n"})

    added = client.post(url(repo, "submodules"), json={"url": str(library), "path": "vendor/lib"})
    assert added.status_code == 204, added.text
    (item,) = client.get(url(repo, "submodules")).json()
    assert item["path"] == "vendor/lib" and item["state"] == "ok"

    bad = client.post(url(repo, "submodules"), json={"url": str(library), "path": "../fuera"})
    assert bad.status_code == 404  # the path leaves the repository

    refused = client.post(url(repo, "submodules/remove"), json={"path": "vendor/lib"})
    assert refused.status_code == 428
    done = client.post(url(repo, "submodules/remove"), json={"path": "vendor/lib", "confirm": True})
    assert done.status_code == 204 and client.get(url(repo, "submodules")).json() == []
    assert not (path / "vendor" / "lib").exists()


# ------------------------------------------------------------------------------- lfs, worktrees
def test_lfs_and_worktrees_through_the_api(client: TestClient, web, tmp_path: Path):
    repo, path, _project = web
    state = client.get(url(repo, "lfs")).json()
    assert state["used"] is False and state["patterns"] == []
    write(path, ".gitattributes", "*.psd filter=lfs diff=lfs merge=lfs -text\n")
    assert client.get(url(repo, "lfs")).json()["patterns"] == ["*.psd"]

    other = tmp_path / "web.wt" / "T-1"
    sh(path, "worktree", "add", "-q", "-b", "agentic/T-1", str(other))
    listed = client.get(url(repo, "worktrees")).json()
    assert [(w["main"], w["task"], w["branch"]) for w in listed] == [
        (True, False, "main"),
        (False, True, "agentic/T-1"),
    ]
    main = client.post(url(repo, "worktrees/remove"), json={"path": str(path)})
    assert main.status_code == 422 and main.json()["detail"]["code"] == "bad_worktree"
    assert client.post(url(repo, "worktrees/remove"), json={"path": str(other)}).status_code == 204
    assert client.post(url(repo, "worktrees/prune")).status_code == 204
    assert len(client.get(url(repo, "worktrees")).json()) == 1


# ------------------------------------------------------------------------------- upkeep
def test_clean_needs_confirmation_and_can_be_undone(client: TestClient, web):
    repo, path, _project = web
    write(path, "scratch.txt", "precioso\n")
    write(path, "carpeta/dentro.txt", "y\n")

    preview = client.get(url(repo, "clean/preview")).json()
    assert preview["files"] == ["scratch.txt"] and preview["folders"] == ["carpeta/"]
    body = {"paths": ["scratch.txt", "carpeta/"]}
    assert client.post(url(repo, "clean"), json=body).status_code == 428
    assert (path / "scratch.txt").exists()

    assert client.post(url(repo, "clean"), json={**body, "confirm": True}).status_code == 204
    assert not (path / "scratch.txt").exists() and not (path / "carpeta").exists()
    (entry,) = client.get(url(repo, "operations")).json()
    assert entry["kind"] == "clean" and entry["lost_files"]

    assert client.post(url(repo, f"operations/{entry['id']}/undo")).status_code == 204
    assert (path / "scratch.txt").read_text("utf-8") == "precioso\n"
    assert (path / "carpeta" / "dentro.txt").exists()


def test_gc_verify_and_size(client: TestClient, web):
    repo, _path, _project = web
    done = wait_job(client, client.post(url(repo, "gc")).json())
    assert done["status"] == "succeeded" and done["kind"] == "gc"
    assert client.get(url(repo, "verify")).json() == {"ok": True, "problems": []}
    assert set(client.get(url(repo, "size")).json()) == {"loose", "packed", "garbage"}


# ------------------------------------------------------------------------------- settings
def test_settings_through_the_api(client: TestClient, web, tmp_path: Path, monkeypatch):
    repo, _path, _project = web
    home = tmp_path / "gitconfig"
    home.write_text("", "utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home))

    put = client.put(
        "/api/git/config", json={"scope": "global", "key": "user.name", "value": "Ana"}
    )
    assert put.status_code == 204
    local = client.put(
        url(repo, "config"), json={"scope": "local", "key": "pull.rebase", "value": "true"}
    )
    assert local.status_code == 204

    shown = client.get(url(repo, "config")).json()
    assert shown["user.name"]["global"] == "Ana" and shown["pull.rebase"]["local"] == "true"
    assert client.get("/api/git/config").json()["user.name"] == {"global": "Ana"}
    keys = {e["key"] for e in client.get(url(repo, "config/all")).json()}
    assert "pull.rebase" in keys

    refused = client.put(
        url(repo, "config"), json={"scope": "local", "key": "core.editor", "value": "calc"}
    )
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "forbidden_key"
    unset = client.put(url(repo, "config"), json={"scope": "local", "key": "pull.rebase"})
    assert (
        unset.status_code == 204
        and client.get(url(repo, "config")).json()["pull.rebase"]["local"] is None
    )


# ------------------------------------------------------------------------------- clone, init
def test_clone_and_init_through_the_api(client: TestClient, tmp_path: Path):
    source = make_repo(tmp_path / "source", files={"README.md": "hi\n"})
    parent = tmp_path / "projects"
    parent.mkdir()

    started = client.post("/api/git/clone", json={"url": str(source), "parent_folder": str(parent)})
    assert started.status_code == 202
    body = started.json()
    assert body["path"] == str(parent / "source")
    assert wait_job(client, body["job"])["status"] == "succeeded"
    assert (parent / "source" / "README.md").exists()
    again = client.post("/api/git/clone", json={"url": str(source), "parent_folder": str(parent)})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "folder_exists"

    folder = tmp_path / "nuevo"
    folder.mkdir()
    project = make_project(client, folder)
    assert client.get(f"/api/projects/{project['id']}/repos").json() == []
    init = client.post(f"/api/projects/{project['id']}/repos/init", json={"branch": "develop"})
    assert init.status_code == 200
    repos = client.get(f"/api/projects/{project['id']}/repos").json()
    assert [(r["rel_path"], r["base_branch"]) for r in repos] == [("", "develop")]
    twice = client.post(f"/api/projects/{project['id']}/repos/init", json={})
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "repo_exists"


# ------------------------------------------------------------------------------- terminal
def test_a_terminal_in_the_repository_folder(client: TestClient, web):
    repo, path, _project = web
    opened = client.post(url(repo, "shell"))
    assert opened.status_code == 201
    shell_id = opened.json()["shell_id"]

    with client.websocket_connect(f"/api/git/shells/{shell_id}/terminal?client_id=t1") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        assert socket.receive_json()["type"] == "state"
        socket.send_json(
            {"type": "input", "data": "git rev-parse --show-toplevel; echo FIN-$((6*7))\r"}
        )
        seen = ""
        for _ in range(200):
            message = socket.receive_json()
            if message["type"] == "output":
                seen += message["data"]
            if "FIN-42" in seen:
                break
        assert "FIN-42" in seen
        assert path.name in seen  # it started in the repository's folder

    assert client.delete(f"/api/git/shells/{shell_id}").status_code == 204
    gone = client.post(url(repo, "shell"))
    assert gone.status_code == 201  # a slot is free again
    client.delete(f"/api/git/shells/{gone.json()['shell_id']}")


def test_only_a_few_terminals_can_be_open_at_once(client: TestClient, web):
    repo, _path, _project = web
    ids = [client.post(url(repo, "shell")).json()["shell_id"] for _ in range(4)]

    fifth = client.post(url(repo, "shell"))

    assert fifth.status_code == 409 and fifth.json()["detail"]["code"] == "too_many_terminals"
    for shell_id in ids:
        client.delete(f"/api/git/shells/{shell_id}")
