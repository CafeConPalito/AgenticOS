"""Task worktrees on a real temporary git repository (folder name with spaces)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from test_scheduler import db_factory, make_agent  # noqa: F401 - pytest fixture

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Project, Task, WorkspaceMode
from agentic_os.services import git
from agentic_os.services import tasks as task_ops
from agentic_os.services.worktrees import Worktrees, root_for


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def make_repo(folder: Path, identity: bool = True) -> Path:
    folder.mkdir(parents=True)
    sh(folder, "init", "-b", "main")
    if identity:
        sh(folder, "config", "user.name", "Test")
        sh(folder, "config", "user.email", "test@example.com")
    (folder / "README.md").write_text("hola\n", "utf-8")
    sh(folder, "add", "-A")
    sh(
        folder,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "init",
    )
    return folder


def make_task(db: Session, folder: Path) -> tuple[Project, Task]:
    project = Project(
        workspace_id=DEFAULT_WORKSPACE,
        name="Mi web",
        path=str(folder),
        path_key=str(folder),
        workspace_mode=WorkspaceMode.WORKTREE,
        base_branch="main",
    )
    db.add(project)
    db.flush()
    agent = make_agent(db)
    return project, task_ops.create_task(db, project, "Login", agent_id=agent.id)


class Forgotten:
    def __init__(self) -> None:
        self.folders: list[str] = []

    def forget(self, folder: str) -> None:
        self.folders.append(folder)


def test_prepare_reuse_and_release(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    trust = Forgotten()
    worktrees = Worktrees(trust)  # type: ignore[arg-type]
    with db_factory() as db:
        project, task = make_task(db, repo)
        path = worktrees.prepare(db, task, project)
        assert path == str(root_for(project) / "T-1") == str(tmp_path / "mi web.wt" / "T-1")
        assert task.branch == "agentic/T-1" and task.worktree_path == path
        assert sh(Path(path), "branch", "--show-current") == "agentic/T-1"
        assert worktrees.prepare(db, task, project) == path  # every stage shares it

        # The agent leaves work without committing: it is committed to the branch, not lost.
        (Path(path) / "login.py").write_text("print('login')\n", "utf-8")
        worktrees.release(db, task, project)
        assert task.worktree_path is None and not Path(path).exists()
        assert git.branch_exists(str(repo), "agentic/T-1")
        files = sh(repo, "ls-tree", "--name-only", "agentic/T-1")
        assert "login.py" in files.splitlines()
        message = sh(repo, "log", "-1", "--format=%s", "agentic/T-1")
        assert message == "chore(agentic): uncommitted work of T-1"
        assert sh(repo, "worktree", "list").count("\n") == 0  # only the main one
        assert trust.folders == [path]
        kinds = [e.kind for e in db.query(task_ops.TaskEvent).filter_by(task_id=task.id)]
        assert kinds.count("workspace") == 2

        # A retry after the folder is gone reuses the branch.
        again = worktrees.prepare(db, task, project)
        assert (Path(again) / "login.py").exists()


def test_without_identity_the_safety_commit_still_works(
    db_factory,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # No user.name/user.email anywhere: neither in the repo nor globally.
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", "utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = make_repo(tmp_path / "repo", identity=False)
    worktrees = Worktrees()
    with db_factory() as db:
        project, task = make_task(db, repo)
        path = Path(worktrees.prepare(db, task, project))
        (path / "nota.txt").write_text("x", "utf-8")
        worktrees.release(db, task, project)
    assert sh(repo, "log", "-1", "--format=%an <%ae>", "agentic/T-1") == (
        "Agentic OS <agentic-os@localhost>"
    )
    assert "nota.txt" in sh(repo, "ls-tree", "--name-only", "agentic/T-1").splitlines()


def test_direct_projects_have_no_worktree(db_factory, tmp_path: Path):  # noqa: F811
    with db_factory() as db:
        project, task = make_task(db, make_repo(tmp_path / "web"))
        project.workspace_mode = WorkspaceMode.DIRECT
        assert Worktrees().prepare(db, task, project) is None


def test_a_bad_base_branch_fails_clearly(db_factory, tmp_path: Path):  # noqa: F811
    with db_factory() as db:
        project, task = make_task(db, make_repo(tmp_path / "web"))
        project.base_branch = "develop"
        with pytest.raises(git.GitError):
            Worktrees().prepare(db, task, project)
