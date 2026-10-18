"""Task worktrees on a real temporary git repository (folder name with spaces)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from test_scheduler import db_factory, make_agent  # noqa: F401 - pytest fixture

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Project, ProjectRepo, Task, TaskRepo, WorkspaceMode
from agentic_os.services import git, repos
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


def test_deleting_a_project_releases_its_task_worktrees(settings, tmp_path: Path):
    from fastapi.testclient import TestClient

    from agentic_os.app import create_app

    repo = make_repo(tmp_path / "web")
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        agent = client.post("/api/agents", json={"name": "Dev"}).json()
        project = client.post(
            "/api/projects",
            json={"name": "Web", "path": str(repo), "workspace_mode": "worktree"},
        ).json()
        task = client.post(
            "/api/tasks",
            json={"project_id": project["id"], "agent_id": agent["id"], "title": "x"},
        ).json()
        state = client.app.state
        with state.sessionmaker() as db:  # as the scheduler does before a launch
            row = db.get(Task, task["id"])
            path = state.scheduler.prepare_workspace(db, row, db.get(Project, project["id"]))
            db.commit()
        assert Path(path).is_dir()
        assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert not Path(path).exists()
    assert git.branch_exists(str(repo), "agentic/T-1")
    assert sh(repo, "worktree", "list").count("\n") == 0


# ------------------------------------------------------------------------ several repositories
def project_of(db: Session, folder: Path) -> tuple[Project, Task]:
    return make_task(db, folder)


def test_two_repositories_below_the_folder_get_a_worktree_each(db_factory, tmp_path: Path):  # noqa: F811
    from gitrepos import make_repo as repo_in

    folder = tmp_path / "shop"
    backend = repo_in(folder / "backend")
    frontend = repo_in(folder / "frontend", branch="develop")
    sh(frontend, "checkout", "-q", "develop")
    with db_factory() as db:
        project, task = make_task(db, folder)
        project.base_branch = None
        work = Path(Worktrees().prepare(db, task, project))
        assert work == tmp_path / "shop.wt" / "T-1"
        assert sh(work / "backend", "branch", "--show-current") == "agentic/T-1"
        assert sh(work / "frontend", "branch", "--show-current") == "agentic/T-1"
        # Each branch starts from its own repository's base.
        assert sh(backend, "rev-parse", "agentic/T-1") == sh(backend, "rev-parse", "main")
        assert sh(frontend, "rev-parse", "agentic/T-1") == sh(frontend, "rev-parse", "develop")
        rows = {
            db.get(ProjectRepo, r.repo_id).name: r
            for r in db.query(TaskRepo).filter_by(task_id=task.id)
        }
        assert set(rows) == {"backend", "frontend"}
        assert rows["backend"].worktree_path == str(work / "backend")
        assert rows["frontend"].base_commit == sh(frontend, "rev-parse", "develop")
        assert task.worktree_path == str(work) and task.branch == "agentic/T-1"
        assert Worktrees().prepare(db, task, project) == str(work)  # shared by every stage


def test_a_single_repository_below_the_folder_is_the_work_folder(db_factory, tmp_path: Path):  # noqa: F811
    from gitrepos import make_repo as repo_in

    folder = tmp_path / "shop"
    repo_in(folder / "backend")
    with db_factory() as db:
        project, task = make_task(db, folder)
        work = Path(Worktrees().prepare(db, task, project))
        assert (work / "README.md").exists() and (work / ".git").exists()


def test_release_commits_each_repository_and_drops_untouched_branches(
    db_factory,  # noqa: F811
    tmp_path: Path,
):
    from gitrepos import make_repo as repo_in

    folder = tmp_path / "shop"
    backend = repo_in(folder / "backend")
    frontend = repo_in(folder / "frontend")
    docs = repo_in(folder / "docs")
    with db_factory() as db:
        project, task = make_task(db, folder)
        worktrees = Worktrees()
        work = Path(worktrees.prepare(db, task, project))
        (work / "backend" / "api.py").write_text("x = 1\n", "utf-8")
        (work / "frontend" / "app.ts").write_text("let x = 1\n", "utf-8")
        worktrees.release(db, task, project)

        assert task.worktree_path is None and not work.exists()
        assert git.branch_exists(str(backend), "agentic/T-1")
        assert git.branch_exists(str(frontend), "agentic/T-1")
        assert not git.branch_exists(str(docs), "agentic/T-1")  # nothing happened there
        assert "api.py" in sh(backend, "ls-tree", "--name-only", "agentic/T-1").splitlines()
        assert "app.ts" in sh(frontend, "ls-tree", "--name-only", "agentic/T-1").splitlines()
        left = {
            db.get(ProjectRepo, r.repo_id).name
            for r in db.query(TaskRepo).filter_by(task_id=task.id)
        }
        assert left == {"backend", "frontend"}
        for repo in (backend, frontend, docs):
            assert sh(repo, "worktree", "list").count("\n") == 0

        # A retry brings the same branches back.
        again = Path(worktrees.prepare(db, task, project))
        assert (again / "backend" / "api.py").exists()


def test_a_failure_in_one_repository_leaves_no_worktrees_behind(db_factory, tmp_path: Path):  # noqa: F811
    from gitrepos import make_repo as repo_in

    folder = tmp_path / "shop"
    backend = repo_in(folder / "backend")
    repo_in(folder / "frontend")
    with db_factory() as db:
        project, task = make_task(db, folder)
        project.base_branch = None
        repos.sync(db, project)
        broken = db.query(ProjectRepo).filter_by(name="frontend").one()
        broken.base_branch = "ghost"
        with pytest.raises(git.GitError):
            Worktrees().prepare(db, task, project)
        assert task.worktree_path is None
        assert db.query(TaskRepo).filter_by(task_id=task.id).count() == 0
        assert sh(backend, "worktree", "list").count("\n") == 0


def test_a_repository_inside_another_is_not_committed_into_it(db_factory, tmp_path: Path):  # noqa: F811
    from gitrepos import make_repo as repo_in

    folder = repo_in(tmp_path / "mono")
    inner = repo_in(folder / "tools" / "cli")
    with db_factory() as db:
        project, task = make_task(db, folder)
        worktrees = Worktrees()
        work = Path(worktrees.prepare(db, task, project))
        assert (work / "tools" / "cli" / ".git").exists()
        (work / "root.txt").write_text("r\n", "utf-8")
        (work / "tools" / "cli" / "tool.py").write_text("t = 1\n", "utf-8")
        worktrees.release(db, task, project)
    root_tree = sh(folder, "ls-tree", "-r", "--name-only", "agentic/T-1").splitlines()
    assert "root.txt" in root_tree
    assert not any(name.startswith("tools") for name in root_tree)  # no gitlink either
    assert "tool.py" in sh(inner, "ls-tree", "--name-only", "agentic/T-1").splitlines()


def test_a_linked_repository_goes_to_an_at_folder(db_factory, tmp_path: Path):  # noqa: F811
    from gitrepos import make_repo as repo_in

    folder = repo_in(tmp_path / "app")
    shared = repo_in(tmp_path / "shared-lib")
    with db_factory() as db:
        project, task = make_task(db, folder)
        repos.ensure(db, project)
        repos.link(db, project, str(shared), name="Shared lib")
        work = Path(Worktrees().prepare(db, task, project))
        assert (work / ".git").exists()  # the root repository: the work folder itself
        assert (work / "@Shared lib" / "README.md").exists()
        assert sh(work / "@Shared lib", "branch", "--show-current") == "agentic/T-1"
