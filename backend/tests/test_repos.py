"""Finding and keeping the git repositories of a project (phase 12, bloque 1)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from gitrepos import commit_file, make_repo, sh, write
from sqlalchemy.orm import Session
from test_scheduler import db_factory  # noqa: F401 - pytest fixture

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Project
from agentic_os.services import repos


def project_in(db: Session, folder: Path, **values) -> Project:
    project = Project(
        workspace_id=DEFAULT_WORKSPACE,
        name=values.pop("name", "Mi web"),
        path=str(folder),
        path_key=str(folder).lower(),
        **values,
    )
    db.add(project)
    db.flush()
    return project


def rels(found: list[repos.Found]) -> list[str]:
    return [f.rel_path for f in found]


def test_a_folder_that_is_not_a_repo_with_two_repos_inside(tmp_path: Path):
    make_repo(tmp_path / "backend")
    make_repo(tmp_path / "frontend")
    (tmp_path / "docs").mkdir()
    assert rels(repos.scan(str(tmp_path))) == ["backend", "frontend"]


def test_the_folder_itself_comes_first_and_nested_repos_are_found(tmp_path: Path):
    make_repo(tmp_path)
    make_repo(tmp_path / "tools" / "cli")
    assert rels(repos.scan(str(tmp_path))) == ["", "tools/cli"]


def test_depth_limits_the_walk(tmp_path: Path):
    make_repo(tmp_path / "a" / "b" / "c" / "deep")
    assert rels(repos.scan(str(tmp_path), depth=3)) == []
    assert rels(repos.scan(str(tmp_path), depth=4)) == ["a/b/c/deep"]


def test_dependency_folders_and_ignored_folders_are_not_walked(tmp_path: Path):
    make_repo(tmp_path / "app", files={".gitignore": "vendored/\n"})
    make_repo(tmp_path / "app" / "node_modules" / "pkg")
    make_repo(tmp_path / "app" / "vendored" / "lib")
    make_repo(tmp_path / "app" / "real")
    assert rels(repos.scan(str(tmp_path))) == ["app", "app/real"]


def test_submodules_belong_to_their_repository(tmp_path: Path):
    library = make_repo(tmp_path / "lib-source")
    app = make_repo(tmp_path / "app")
    sh(app, "submodule", "add", str(library), "vendor/lib")
    sh(app, "commit", "-q", "-m", "add submodule")
    assert (app / "vendor" / "lib" / ".git").exists()
    assert rels(repos.scan(str(app))) == [""]


def test_sync_adds_repositories_with_their_current_branch(db_factory, tmp_path: Path):  # noqa: F811
    make_repo(tmp_path / "backend", branch="develop")
    make_repo(tmp_path / "frontend")
    with db_factory() as db:
        project = project_in(db, tmp_path)
        listed = repos.sync(db, project)
        assert [(r.rel_path, r.name, r.base_branch) for r in listed] == [
            ("backend", "backend", "develop"),
            ("frontend", "frontend", "main"),
        ]
        assert all(r.participates and not r.linked and not r.missing for r in listed)
        # Looking again changes nothing.
        assert [r.id for r in repos.sync(db, project)] == [r.id for r in listed]


def test_the_project_base_branch_is_the_root_repositorys(db_factory, tmp_path: Path):  # noqa: F811
    make_repo(tmp_path)
    sh(tmp_path, "branch", "release")
    with db_factory() as db:
        project = project_in(db, tmp_path, base_branch="release")
        (root,) = repos.sync(db, project)
        assert root.base_branch == "release" and root.rel_path == ""


def test_a_repository_that_disappears_is_marked_and_kept(db_factory, tmp_path: Path):  # noqa: F811
    make_repo(tmp_path / "backend")
    make_repo(tmp_path / "frontend")
    with db_factory() as db:
        project = project_in(db, tmp_path)
        repos.sync(db, project)
        (tmp_path / "frontend" / ".git").rename(tmp_path / "frontend" / ".git-off")
        after = {r.name: r.missing for r in repos.sync(db, project)}
        assert after == {"backend": False, "frontend": True}
        (tmp_path / "frontend" / ".git-off").rename(tmp_path / "frontend" / ".git")
        assert {r.name: r.missing for r in repos.sync(db, project)} == {
            "backend": False,
            "frontend": False,
        }


def test_ensure_scans_a_project_nobody_has_looked_at(db_factory, tmp_path: Path):  # noqa: F811
    make_repo(tmp_path)
    with db_factory() as db:
        project = project_in(db, tmp_path)
        assert [r.rel_path for r in repos.ensure(db, project)] == [""]
        assert [r.rel_path for r in repos.active(db, project)] == [""]


def test_a_project_that_is_a_subfolder_of_a_repository_uses_that_repository(
    db_factory,  # noqa: F811
    tmp_path: Path,
):
    top = make_repo(tmp_path / "mono")
    write(top, "services/api/main.py", "x = 1\n")
    sh(top, "add", "-A")
    sh(top, "commit", "-q", "-m", "api")
    with db_factory() as db:
        project = project_in(db, top / "services" / "api")
        (repo,) = repos.sync(db, project)
        assert (repo.linked, repo.rel_path, repo.name) == (True, None, "mono")
        assert Path(repo.path) == top.resolve()


def test_link_a_repository_outside_the_folder(db_factory, tmp_path: Path):  # noqa: F811
    project_folder = tmp_path / "project"
    project_folder.mkdir()
    shared = make_repo(tmp_path / "shared-lib")
    with db_factory() as db:
        project = project_in(db, project_folder)
        linked = repos.link(db, project, str(shared), name="Shared")
        assert (linked.linked, linked.rel_path, linked.name) == (True, None, "Shared")
        assert linked.base_branch == "main"
        # A later scan keeps it and does not mark it missing.
        assert [(r.name, r.missing) for r in repos.sync(db, project)] == [("Shared", False)]


def test_link_rejects_a_folder_that_is_not_a_repository_root(db_factory, tmp_path: Path):  # noqa: F811
    from agentic_os.errors import ApiError

    plain = tmp_path / "plain"
    plain.mkdir()
    inner = make_repo(tmp_path / "outer")
    (inner / "sub").mkdir()
    with db_factory() as db:
        project = project_in(db, tmp_path / "project")
        for path in (plain, inner / "sub"):
            try:
                repos.link(db, project, str(path))
            except ApiError as error:
                assert error.code == "not_a_repository"
            else:
                raise AssertionError(f"{path} should be rejected")


def test_nested_paths_are_left_out_of_the_parents_snapshots(db_factory, tmp_path: Path):  # noqa: F811
    make_repo(tmp_path)
    make_repo(tmp_path / "tools" / "cli")
    with db_factory() as db:
        project = project_in(db, tmp_path)
        listed = repos.sync(db, project)
        root, cli = listed
        assert repos.nested_paths(listed, root) == ["tools/cli"]
        assert repos.nested_paths(listed, cli) == []


# ------------------------------------------------------------------------------------------- API
def create_project(client: TestClient, folder: Path, **extra) -> dict:
    response = client.post("/api/projects", json={"name": "P", "path": str(folder), **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_api_lists_scans_and_edits_repositories(client: TestClient, tmp_path: Path):
    make_repo(tmp_path / "backend")
    make_repo(tmp_path / "frontend")
    project = create_project(client, tmp_path)

    listed = client.get(f"/api/projects/{project['id']}/repos").json()
    assert [r["rel_path"] for r in listed] == ["backend", "frontend"]
    assert listed[0]["git"] == {"is_repo": True, "branch": "main", "dirty": False}

    make_repo(tmp_path / "docs-site")
    assert len(client.get(f"/api/projects/{project['id']}/repos").json()) == 2
    scanned = client.post(f"/api/projects/{project['id']}/repos/scan").json()
    assert [r["rel_path"] for r in scanned] == ["backend", "frontend", "docs-site"]

    backend = listed[0]
    sh(tmp_path / "backend", "branch", "develop")
    edited = client.patch(
        f"/api/repos/{backend['id']}",
        json={"base_branch": "develop", "participates": False, "pull_mode": "rebase"},
    ).json()
    assert (edited["base_branch"], edited["participates"], edited["pull_mode"]) == (
        "develop",
        False,
        "rebase",
    )
    unknown = client.patch(f"/api/repos/{backend['id']}", json={"base_branch": "nope"})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "unknown_branch"


def test_api_links_and_removes_a_repository(client: TestClient, tmp_path: Path):
    folder = tmp_path / "project"
    folder.mkdir()
    shared = make_repo(tmp_path / "shared")
    project = create_project(client, folder)

    response = client.post(f"/api/projects/{project['id']}/repos", json={"path": str(shared)})
    assert response.status_code == 201, response.text
    linked = response.json()
    assert linked["linked"] is True and linked["rel_path"] is None

    again = client.post(f"/api/projects/{project['id']}/repos", json={"path": str(shared)})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "repo_exists"

    assert client.delete(f"/api/repos/{linked['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}/repos").json() == []
    assert shared.is_dir()  # never touched
    assert client.delete(f"/api/repos/{linked['id']}").status_code == 404


def test_worktree_mode_works_with_repositories_below_the_folder(client: TestClient, tmp_path: Path):
    make_repo(tmp_path / "backend", branch="develop")
    project = create_project(client, tmp_path, workspace_mode="worktree")
    # No root repository: the base is the first repository's current branch.
    assert project["base_branch"] == "develop"
    commit_file(tmp_path / "backend", "a.txt", "1\n")
    unknown = client.patch(f"/api/projects/{project['id']}", json={"base_branch": "ghost"})
    assert unknown.json()["detail"]["code"] == "unknown_branch"
