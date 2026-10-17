"""Integrating the branches of a task into their bases, on real temporary repositories."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepos import commit_file, make_repo, sh, write
from sqlalchemy.orm import Session
from test_scheduler import db_factory, make_agent  # noqa: F401 - pytest fixture

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import InboxItem, Project, Task, TaskRepo, WorkspaceMode
from agentic_os.services import integration
from agentic_os.services import tasks as task_ops
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.worktrees import Worktrees


def make_project(db: Session, folder: Path, **fields) -> Project:
    project = Project(
        workspace_id=DEFAULT_WORKSPACE,
        name="Web",
        path=str(folder),
        path_key=str(folder),
        workspace_mode=WorkspaceMode.WORKTREE,
        base_branch="main",
        **fields,
    )
    db.add(project)
    db.flush()
    return project


def work_on(db: Session, project: Project, files: dict[str, str], title: str = "Login") -> Task:
    """A task that worked in each repository of the project (`files` by path relative to the
    project folder), committed on its branch, with its worktrees already released."""
    agent = make_agent(db, name=f"Dev {title}")
    task = task_ops.create_task(db, project, title, agent_id=agent.id)
    worktrees = Worktrees()
    folder = Path(worktrees.prepare(db, task, project) or "")
    for name, text in files.items():
        target = folder / name
        write(target.parent, target.name, text)
    for row in db.query(TaskRepo).filter_by(task_id=task.id):
        sh(Path(row.worktree_path or ""), "add", "-A")
        sh(Path(row.worktree_path or ""), "commit", "-q", "-m", f"work of {task.code}")
    worktrees.release(db, task, project)
    db.flush()
    return task


@pytest.fixture
def web(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "web", files={"a.txt": "base\n"})


def test_merge_into_a_checked_out_base_moves_the_folder(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        commit_file(web, "other.txt", "x\n", message="main moves")

        checked = integration.check(db, task, project)
        (item,) = checked.repos
        assert item.state == "clean" and item.ahead == 1 and item.behind == 1
        assert Path(item.active_in or "") == web and checked.can_integrate

        result = integration.run(db, task, project, "merge")
        assert result.integrated == 1 and not result.stopped
        assert (web / "login.py").exists()  # the folder followed the branch
        assert sh(web, "log", "-1", "--format=%s") == f"Merge {task.code}: Login"
        assert len(sh(web, "log", "-1", "--format=%P").split()) == 2
        row = db.query(TaskRepo).filter_by(task_id=task.id).one()
        assert row.integrated_sha == sh(web, "rev-parse", "main")
        assert integration.check(db, task, project).repos[0].state == "integrated"
        kinds = [e.kind for e in db.query(task_ops.TaskEvent).filter_by(task_id=task.id)]
        assert "integrated" in kinds


def test_merge_without_a_folder_only_moves_the_branch(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        sh(web, "checkout", "-q", "-b", "elsewhere")  # nobody has main checked out now
        head = sh(web, "rev-parse", "HEAD")

        assert integration.check(db, task, project).repos[0].active_in is None
        integration.run(db, task, project, "merge")

        assert "login.py" in sh(web, "ls-tree", "--name-only", "main").splitlines()
        assert sh(web, "rev-parse", "HEAD") == head and not (web / "login.py").exists()


def test_squash_leaves_one_commit_with_the_subjects(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        integration.run(db, task, project, "squash")
        assert len(sh(web, "log", "-1", "--format=%P").split()) == 1
        assert sh(web, "log", "-1", "--format=%s") == f"{task.code}: Login"
        assert f"work of {task.code}" in sh(web, "log", "-1", "--format=%b")


def test_rebase_keeps_a_straight_history(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        commit_file(web, "other.txt", "x\n", message="main moves")
        integration.run(db, task, project, "rebase")
        assert sh(web, "rev-list", "--merges", "--count", "main") == "0"
        assert sh(web, "log", "-1", "--format=%s") == f"work of {task.code}"
        assert (web / "login.py").exists() and (web / "other.txt").exists()


def test_conflicts_are_reported_and_nothing_moves(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"a.txt": "task\n"})
        commit_file(web, "a.txt", "main\n", message="main edits a")
        before = sh(web, "rev-parse", "main")

        checked = integration.check(db, task, project)
        assert checked.repos[0].state == "conflicts" and checked.repos[0].conflicts == ["a.txt"]
        assert not checked.can_integrate

        result = integration.run(db, task, project, "merge")
        assert result.stopped and result.integrated == 0
        assert result.repos[0].status == "conflicts" and result.repos[0].conflicts == ["a.txt"]
        assert sh(web, "rev-parse", "main") == before
        assert sh(web, "status", "--porcelain") == ""  # no half-done merge in the folder


def test_uncommitted_changes_in_the_base_folder_block_it(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        write(web, "a.txt", "dirty\n")

        item = integration.check(db, task, project).repos[0]
        assert item.state == "blocked" and item.dirty == ["a.txt"]
        result = integration.run(db, task, project, "merge")
        assert (
            result.repos[0].status == "blocked" and result.repos[0].error_code == "dirty_worktree"
        )
        assert (web / "a.txt").read_text() == "dirty\n"


def test_undo_puts_the_base_back_unless_it_moved(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        before = sh(web, "rev-parse", "main")
        integration.run(db, task, project, "merge")
        db.commit()

        commit_file(web, "later.txt", "x\n", message="later")
        with pytest.raises(GitxError) as moved:
            integration.undo(db, task, project)
        assert moved.value.code == "moved_since"

        sh(web, "reset", "-q", "--hard", "HEAD~1")  # drop that commit again
        assert integration.undo(db, task, project) == 1
        assert sh(web, "rev-parse", "main") == before and not (web / "login.py").exists()
        row = db.query(TaskRepo).filter_by(task_id=task.id).one()
        assert row.integrated_at is None
        with pytest.raises(GitxError) as none:
            integration.undo(db, task, project)
        assert none.value.code == "no_operation"


@pytest.fixture
def two(tmp_path: Path) -> Path:
    """A project folder (not a repository) with two: backend/ and frontend/."""
    folder = tmp_path / "shop"
    make_repo(folder / "backend", files={"a.txt": "base\n"})
    make_repo(folder / "frontend", files={"b.txt": "base\n"})
    return folder


def test_several_repositories_stop_at_the_first_conflict_and_undo_as_a_group(
    db_factory,  # noqa: F811
    two: Path,
):
    with db_factory() as db:
        project = make_project(db, two)
        task = work_on(db, project, {"backend/new.py": "n\n", "frontend/b.txt": "task\n"})
        commit_file(two / "frontend", "b.txt", "main\n", message="main edits b")
        backend_before = sh(two / "backend", "rev-parse", "main")

        checked = integration.check(db, task, project)
        states = {c.name: c.state for c in checked.repos}
        assert states == {"backend": "clean", "frontend": "conflicts"}

        result = integration.run(db, task, project, "merge")
        assert result.stopped and result.integrated == 1
        assert [o.status for o in result.repos] == ["integrated", "conflicts"]
        assert sh(two / "backend", "rev-parse", "main") != backend_before  # the first stays done

        db.commit()
        assert integration.undo(db, task, project) == 1
        assert sh(two / "backend", "rev-parse", "main") == backend_before


def test_resolving_here_brings_the_base_into_the_branch(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"a.txt": "task\n"})
        commit_file(web, "a.txt", "main\n", message="main edits a")
        repo_id = integration.check(db, task, project).repos[0].repo_id

        resolution = integration.prepare_resolution(db, task, project, repo_id)
        assert resolution.conflicts == ["a.txt"] and Path(resolution.path).is_dir()
        with pytest.raises(GitxError) as open_one:
            integration.finish_resolution(db, task, project, repo_id)
        assert open_one.value.code == "conflicts_unresolved"

        write(Path(resolution.path), "a.txt", "both\n")
        sh(Path(resolution.path), "add", "a.txt")
        integration.finish_resolution(db, task, project, repo_id)
        assert not Path(resolution.path).exists()

        assert integration.check(db, task, project).repos[0].state == "clean"
        integration.run(db, task, project, "merge")
        assert (web / "a.txt").read_text() == "both\n"


def test_a_resolver_task_works_on_the_branches_with_conflicts_only(
    db_factory,  # noqa: F811
    two: Path,
):
    with db_factory() as db:
        project = make_project(db, two)
        task = work_on(db, project, {"backend/new.py": "n\n", "frontend/b.txt": "task\n"})
        commit_file(two / "frontend", "b.txt", "main\n", message="main edits b")
        agent = make_agent(db, name="Fixer")

        fix = integration.resolution_task(db, task, project, agent.id)
        assert (
            fix.resolves_task_id == task.id and fix.title == f"Resolver conflictos de {task.code}"
        )
        assert "frontend" in fix.description and "`b.txt`" in fix.description

        folder = Worktrees().prepare(db, fix, project)
        rows = db.query(TaskRepo).filter_by(task_id=fix.id).all()
        assert len(rows) == 1 and rows[0].branch == task.branch  # the original's branch
        assert sh(Path(rows[0].worktree_path or ""), "branch", "--show-current") == task.branch
        assert folder


def test_a_task_without_conflicts_has_nothing_to_resolve(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        agent = make_agent(db, name="Fixer")
        with pytest.raises(GitxError) as error:
            integration.resolution_task(db, task, project, agent.id)
        assert error.value.code == "no_conflicts"


def test_on_approve_integrates_and_a_conflict_leaves_a_request(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web, on_approve="integrate", integration_mode="squash")
        clean = work_on(db, project, {"login.py": "login\n"}, title="Login")
        integration.after_approval(db, clean, project)
        assert (web / "login.py").exists()
        assert db.query(InboxItem).count() == 0

        clash = work_on(db, project, {"a.txt": "task\n"}, title="Clash")
        commit_file(web, "a.txt", "main\n", message="main edits a")
        integration.after_approval(db, clash, project)
        (item,) = db.query(InboxItem).all()
        assert item.kind == "delivery" and item.title == f"No se pudo integrar {clash.code}"
        assert "conflictos en web: 1 ficheros" in item.detail


def test_on_approve_none_does_nothing(db_factory, web: Path):  # noqa: F811
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        integration.after_approval(db, task, project)
        assert not (web / "login.py").exists()


def test_integrate_and_push_updates_the_remote_and_a_failed_push_keeps_the_integration(
    db_factory,  # noqa: F811
    web: Path,
    tmp_path: Path,
):
    from gitrepos import make_bare

    bare = make_bare(tmp_path / "remote.git")
    sh(web, "remote", "add", "origin", str(bare))
    sh(web, "push", "-q", "-u", "origin", "main")
    with db_factory() as db:
        project = make_project(db, web)
        task = work_on(db, project, {"login.py": "login\n"})
        result = integration.run(db, task, project, "merge", push=True)
        assert result.repos[0].pushed
        assert sh(bare, "rev-parse", "main") == sh(web, "rev-parse", "main")

        second = work_on(db, project, {"other.py": "x\n"}, title="Other")
        sh(web, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        failed = integration.run(db, second, project, "merge", push=True)
        item = failed.repos[0]
        assert item.status == "integrated" and not item.pushed and item.error_code
        assert (web / "other.py").exists()  # integrated locally even though the push failed
