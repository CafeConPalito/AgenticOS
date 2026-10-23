"""The skill library through the API (phase 17, block 2): CA1 (create, edit, switch off, move,
export and delete at every level, with reasons in words) and CA12 (history, diff, restore)."""

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agentic_os.services.skills.library import SkillLibrary
from agentic_os.services.skills.store import SkillStore


def _skill(client: TestClient, name: str = "revision-codigo", **level) -> dict:
    payload = {
        "scope": "general",
        "name": name,
        "description": "Revisa los cambios de una rama.",
        "body": "# Pasos\n1. Lee el diff.\n",
        **level,
    }
    response = client.post("/api/skills", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _agent(client: TestClient) -> str:
    return client.post("/api/agents", json={"name": "Dev"}).json()["id"]


def _project(client: TestClient, tmp_path: Path) -> str:
    folder = tmp_path / "proyecto"
    folder.mkdir(exist_ok=True)
    response = client.post("/api/projects", json={"name": "Tienda", "path": str(folder)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_at_every_level_and_list_by_level(client: TestClient, tmp_path: Path):
    agent = _agent(client)
    project = _project(client, tmp_path)
    general = _skill(client)
    in_project = _skill(client, scope="project", project_id=project)
    in_agent = _skill(client, scope="agent", agent_id=agent)  # the same name at other levels
    assert general["version"] == 1 and general["files"] == 1
    assert general["header"] == {"name": "revision-codigo", "description": general["description"]}
    assert general["body"].startswith("# Pasos")
    listed = client.get("/api/skills", params={"scope": "project", "project_id": project}).json()
    assert [s["id"] for s in listed] == [in_project["id"]]
    assert {s["id"] for s in client.get("/api/skills").json()} == {
        general["id"],
        in_project["id"],
        in_agent["id"],
    }


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"name": "Revisión de código"}, 422, "bad_name"),
        ({"description": " "}, 422, "no_description"),
        ({"files": {"../fuera.txt": {"text": "x"}}}, 422, "bad_path"),
        ({"scope": "project"}, 422, "level_mismatch"),
    ],
)
def test_bad_skills_are_refused_with_a_reason(client: TestClient, payload, status, code):
    body = {"scope": "general", "name": "ok", "description": "d", **payload}
    response = client.post("/api/skills", json=body)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["message"]


