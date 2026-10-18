"""Fixes from the code review of the agents block (phase 12, block 7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from gitrepos import commit_file, make_bare, make_repo, sh
from test_git_api import make_project, repo_ids

from agentic_os.models import ProjectRepo
from agentic_os.services.gitx import activity
from agentic_os.services.gitx.runner import Repo


def window() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(seconds=30), now + timedelta(seconds=30)


@pytest.fixture
def web(tmp_path: Path) -> Path:
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    bare = make_bare(tmp_path / "remote.git")
    sh(path, "remote", "add", "origin", str(bare))
    sh(path, "push", "-q", "-u", "origin", "main")
    return path


def fake_run() -> SimpleNamespace:
    return SimpleNamespace(id="run-1", task_id=None, agent_id=None, agent_name="Dev")


def test_a_fast_forward_brings_a_commit_that_is_not_the_runs(web: Path):
    """Merging somebody else's branch moves HEAD to their commit: it is not the agent's."""
    sh(web, "checkout", "-q", "-b", "theirs")
    commit_file(web, "t.txt", "t\n", message="somebody's work")
    sh(web, "checkout", "-q", "main")
    repo = Repo(str(web))
    before = activity.snapshot(repo)
    since, until = window()

    sh(web, "merge", "-q", "--ff-only", "theirs")

    found = activity.collect(repo, before, since, until)
    assert found.commits == []
    assert found.branches == []  # main moved, but with no commit of the run in it


def test_the_same_commit_twice_is_recorded_once(client: TestClient, tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    rid = repo_ids(client, make_project(client, path))[path.name]
    repo = Repo(str(path))
    before = activity.snapshot(repo)
    since, until = window()
    sh(path, "checkout", "-q", "-b", "feature")
    commit_file(path, "f.txt", "1\n", message="feature")
    sh(path, "checkout", "-q", "main")
    sh(path, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")

    found = activity.collect(repo, before, since, until)
    shas = [c.sha for c in found.commits]
    assert len(shas) == len(set(shas)) == 2  # the feature commit and the merge commit

    # Even a list that repeats one cannot break the unique (repository, commit) pair.
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        repeated = [*found.commits, found.commits[0]]
        added = activity.attribute(db, rid, fake_run(), repeated, None)  # type: ignore[arg-type]
        db.commit()
    assert added == 2


def test_a_branch_that_moved_without_a_commit_of_the_run_is_not_attributed(web: Path):
    """A reset could be anybody's: undoing it would reset somebody else's work."""
    commit_file(web, "p.txt", "p\n", message="the person, before")
    repo = Repo(str(web))
    before = activity.snapshot(repo)
    since, until = window()
    sh(web, "reset", "-q", "--hard", "HEAD~1")
    assert activity.collect(repo, before, since, until).branches == []


def test_undoing_twice_finds_everything_already_done(client: TestClient, tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    rid = repo_ids(client, make_project(client, path))[path.name]
    sh(path, "branch", "work")
    repo = Repo(str(path))
    before = activity.snapshot(repo)
    since, until = window()
    sh(path, "checkout", "-q", "work")
    commit_file(path, "w.txt", "w\n", message="work")
    sh(path, "branch", "extra")
    sh(path, "checkout", "-q", "main")
    found = activity.collect(repo, before, since, until)

    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(ProjectRepo, rid)
        activity.undo(db, row, repo, found)  # type: ignore[arg-type]
        again = activity.undo(db, row, repo, found)  # type: ignore[arg-type]
        db.commit()
    assert {(i.branch, i.result, i.reason) for i in again.items} == {
        ("work", "reverted", "already"),
        ("extra", "deleted", "already"),
    }
    assert all(i.result != "skipped" for i in again.items)  # so the run counts as undone


def test_attributions_are_looked_up_in_chunks(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = make_repo(tmp_path / "web")
    rid = repo_ids(client, make_project(client, path))[path.name]
    shas = [f"{n:040x}" for n in range(1, 8)]
    monkeypatch.setattr(activity, "CHUNK", 3)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        commits = [activity.RunCommit(sha=s, subject="x", kind="commit") for s in shas]
        activity.attribute(db, rid, fake_run(), commits, None)  # type: ignore[arg-type]
        db.commit()
        assert set(activity.attributions(db, rid, [*shas, "f" * 40])) == set(shas)


def test_undoing_a_run_checks_every_repository_before_touching_any(
    client: TestClient, tmp_path: Path
):
    """A missing repository must not leave the others half undone."""
    from agentic_os.models import RunRepo

    folder = tmp_path / "shop"
    backend = make_repo(folder / "backend")
    make_repo(folder / "frontend")
    ids = repo_ids(client, make_project(client, folder))
    sh(backend, "branch", "work")
    repo = Repo(str(backend))
    before = activity.snapshot(repo)
    since, until = window()
    sh(backend, "checkout", "-q", "work")
    commit_file(backend, "w.txt", "w\n", message="work")
    sh(backend, "checkout", "-q", "main")
    found = activity.collect(repo, before, since, until)
    other = activity.Activity(
        branches=[activity.BranchMove(name="x", start="a" * 40, end="b" * 40)]
    )

    from agentic_os.models import Run
    from agentic_os.models.run import RunStatus

    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        run = Run(
            workspace_id="default",
            agent_name="Dev",
            agent_color="#fff",
            project_name="Shop",
            cli="claude",
            prompt="p",
            cwd=str(folder),
            status=RunStatus.EXITED,
        )
        db.add(run)
        db.flush()
        for name, data in (("backend", found), ("frontend", other)):
            db.add(
                RunRepo(
                    run_id=run.id,
                    repo_id=ids[name],
                    repo_name=name,
                    path=str(folder / name),
                    activity=data.model_dump(),
                )
            )
        db.commit()
        run_id = run.id
    (folder / "frontend" / ".git").rename(folder / "frontend" / "gone")  # not a repository now
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(ProjectRepo, ids["frontend"]).missing = True  # type: ignore[union-attr]
        db.commit()

    response = client.post(f"/api/runs/{run_id}/git/undo", json={"confirm": True})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "repo_missing"
    assert sh(backend, "rev-parse", "work") != sh(backend, "rev-parse", "main")  # untouched
