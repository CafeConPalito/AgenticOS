"""Fetch, pull and push as jobs, on real repositories with a local remote (phase 12, bloque 2)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from gitrepos import commit_file, make_bare, make_repo, sh

from agentic_os.schemas.git import JobState
from agentic_os.services.gitx import read, remote
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.jobs import PROGRESS, JobManager
from agentic_os.services.gitx.runner import Repo


class Events:
    """What a WebSocket client would receive."""

    def __init__(self, manager: JobManager) -> None:
        self.items: list[dict] = []
        manager.listener = self.items.append

    def of(self, kind: str) -> list[dict]:
        return [e for e in self.items if e["type"] == kind]


def wait(manager: JobManager, job: JobState, seconds: float = 30) -> JobState:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = manager.get(job.id)
        assert state is not None
        if state.status != "running":
            return state
        time.sleep(0.05)
    raise AssertionError(f"job {job.kind} still running after {seconds}s")


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A bare remote, a repository that pushed to it and a clone of it."""
    bare = make_bare(tmp_path / "remote.git")
    first = make_repo(tmp_path / "first")
    sh(first, "remote", "add", "origin", str(bare))
    sh(first, "push", "-q", "-u", "origin", "main")
    second = tmp_path / "second"
    sh(tmp_path, "clone", "-q", str(bare), str(second))
    sh(second, "config", "user.name", "Otro")
    sh(second, "config", "user.email", "otro@example.com")
    sh(second, "config", "core.autocrlf", "false")
    return bare, first, second


def test_progress_lines_are_recognised():
    for line, phase, pct in (
        ("Receiving objects:  45% (45/100), 1.2 MiB | 2.0 MiB/s", "Receiving objects", 45),
        ("remote: Counting objects: 100% (12/12), done.", "Counting objects", 100),
        ("Resolving deltas:   7% (1/14)", "Resolving deltas", 7),
    ):
        match = PROGRESS.match(line)
        assert match and match.group("phase").strip() == phase and int(match.group("pct")) == pct
    assert PROGRESS.match("From https://github.com/x/y") is None


def test_a_fetch_job_brings_the_new_commits_and_emits_events(pair):
    _bare, first, second = pair
    commit_file(first, "nuevo.txt", "n\n")
    sh(first, "push", "-q")
    manager = JobManager()
    events = Events(manager)

    job = manager.start(Repo(str(second)), "repo-1", "fetch", remote.fetch_args())
    done = wait(manager, job)

    assert done.status == "succeeded" and done.percent == 100 and done.ended_at is not None
    assert read.status(Repo(str(second))).behind == 1
    kinds = [e["type"] for e in events.items]
    assert kinds[0] == "job" and kinds[-1] == "repo_changed"
    assert events.items[-1]["repo_id"] == "repo-1"
    assert events.of("job")[-1]["job"]["status"] == "succeeded"
    assert manager.active() == []


def test_a_pull_job_fast_forwards_and_refuses_what_is_not_one(pair):
    _bare, first, second = pair
    commit_file(first, "uno.txt", "1\n")
    sh(first, "push", "-q")
    manager = JobManager()
    repo = Repo(str(second))

    ok = wait(
        manager, manager.start(repo, "r", "pull", remote.pull_args("ff_only"), exclusive=True)
    )
    assert ok.status == "succeeded" and (second / "uno.txt").exists()

    commit_file(first, "dos.txt", "2\n")
    sh(first, "push", "-q")
    commit_file(second, "local.txt", "l\n")  # now both sides have something the other lacks
    refused = wait(
        manager, manager.start(repo, "r", "pull", remote.pull_args("ff_only"), exclusive=True)
    )
    assert refused.status == "failed" and refused.error_code == "non_fast_forward"

    merged = wait(
        manager, manager.start(repo, "r", "pull", remote.pull_args("merge"), exclusive=True)
    )
    assert merged.status == "succeeded" and (second / "dos.txt").exists()


def test_pull_with_rebase_keeps_a_straight_history(pair):
    _bare, first, second = pair
    commit_file(first, "remoto.txt", "r\n")
    sh(first, "push", "-q")
    commit_file(second, "local.txt", "l\n", message="local")
    manager = JobManager()

    done = wait(
        manager,
        manager.start(Repo(str(second)), "r", "pull", remote.pull_args("rebase"), exclusive=True),
    )

    assert done.status == "succeeded"
    assert sh(second, "log", "--format=%s", "-1") == "local"
    assert sh(second, "rev-list", "--merges", "--count", "HEAD") == "0"