def test_a_name_is_unique_in_its_level(client: TestClient):
    _skill(client)
    response = client.post(
        "/api/skills", json={"scope": "general", "name": "revision-codigo", "description": "d"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "name_taken"


def test_edit_makes_versions_and_keeps_the_header_fields(client: TestClient):
    skill = _skill(client)
    edited = client.post(
        f"/api/skills/{skill['id']}/versions",
        json={
            "description": "Revisa ramas: estándares y lo que pedía la tarea.",
            "files": {"scripts/check.py": {"text": "print('ok')\n"}},
            "note": "Añado el script",
        },
    ).json()
    assert edited["version"] == 2
    assert edited["executables"] == 1
    assert edited["body"].startswith("# Pasos")  # the body was not sent: it stays
    again = client.post(
        f"/api/skills/{skill['id']}/versions", json={"files": {"scripts/check.py": None}}
    ).json()
    assert again["version"] == 3 and again["files"] == 1
    versions = client.get(f"/api/skills/{skill['id']}/versions").json()
    assert [v["number"] for v in versions] == [3, 2, 1]
    assert versions[1]["note"] == "Añado el script"
    assert versions[0]["note"] == "quitado scripts/check.py"  # summarised from the diff
    assert versions[0]["current"] and not versions[1]["current"]
    assert versions[0]["author"]["kind"] == "user"


def test_saving_the_same_files_is_not_a_version(client: TestClient):
    skill = _skill(client)
    response = client.post(f"/api/skills/{skill['id']}/versions", json={"body": skill["body"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_changes"


def test_diff_between_any_two_versions_and_restore(client: TestClient):
    skill = _skill(client)
    sid = skill["id"]
    client.post(
        f"/api/skills/{sid}/versions", json={"body": "# Pasos\n1. Lee el diff con calma.\n"}
    )
    client.post(f"/api/skills/{sid}/versions", json={"files": {"ejemplo.md": {"text": "x\n"}}})
    versions = {v["number"]: v["id"] for v in client.get(f"/api/skills/{sid}/versions").json()}
    last = client.get(f"/api/skills/{sid}/diff").json()  # the current against the one before
    assert (last["from_version"], last["to_version"]) == (2, 3)
    assert [f["change"]["status"] for f in last["files"]] == ["added"]
    wide = client.get(f"/api/skills/{sid}/diff", params={"from": versions[1], "to": versions[3]})
    files = {f["change"]["path"]: f for f in wide.json()["files"]}
    assert set(files) == {"SKILL.md", "ejemplo.md"}
    lines = [line for h in files["SKILL.md"]["diff"]["hunks"] for line in h["lines"]]
    assert {"kind": "add", "text": "1. Lee el diff con calma."} in [
        {"kind": line["kind"], "text": line["text"]} for line in lines
    ]
    restored = client.post(f"/api/skills/{sid}/restore/{versions[1]}").json()
    assert restored["version"] == 4
    assert restored["body"] == skill["body"]
    history = client.get(f"/api/skills/{sid}/versions").json()
    assert len(history) == 4  # nothing was deleted
    assert history[0]["author"]["kind"] == "restore"
    assert history[0]["restored_from_id"] == versions[1]
    assert history[0]["note"] == "Restaurada la versión 1"


def test_switch_off_move_and_delete(client: TestClient):
    agent = _agent(client)
    skill = _skill(client)
    sid = skill["id"]
    off = client.patch(f"/api/skills/{sid}", json={"enabled": False}).json()
    assert off["enabled"] is False
    moved = client.patch(f"/api/skills/{sid}", json={"scope": "agent", "agent_id": agent}).json()
    assert (moved["scope"], moved["agent_id"]) == ("agent", agent)
    response = client.patch(f"/api/skills/{sid}", json={"agent_id": agent})
    assert response.json()["detail"]["code"] == "level_mismatch"
    assert client.delete(f"/api/skills/{sid}").status_code == 204
    assert client.get(f"/api/skills/{sid}").status_code == 404


def test_delete_removes_the_files_nobody_else_uses(client: TestClient, settings):
    a = _skill(client, "uno")
    _skill(client, "dos")
    store = SkillStore(Path(settings.data_dir))
    before = sum(1 for p in store.blobs.rglob("*") if p.is_file())
    client.delete(f"/api/skills/{a['id']}")
    after = sum(1 for p in store.blobs.rglob("*") if p.is_file())
    assert before == 2 and after == 1


def test_export_is_a_zip_of_the_current_version(client: TestClient):
    skill = _skill(client)
    client.post(f"/api/skills/{skill['id']}/versions", json={"files": {"a/b.txt": {"text": "x"}}})
    response = client.get(f"/api/skills/{skill['id']}/export")
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert sorted(names) == ["revision-codigo/SKILL.md", "revision-codigo/a/b.txt"]


def test_a_file_of_a_version_can_be_read(client: TestClient):
    skill = _skill(client)
    response = client.get(f"/api/skills/{skill['id']}/files/SKILL.md")
    assert response.text.startswith("---\nname: revision-codigo")
    assert client.get(f"/api/skills/{skill['id']}/files/otro.md").status_code == 404


def test_vectors_follow_the_name_and_description(tmp_path: Path):
    """The library asks for a vector when a skill is made or its description changes, and gives
    new ones to every skill when the model changes (spike S4)."""
    calls: list[list[str]] = []
    model = {"id": "e5"}

    def embed(texts: list[str]) -> np.ndarray:
        calls.append(texts)
        return np.ones((len(texts), 4), dtype=np.float32)

    from sqlalchemy.orm import Session

    from agentic_os.db.base import Base
    from agentic_os.db.session import create_db_engine

    engine = create_db_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    lib = SkillLibrary(SkillStore(tmp_path), embed=embed, model=lambda: model["id"])
    md = b"---\nname: uno\ndescription: Hace cosas.\n---\nB\n"
    with Session(engine) as db:
        skill, _ = lib.create(
            db, scope="general", project_id=None, agent_id=None, files={"SKILL.md": md}
        )
        assert calls == [["uno: Hace cosas."]]
        assert skill.vector_model == "e5" and len(skill.vector) == 16
        lib.edit(db, skill, body="Otro cuerpo")  # same description: no new vector
        assert len(calls) == 1
        model["id"] = "gemma"
        assert lib.refresh_stale(db) == 1
        assert skill.vector_model == "gemma"
        assert lib.refresh_stale(db) == 0
