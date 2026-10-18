"""Diffs of runs and tasks in projects with several repositories (phase 12, bloque 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gitrepos import make_repo as repo_in
from test_changes import commit, make_run, write
from test_scheduler import db_factory  # noqa: F401 - pytest fixture
from test_worktrees import make_task, sh

from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Agent, Project, ProjectRepo, Task, WorkspaceMode
from agentic_os.services import changes, repos, snapshots
from agentic_os.services.worktrees import Worktrees


def numstat(repo: Path, old: str, new: str) -> set[tuple[str, int, int]]:
    out = sh(repo, "diff", "--numstat", old, new)
    return {
        (path, int(added), int(deleted))
        for added, deleted, path in (line.split("\t") for line in out.splitlines())
    }


def listed(part: changes.RepoChanges) -> set[tuple[str, int, int]]:
    return {(f.path, f.additions, f.deletions) for f in part.files}


def two_repos(tmp_path: Path) -> tuple[Path, Path, Path]:
    folder = tmp_path / "shop"
    return folder, repo_in(folder / "backend"), repo_in(folder / "frontend")


def test_a_worktree_task_shows_one_diff_per_repository(db_factory, tmp_path: Path):  # noqa: F811
    folder, backend, frontend = two_repos(tmp_path)
    worktrees = Worktrees()
    with db_factory() as db:
        project, task = make_task(db, folder)
        work = Path(worktrees.prepare(db, task, project))
        bases = {
            name: sh(repo, "rev-parse", "main")
            for name, repo in (("backend", backend), ("frontend", frontend))
        }

        def dev(_folder: Path) -> None:
            write(work / "backend", "api.py", "def login():\n    return 1\n")
            commit(work / "backend", "feat: login")
            write(work / "frontend", "app.ts", "let a = 1\nlet b = 2\n")  # left uncommitted

        run = make_run(db, project, work, task)
        starts = {
            r.name: snapshots.take(str(work / r.name), run.id, "start").sha
            for r in repos.active(db, project)
        }
        dev(work)
        ends = {
            r.name: snapshots.take(str(work / r.name), run.id, "end").sha
            for r in repos.active(db, project)
        }
        from agentic_os.models import RunRepo

        for repo in repos.active(db, project):
            db.add(
                RunRepo(
                    run_id=run.id,
                    repo_id=repo.id,
                    repo_name=repo.name,
                    path=str(work / repo.name),
                    snapshot_start=starts[repo.name],
                    snapshot_end=ends[repo.name],
                )
            )
        db.flush()
        worktrees.release(db, task, project)  # commits the leftovers and removes the folders
        assert not work.exists()

        result = changes.task_changes(db, task)

        assert result.state == "ok"
        by_name = {part.name: part for part in result.repos}
        assert set(by_name) == {"backend", "frontend"}
        assert listed(by_name["backend"]) == numstat(backend, bases["backend"], "agentic/T-1")
        assert listed(by_name["frontend"]) == numstat(frontend, bases["frontend"], "agentic/T-1")
        assert (result.totals.files, result.totals.additions) == (2, 4)
        assert all(part.from_ref.kind == "base" for part in result.repos)

        per_run = changes.run_changes(db, run)
        assert {p.name: listed(p) for p in per_run.repos} == {
            "backend": {("api.py", 2, 0)},
            "frontend": {("app.ts", 2, 0)},
        }


def test_a_repository_the_task_did_not_touch_is_not_listed(db_factory, tmp_path: Path):  # noqa: F811
    folder, _backend, _frontend = two_repos(tmp_path)
    repo_in(folder / "docs")
    with db_factory() as db:
        project, task = make_task(db, folder)
        worktrees = Worktrees()
        work = Path(worktrees.prepare(db, task, project))
        write(work / "backend", "api.py", "x\n")
        worktrees.release(db, task, project)
        # docs and frontend got no commits: their branches are gone and so are their rows.
        result = changes.task_changes(db, task)
        assert [part.name for part in result.repos] == ["backend"]


def test_pick_chooses_the_repository_of_a_file_request(db_factory, tmp_path: Path):  # noqa: F811
    folder, _backend, _frontend = two_repos(tmp_path)
    with db_factory() as db:
        project, task = make_task(db, folder)
        project.workspace_mode = WorkspaceMode.DIRECT
        run = make_run(db, project, folder, task)
        ranges = changes.run_ranges(db, run)
        assert len(ranges) == 1 and ranges[0].state == "no_snapshots"  # no rows: before the phase

        fake = [changes.Range("ok", key="a", name="backend"), changes.Range("ok", key="b")]
        assert changes.pick(fake, "b").key == "b"
        with pytest.raises(ApiError) as several:
            changes.pick(fake, None)
        assert several.value.code == "repo_required"
        with pytest.raises(NotFound):
            changes.pick(fake, "zzz")
        assert changes.pick(fake[:1], None).key == "a"  # one repository needs no key


def test_the_snapshot_of_a_repository_leaves_out_the_ones_inside_it(tmp_path: Path):
    root = repo_in(tmp_path / "mono")
    repo_in(root / "tools" / "cli")
    write(root, "src/app.py", "x = 1\n")

    plain = snapshots.take(str(root))
    excluded = snapshots.take(str(root), exclude=["tools/cli"])

    def files(sha: str) -> set[str]:
        return set(sh(root, "ls-tree", "-r", "--name-only", sha).splitlines())

    assert plain is not None and excluded is not None
    assert "tools/cli" in sh(root, "ls-tree", "-r", plain.sha)  # taken for a submodule
    assert files(excluded.sha) == {"README.md", "src/app.py"}


def test_api_changes_of_a_run_with_two_repositories(client: TestClient, tmp_path: Path):
    client.post("/api/scheduler/pause")
    folder, backend, frontend = two_repos(tmp_path)
    project_id = client.post("/api/projects", json={"name": "Shop", "path": str(folder)}).json()[
        "id"
    ]
    agent_id = client.post("/api/agents", json={"name": "Dev"}).json()["id"]
    task_id = client.post(
        "/api/tasks", json={"project_id": project_id, "agent_id": agent_id, "title": "Login"}
    ).json()["id"]

    with client.app.state.sessionmaker() as db:
        project, task = db.get(Project, project_id), db.get(Task, task_id)
        run = make_run(db, project, folder, task)
        run.agent_id = db.get(Agent, agent_id).id
        from agentic_os.models import RunRepo

        for repo in repos.active(db, project):
            start = snapshots.take(repo.path, run.id, "start")
            write(Path(repo.path), f"{repo.name}.txt", "1\n2\n3\n")
            end = snapshots.take(repo.path, run.id, "end")
            db.add(
                RunRepo(
                    run_id=run.id,
                    repo_id=repo.id,
                    repo_name=repo.name,
                    path=repo.path,
                    snapshot_start=start.sha,
                    snapshot_end=end.sha,
                )
            )
        db.commit()
        run_id = run.id
        ids = {r.name: r.id for r in db.query(ProjectRepo).filter_by(project_id=project_id)}

    body = client.get(f"/api/runs/{run_id}/changes").json()
    assert body["state"] == "ok"
    assert body["totals"] == {"files": 2, "additions": 6, "deletions": 0}
    assert [r["name"] for r in body["repos"]] == ["backend", "frontend"]
    assert [f["path"] for f in body["repos"][1]["files"]] == ["frontend.txt"]

    asked = client.get(f"/api/runs/{run_id}/changes/file", params={"path": "frontend.txt"})
    assert asked.status_code == 422 and asked.json()["detail"]["code"] == "repo_required"
    diff = client.get(
        f"/api/runs/{run_id}/changes/file",
        params={"path": "frontend.txt", "repo": ids["frontend"]},
    ).json()
    assert [line["text"] for line in diff["hunks"][0]["lines"]] == ["1", "2", "3"]
    # A file of the other repository is not found in this one.
    wrong = client.get(
        f"/api/runs/{run_id}/changes/file",
        params={"path": "backend.txt", "repo": ids["frontend"]},
    )
    assert wrong.status_code == 404
    assert (backend / "backend.txt").exists() and (frontend / "frontend.txt").exists()
    assert sh(backend, "status", "--porcelain")  # the snapshots left the real work alone
