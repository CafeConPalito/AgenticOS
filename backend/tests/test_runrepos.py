"""Where each repository of a project is for one run (phase 12, bloque 1)."""

from __future__ import annotations

from pathlib import Path

from gitrepos import make_repo
from test_scheduler import db_factory  # noqa: F401 - pytest fixture
from test_worktrees import make_task

from agentic_os.models import WorkspaceMode
from agentic_os.services import repos, runrepos
from agentic_os.services.worktrees import Worktrees


def test_a_direct_run_sees_the_repositories_where_they_are(db_factory, tmp_path: Path):  # noqa: F811
    folder = tmp_path / "shop"
    make_repo(folder / "backend")
    make_repo(folder / "frontend")
    shared = make_repo(tmp_path / "shared")
    with db_factory() as db:
        project, task = make_task(db, folder)
        project.workspace_mode = WorkspaceMode.DIRECT
        repos.ensure(db, project)
        repos.link(db, project, str(shared), name="Shared")
        found = runrepos.targets_for(db, project, task)
        assert [(t.name, t.branch) for t in found] == [
            ("backend", None),
            ("frontend", None),
            ("Shared", None),
        ]
        assert runrepos.extra_dirs(found, str(folder)) == (str(shared.resolve()),)


def test_a_worktree_task_sees_its_worktrees_and_its_branch(db_factory, tmp_path: Path):  # noqa: F811
    folder = tmp_path / "shop"
    make_repo(folder / "backend")
    make_repo(folder / "frontend")
    with db_factory() as db:
        project, task = make_task(db, folder)
        work = Worktrees().prepare(db, task, project)
        found = runrepos.targets_for(db, project, task)
        assert [(t.name, t.branch, t.base) for t in found] == [
            ("backend", "agentic/T-1", "main"),
            ("frontend", "agentic/T-1", "main"),
        ]
        assert {Path(t.folder) for t in found} == {Path(work) / "backend", Path(work) / "frontend"}
        assert runrepos.extra_dirs(found, work) == ()


def test_a_project_without_repositories_has_no_targets(db_factory, tmp_path: Path):  # noqa: F811
    (tmp_path / "notes").mkdir()
    with db_factory() as db:
        project, task = make_task(db, tmp_path / "notes")
        assert runrepos.targets_for(db, project, None) == []
        assert runrepos.targets_for(db, None, task) == []


def test_nested_folders_are_relative_and_exclude_the_folder_itself():
    root = str(Path("D:/web"))
    others = [root, str(Path("D:/web/tools/cli")), str(Path("D:/elsewhere")), str(Path("D:/webby"))]
    assert runrepos.nested_in(root, others) == ["tools/cli"]


def test_is_within_does_not_confuse_prefixes():
    assert runrepos.is_within("D:/web/api", "D:/web")
    assert runrepos.is_within("D:/web", "D:/web")
    assert not runrepos.is_within("D:/webby", "D:/web")
