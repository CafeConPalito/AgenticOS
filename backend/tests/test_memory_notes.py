from pathlib import Path

from fastapi.testclient import TestClient


def create_project(client: TestClient, tmp_path: Path, name: str = "Web") -> dict:
    folder = tmp_path / name
    folder.mkdir()
    response = client.post("/api/projects", json={"name": name, "path": str(folder)})
    assert response.status_code == 201
    return response.json()


def test_notes_crud(client: TestClient, tmp_path: Path):
    project = create_project(client, tmp_path)
    base = f"/api/projects/{project['id']}/memory"
    assert client.get(base).json() == {"notes": [], "size": 0, "limit": 12_000}

    first = client.post(base, json={"text": "  Usa pnpm.  "}).json()
    assert (first["author_kind"], first["author_name"], first["text"]) == ("user", "", "Usa pnpm.")
    second = client.post(base, json={"text": "Despliega con Docker."}).json()

    edited = client.patch(f"{base}/{first['id']}", json={"text": "Usa pnpm 9."}).json()
    assert edited["text"] == "Usa pnpm 9."

    memory = client.get(base).json()
    assert [n["text"] for n in memory["notes"]] == ["Usa pnpm 9.", "Despliega con Docker."]
    assert memory["size"] > 0

    assert client.delete(f"{base}/{second['id']}").status_code == 204
    assert [n["id"] for n in client.get(base).json()["notes"]] == [first["id"]]


def test_invalid_notes_and_foreign_ids(client: TestClient, tmp_path: Path):
    web = create_project(client, tmp_path, "Web")
    blog = create_project(client, tmp_path, "Blog")
    base = f"/api/projects/{web['id']}/memory"
    assert client.post(base, json={"text": "   "}).status_code == 422
    assert client.post(base, json={"text": "x", "author_kind": "agent"}).status_code == 422
    assert client.get("/api/projects/nope/memory").status_code == 404

    note = client.post(base, json={"text": "de Web"}).json()
    # A note can only be reached through its own project.
    other = f"/api/projects/{blog['id']}/memory/{note['id']}"
    assert client.patch(other, json={"text": "x"}).status_code == 404
    assert client.delete(other).status_code == 404


def test_notes_die_with_their_project(client: TestClient, tmp_path: Path):
    project = create_project(client, tmp_path)
    client.post(f"/api/projects/{project['id']}/memory", json={"text": "nota"})
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}/memory").status_code == 404
