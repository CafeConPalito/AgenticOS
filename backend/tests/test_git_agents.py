"""Agents and git (phase 12, block 7): permission to use it, what each run did with it and
undoing that."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gitrepos import commit_file, make_bare, make_repo, sh
from test_adapters import allowed, context
from test_git_api import make_project, repo_ids

from agentic_os.models import Cli, PermissionMode
from agentic_os.services.adapters import adapter_for
from agentic_os.services.context import GIT_RULES, build_instructions
from agentic_os.services.gitx import activity
from agentic_os.services.gitx.runner import Repo

BARE = "mcp__agentic-os__*"
GIT_TOOLS = ["Bash(git:*)", "PowerShell(git *)"]


# ------------------------------------------------------------------------------ authorization
@pytest.mark.parametrize(
    ("mode", "tools"),
    [
        (PermissionMode.ASK, [BARE, *GIT_TOOLS]),
        (PermissionMode.RESTRICTED, [BARE, *GIT_TOOLS, "Read", "Glob", "Grep"]),
        (PermissionMode.AUTONOMOUS, [BARE]),  # everything is allowed already
    ],
)
def test_claude_may_use_git_in_every_mode_when_the_project_allows_it(tmp_path: Path, mode, tools):
    ctx = dataclasses.replace(
        context(tmp_path, Cli.CLAUDE, mode=mode, tools=("read",)), git_authorized=True
    )
    argv = adapter_for(Cli.CLAUDE).prepare(ctx).argv
    assert allowed(argv) == tools


def test_without_the_authorization_claude_is_as_before(tmp_path: Path):
    ctx = context(tmp_path, Cli.CLAUDE, mode=PermissionMode.ASK)
    assert allowed(adapter_for(Cli.CLAUDE).prepare(ctx).argv) == [BARE]


def test_the_git_tool_of_a_restricted_agent_is_not_listed_twice(tmp_path: Path):
    ctx = dataclasses.replace(
        context(tmp_path, Cli.CLAUDE, mode=PermissionMode.RESTRICTED, tools=("git",)),
        git_authorized=True,
    )
    assert allowed(adapter_for(Cli.CLAUDE).prepare(ctx).argv) == [BARE, *GIT_TOOLS]


def test_the_agent_is_told_it_may_use_git_only_when_it_may():
    assert GIT_RULES in build_instructions(None, None, "D:/web", git_authorized=True)
    assert GIT_RULES not in build_instructions(None, None, "D:/web")


# ------------------------------------------------------------------------------ what a run did
def window() -> tuple[datetime, datetime]:
    """From a few seconds ago to a few seconds from now: every commit of the test is inside."""
    now = datetime.now(UTC)
    return now - timedelta(seconds=30), now + timedelta(seconds=30)


@pytest.fixture
def web(tmp_path: Path) -> Path:
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    bare = make_bare(tmp_path / "remote.git")
    sh(path, "remote", "add", "origin", str(bare))
    sh(path, "push", "-q", "-u", "origin", "main")
    return path


def test_commits_branches_tags_and_pushes_of_a_run_are_told_apart(web: Path):
    repo = Repo(str(web))
    before = activity.snapshot(repo)
    since, until = window()

    sh(web, "checkout", "-q", "-b", "feature")
    first = commit_file(web, "f.txt", "1\n", message="feature one")
    second = commit_file(web, "g.txt", "2\n", message="feature two")
    sh(web, "tag", "v1")
    sh(web, "push", "-q", "-u", "origin", "feature")
    sh(web, "checkout", "-q", "main")

    found = activity.collect(repo, before, since, until)

    assert [(c.sha, c.subject) for c in found.commits] == [
        (first, "feature one"),
        (second, "feature two"),
    ]
    assert [(b.name, b.start is None, b.end) for b in found.branches] == [("feature", True, second)]
    assert [t.name for t in found.tags] == ["v1"]
    (push,) = found.pushes
    assert (push.remote, push.branch, push.end, push.forced) == ("origin", "feature", second, False)
    assert found.head_start == "branch:main" and found.head_end == "branch:main"
    assert not found.empty


def test_a_force_push_is_recognised(web: Path):
    sh(web, "checkout", "-q", "-b", "feature")
    commit_file(web, "f.txt", "1\n", message="one")
    sh(web, "push", "-q", "-u", "origin", "feature")
    repo = Repo(str(web))
    before = activity.snapshot(repo)
    since, until = window()

    sh(web, "commit", "-q", "--amend", "-m", "one, reworded")  # rewrites the pushed commit
    sh(web, "push", "-q", "--force", "origin", "feature")

    found = activity.collect(repo, before, since, until)
    assert [c.kind for c in found.commits] == ["amend"]
    (push,) = found.pushes
    assert push.forced and push.branch == "feature"


def test_a_run_that_did_nothing_with_git_leaves_an_empty_record(web: Path):
    repo = Repo(str(web))
    before = activity.snapshot(repo)
    since, until = window()
    found = activity.collect(repo, before, since, until)
    assert found.empty and found.commits == [] and found.pushes == []


def test_what_another_task_did_in_the_same_repository_is_not_counted(web: Path, tmp_path: Path):
    """A worktree has its own HEAD reflog: the run in one folder does not see the commits made
    in another folder of the same repository."""
    other = tmp_path / "other"
    sh(web, "worktree", "add", "-q", "-b", "other-task", str(other))
    mine = tmp_path / "mine"
    sh(web, "worktree", "add", "-q", "-b", "my-task", str(mine))
    repo = Repo(str(mine))
    before = activity.snapshot(repo)
    since, until = window()

    commit_file(other, "x.txt", "x\n", message="somebody else")
    wanted = commit_file(mine, "y.txt", "y\n", message="mine")

    found = activity.collect(repo, before, since, until)
    assert [c.sha for c in found.commits] == [wanted]
    assert [b.name for b in found.branches] == ["my-task"]  # other-task moved, but not by this run


# ------------------------------------------------------------------------------ undoing it
def test_undo_puts_branches_back_and_deletes_the_ones_the_run_created(
    client: TestClient, tmp_path: Path
):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    project = make_project(client, path)
    rid = repo_ids(client, project)[path.name]
    sh(path, "branch", "work")
    repo = Repo(str(path))
    before = activity.snapshot(repo)
    since, until = window()
    base = sh(path, "rev-parse", "main")

    sh(path, "checkout", "-q", "work")
    commit_file(path, "w.txt", "w\n", message="work")
    sh(path, "branch", "extra")
    sh(path, "checkout", "-q", "main")
    found = activity.collect(repo, before, since, until)
    assert {b.name for b in found.branches} == {"work", "extra"}

    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from agentic_os.models import ProjectRepo

        row = db.get(ProjectRepo, rid)
        result = activity.undo(db, row, repo, found)
        db.commit()
    assert {(i.branch, i.result) for i in result.items} == {
        ("work", "reverted"),
        ("extra", "deleted"),
    }
    assert sh(path, "rev-parse", "work") == base
    assert sh(path, "branch", "--list", "extra") == ""
    # It is itself an operation of the repository, so «Deshacer» of the Git tab can undo it.
    ops = client.get(f"/api/repos/{rid}/operations").json()
    assert ops[0]["kind"] == "undo_run"


def test_undo_leaves_a_branch_that_moved_afterwards(client: TestClient, tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    project = make_project(client, path)
    rid = repo_ids(client, project)[path.name]
    sh(path, "branch", "work")
    repo = Repo(str(path))
    before = activity.snapshot(repo)
    since, until = window()
    sh(path, "checkout", "-q", "work")
    commit_file(path, "w.txt", "w\n", message="the run's commit")
    found = activity.collect(repo, before, since, until)
    later = commit_file(path, "z.txt", "z\n", message="the person kept working")
    sh(path, "checkout", "-q", "main")

    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from agentic_os.models import ProjectRepo

        result = activity.undo(db, db.get(ProjectRepo, rid), repo, found)
        db.commit()
    assert [(i.branch, i.result, i.reason) for i in result.items] == [
        ("work", "skipped", "moved_since")
    ]
    assert sh(path, "rev-parse", "work") == later  # not touched


def test_undoing_a_checked_out_branch_moves_its_folder_too(client: TestClient, tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    project = make_project(client, path)
    rid = repo_ids(client, project)[path.name]
    tree = tmp_path / "tree"
    sh(path, "worktree", "add", "-q", "-b", "task", str(tree))
    repo = Repo(str(tree))
    before = activity.snapshot(repo)
    since, until = window()
    commit_file(tree, "t.txt", "t\n", message="task work")
    found = activity.collect(repo, before, since, until)

    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from agentic_os.models import ProjectRepo

        result = activity.undo(db, db.get(ProjectRepo, rid), Repo(str(path)), found)
        db.commit()
    assert [(i.branch, i.result) for i in result.items] == [("task", "reverted")]
    assert not (tree / "t.txt").exists()  # the folder followed the branch
