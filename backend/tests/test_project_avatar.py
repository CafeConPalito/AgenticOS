"""Project photo (phase 24, block 1; CA1): a cropped photo like an agent's, without owls, that
can be changed and removed, and is kept by the cleanup of unused photos."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_avatars import picture

from agentic_os.services import avatars


def new_project(client: TestClient, folder: Path, name: str = "Web") -> dict:
    folder.mkdir(exist_ok=True)
    response = client.post("/api/projects", json={"name": name, "path": str(folder)})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, project_id: str, data: bytes):
    return client.put(
        f"/api/projects/{project_id}/avatar", content=data, headers={"Content-Type": "image/png"}
    )


def test_a_project_starts_with_its_initials_takes_a_photo_and_drops_it(
    client: TestClient, tmp_path: Path
):
    project = new_project(client, tmp_path / "web")
    assert project["avatar"] is None

    response = upload(client, project["id"], picture())
    assert response.status_code == 200, response.text
    value = response.json()["avatar"]
    assert value.startswith("photo:")
    assert client.get(f"/api/avatars/{value.removeprefix('photo:')}.webp").status_code == 200
    assert client.get(f"/api/projects/{project['id']}").json()["avatar"] == value
    assert any(p["avatar"] == value for p in client.get("/api/projects").json())

    changed = upload(client, project["id"], picture(128, color=(20, 120, 60))).json()["avatar"]
    assert changed != value

    cleared = client.patch(f"/api/projects/{project['id']}", json={"avatar": None})
    assert cleared.status_code == 200
    assert cleared.json()["avatar"] is None


def test_projects_take_no_owls_nor_photos_that_are_not_stored(client: TestClient, tmp_path: Path):
    project = new_project(client, tmp_path / "web")
    for bad, code in [
        ("owl:wizard", "avatar_no_owls"),
        ("photo:aaaaaaaaaaaa", "avatar_photo_missing"),
    ]:
        response = client.patch(f"/api/projects/{project['id']}", json={"avatar": bad})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == code
    assert client.patch(f"/api/projects/{project['id']}", json={"avatar": "x.png"}).status_code == (
        422
    )


def test_a_refused_crop_says_why_and_keeps_the_photo(client: TestClient, tmp_path: Path):
    project = new_project(client, tmp_path / "web")
    value = upload(client, project["id"], picture()).json()["avatar"]
    response = upload(client, project["id"], picture(256, height=100))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "avatar_not_square"
    assert client.get(f"/api/projects/{project['id']}").json()["avatar"] == value


def test_the_cleanup_keeps_the_photos_projects_use(client: TestClient, tmp_path: Path):
    project = new_project(client, tmp_path / "web")
    first = upload(client, project["id"], picture()).json()["avatar"]
    second = upload(client, project["id"], picture(128, color=(30, 90, 200))).json()["avatar"]
    data_dir = Path(client.app.state.settings.data_dir)
    with client.app.state.sessionmaker() as db:
        assert avatars.remove_unused(db, data_dir) == 1
    assert not avatars.photo_path(data_dir, first.removeprefix("photo:")).exists()
    assert avatars.photo_path(data_dir, second.removeprefix("photo:")).exists()
