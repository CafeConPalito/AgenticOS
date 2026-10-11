import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.api import projects as projects_api

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run = ["git", "-C", str(path)]
    subprocess.run([*run, "init", "-q", "-b", branch], check=True)
    subprocess.run([*run, "config", "user.email", "t@example.com"], check=True)
    subprocess.run([*run, "config", "user.name", "Test"], check=True)
    (path / "README.md").write_text("hola", "utf-8")
    subprocess.run([*run, "add", "-A"], check=True)
    subprocess.run([*run, "commit", "-q", "-m", "init"], check=True)
    return path


def create(client: TestClient, **body) -> dict:
    response = client.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_roundtrip(client: TestClient, tmp_path: Path):
    folder = tmp_path / "tienda"
    folder.mkdir()
    project = create(client, name="Tienda online", path=str(folder))
    assert project["workspace_mode"] == "direct"
    assert project["path"] == str(folder.resolve())
    assert project["folder_exists"] is True
    assert project["git"] == {"is_repo": False, "branch": None, "dirty": False}

    updated = client.patch(f"/api/projects/{project['id']}", json={"description": "Tienda"})
    assert updated.json()["description"] == "Tienda"
    assert "memory" not in updated.json()  # the memory is a list of notes (/memory)

    assert [p["id"] for p in client.get("/api/projects").json()] == [project["id"]]
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert folder.is_dir()  # deleting the project never touches the folder
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_missing_folder_is_rejected_unless_created(client: TestClient, tmp_path: Path):
    missing = tmp_path / "nueva" / "web"
    response = client.post("/api/projects", json={"name": "Web", "path": str(missing)})
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "folder_not_found",
        "message": "the folder does not exist",
        "field": "path",
    }
    created = create(client, name="Web", path=str(missing), create_folder=True)
    assert missing.is_dir()
    assert created["folder_exists"] is True


def test_file_is_not_a_folder(client: TestClient, tmp_path: Path):
    file = tmp_path / "x.txt"
    file.write_text("x", "utf-8")
    response = client.post("/api/projects", json={"name": "X", "path": str(file)})
    assert response.json()["detail"]["code"] == "not_a_folder"


def test_duplicate_path_is_rejected_even_with_other_casing(client: TestClient, tmp_path: Path):
    folder = tmp_path / "Blog"
    folder.mkdir()
    create(client, name="Blog", path=str(folder))
    variants = [str(folder), str(folder) + "\\", str(folder).replace("\\", "/")]
    if Path("C:/").exists():  # Windows: paths are case-insensitive
        variants.append(str(folder).upper())
    for variant in variants:
        response = client.post("/api/projects", json={"name": "Otro", "path": variant})
        assert response.status_code == 409, variant
        assert response.json()["detail"]["code"] == "project_exists"


def test_worktree_mode_requires_git(client: TestClient, tmp_path: Path):
    folder = tmp_path / "plain"
    folder.mkdir()
    response = client.post(
        "/api/projects", json={"name": "P", "path": str(folder), "workspace_mode": "worktree"}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "worktree_requires_git"

    project = create(client, name="P", path=str(folder))
    response = client.patch(f"/api/projects/{project['id']}", json={"workspace_mode": "worktree"})
    assert response.json()["detail"]["code"] == "worktree_requires_git"


@needs_git
def test_git_state_is_detected(client: TestClient, tmp_path: Path):
    repo = git_repo(tmp_path / "app", branch="develop")
    project = create(client, name="App", path=str(repo), workspace_mode="worktree")
    assert project["git"] == {"is_repo": True, "branch": "develop", "dirty": False}

    (repo / "nuevo.txt").write_text("cambio", "utf-8")
    assert client.get(f"/api/projects/{project['id']}").json()["git"]["dirty"] is True


def test_folder_removed_after_registration(client: TestClient, tmp_path: Path):
    folder = tmp_path / "temporal"
    folder.mkdir()
    project = create(client, name="T", path=str(folder))
    folder.rmdir()
    fetched = client.get(f"/api/projects/{project['id']}").json()
    assert fetched["folder_exists"] is False
    assert fetched["git"] is None


def test_open_folder(client: TestClient, tmp_path: Path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(projects_api, "open_in_file_manager", opened.append)
    folder = tmp_path / "abrir"
    folder.mkdir()
    project = create(client, name="A", path=str(folder))
    assert client.post(f"/api/projects/{project['id']}/open").status_code == 204
    assert opened == [str(folder.resolve())]


def test_validation_errors(client: TestClient, tmp_path: Path):
    assert client.post("/api/projects", json={"path": str(tmp_path)}).json()["detail"]["field"] == (
        "name"
    )
    response = client.post("/api/projects", json={"name": "X", "path": "  "})
    assert response.json()["detail"]["field"] == "path"


def test_explicit_null_is_a_422(client: TestClient, tmp_path: Path):
    folder = tmp_path / "n"
    folder.mkdir()
    project = create(client, name="N", path=str(folder))
    response = client.patch(f"/api/projects/{project['id']}", json={"description": None})
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "description"


@pytest.mark.parametrize("relative", ["mi-web", "./mi-web", r"..\otra"])
def test_relative_paths_are_rejected(client: TestClient, relative: str):
    response = client.post(
        "/api/projects", json={"name": "W", "path": relative, "create_folder": True}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "path_not_absolute"


def test_unique_constraint_race_is_a_409(client: TestClient, tmp_path: Path, monkeypatch):
    # Simulate the race: both requests pass the pre-check, the second hits the DB constraint.
    folder = tmp_path / "carrera"
    folder.mkdir()
    create(client, name="A", path=str(folder))
    monkeypatch.setattr(projects_api, "_check_unique", lambda *a, **k: None)
    response = client.post("/api/projects", json={"name": "B", "path": str(folder)})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project_exists"