def test_a_push_job_publishes_the_branch_and_gives_a_new_one_an_upstream(pair):
    bare, _first, second = pair
    repo = Repo(str(second))
    sh(second, "checkout", "-q", "-b", "feature")
    commit_file(second, "f.txt", "f\n")
    manager = JobManager()

    args = remote.push_args(repo)
    assert args[:3] == ["push", "--progress", "-u"] and args[-2:] == ["origin", "feature"]
    done = wait(manager, manager.start(repo, "r", "push", args))

    assert done.status == "succeeded"
    assert sh(bare, "rev-parse", "feature") == sh(second, "rev-parse", "feature")
    assert read.status(repo).upstream == "origin/feature"
    assert "-u" not in remote.push_args(repo)  # it has one now
    # Pushing something the remote has moved past is refused, never forced.
    sh(second, "reset", "-q", "--hard", "HEAD~1")
    commit_file(second, "g.txt", "g\n")
    rejected = wait(manager, manager.start(repo, "r", "push", remote.push_args(repo)))
    assert rejected.status == "failed" and rejected.error_code == "non_fast_forward"


def test_a_job_that_cannot_reach_the_remote_fails_with_a_clear_code(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    sh(path, "remote", "add", "origin", "http://127.0.0.1:9/none.git")
    manager = JobManager()

    done = wait(manager, manager.start(Repo(str(path)), "r", "fetch", remote.fetch_args()))

    assert done.status == "failed" and done.error_code == "network" and done.message


def test_asking_for_credentials_fails_instead_of_waiting(tmp_path: Path):
    """An https remote that wants a login must not leave the job waiting at a prompt."""
    path = make_repo(tmp_path / "web")
    sh(
        path,
        "remote",
        "add",
        "origin",
        "https://github.com/octocat/this-repo-does-not-exist-xyz.git",
    )
    manager = JobManager()

    started = time.monotonic()
    done = wait(
        manager,
        manager.start(
            Repo(str(path)),
            "r",
            "fetch",
            ["-c", "credential.helper=", *remote.fetch_args()],
            interactive=False,
        ),
        seconds=40,
    )

    assert done.status == "failed" and done.error_code in ("auth_failed", "network")
    assert time.monotonic() - started < 30


def test_a_running_job_can_be_cancelled(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    manager = JobManager()
    events = Events(manager)

    job = manager.start(Repo(str(path)), "r", "gc", ["-c", "alias.zz=!sleep 60", "zz"])
    time.sleep(0.5)
    assert manager.get(job.id).status == "running"  # type: ignore[union-attr]
    assert [s.id for s in manager.active("r")] == [job.id] and manager.active("otro") == []

    started = time.monotonic()
    assert manager.cancel(job.id)
    done = wait(manager, job, seconds=15)

    assert done.status == "cancelled" and time.monotonic() - started < 10
    assert events.of("job")[-1]["job"]["status"] == "cancelled"
    assert not manager.cancel(job.id)  # nothing left to cancel
    assert not manager.cancel("nope")


def test_an_exclusive_job_holds_the_repositorys_write_lock(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    repo = Repo(str(path))
    manager = JobManager()

    job = manager.start(repo, "r", "pull", ["-c", "alias.zz=!sleep 3", "zz"], exclusive=True)
    time.sleep(0.5)
    took: list[float] = []

    def other() -> None:
        started = time.monotonic()
        with Repo(str(path)).write():  # the same repository, another handle
            took.append(time.monotonic() - started)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(timeout=10)
    wait(manager, job)

    assert took and took[0] > 1.5  # it waited for the job


# ------------------------------------------------------------------------------- helpers
def test_remotes_and_defaults(pair):
    bare, _first, second = pair
    repo = Repo(str(second))

    assert [(r.name, r.fetch_url) for r in remote.remotes(repo)] == [
        ("origin", str(bare).replace("\\", "/"))
    ] or [r.name for r in remote.remotes(repo)] == ["origin"]
    assert remote.default_remote(repo, "main") == "origin"
    assert remote.default_remote(repo) == "origin"
    assert remote.fetch_args("upstream", prune=False) == ["fetch", "--progress", "upstream"]
    assert remote.pull_args("rebase", "origin", "main")[2:] == ["--rebase", "origin", "main"]


def test_without_a_remote_or_a_branch_there_is_nothing_to_push(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    repo = Repo(str(path))
    with pytest.raises(GitxError) as none:
        remote.push_args(repo)
    assert none.value.code == "no_remote"
    sh(path, "checkout", "-q", "--detach")
    with pytest.raises(GitxError) as detached:
        remote.push_args(repo)
    assert detached.value.code == "detached_head"
