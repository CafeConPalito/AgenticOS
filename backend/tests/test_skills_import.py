"""Importing skills (phase 17, block 2, CA2): a folder, a .zip, a lone SKILL.md and the skills of
the CLIs, each to the level the person chooses. The originals are never changed."""

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MD = "---\nname: {name}\ndescription: {description}\n---\n\nCuerpo de {name}.\n"


def _folder(root: Path, name: str, description: str = "Hace cosas.", **extra: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(MD.format(name=name, description=description), "utf-8")
    for path, text in extra.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, "utf-8")
    return folder


def _tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(folder).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _import(client: TestClient, path: Path, **level) -> dict:
    response = client.post(
        "/api/skills/import", json={"scope": "general", "path": str(path), **level}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_folder_is_imported_with_its_files_and_left_untouched(client: TestClient, tmp_path):
    files = {"scripts/fill.py": "print('x')\n", "reference/forms.md": "F\n"}
    folder = _folder(tmp_path / "src", "pdf-tools", **files)
    (folder / "__pycache__").mkdir()
    (folder / "__pycache__" / "x.pyc").write_bytes(b"\0")
    before = _tree_hash(folder)
    result = _import(client, folder)
    assert result["error_code"] is None
    skill = result["skill"]
    assert (skill["name"], skill["origin"], skill["files"], skill["executables"]) == (
        "pdf-tools",
        "import",
        3,
        1,
    )
    assert _tree_hash(folder) == before
    versions = client.get(f"/api/skills/{skill['id']}/versions").json()
    assert versions[0]["author"]["kind"] == "import"


def test_a_zip_with_one_top_folder_and_a_lone_skill_md(client: TestClient, tmp_path):
    archive = tmp_path / "skill.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("informes/SKILL.md", MD.format(name="informes", description="d"))
        z.writestr("informes/plantilla.md", "T")
    assert _import(client, archive)["skill"]["files"] == 2
    lone = tmp_path / "SKILL.md"
    lone.write_text(MD.format(name="suelta", description="d"), "utf-8")
    assert _import(client, lone)["skill"]["name"] == "suelta"


def test_a_zip_that_escapes_its_folder_is_refused(client: TestClient, tmp_path):
    archive = tmp_path / "malo.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("SKILL.md", MD.format(name="malo", description="d"))
        z.writestr("../../fuera.txt", "x")
    archive.write_bytes(buffer.getvalue())
    result = _import(client, archive)
    assert (result["skill"], result["error_code"]) == (None, "bad_path")


def test_a_taken_name_gets_a_number(client: TestClient, tmp_path):
    folder = _folder(tmp_path / "src", "notas")
    _import(client, folder)
    second = _import(client, folder)
    assert second["renamed_to"] == "notas-2"
    assert second["skill"]["name"] == "notas-2"


def test_a_missing_path_or_wrong_kind_is_an_error_in_the_result(client: TestClient, tmp_path):
    assert _import(client, tmp_path / "no-existe")["error_code"] == "not_found"
    other = tmp_path / "foto.png"
    other.write_bytes(b"\x89PNG")
    assert _import(client, other)["error_code"] == "unsupported"


@pytest.fixture
def cli_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    _folder(home / ".claude" / "skills", "mi-revision", "Mi forma de revisar.")
    _folder(home / ".gemini" / "config" / "skills", "agy-global")
    broken = home / ".claude" / "skills" / "rota"
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text("sin cabecera", "utf-8")
    return home


def test_scan_lists_the_clis_and_the_repositories_skills(client: TestClient, tmp_path, cli_home):
    repo = tmp_path / "repo"
    _folder(repo / ".claude" / "skills", "del-repo")
    _folder(repo / ".agents" / "skills", "del-repo-agy")
    project = client.post("/api/projects", json={"name": "Repo", "path": str(repo)}).json()
    found = {s["name"]: s for s in client.get("/api/skills/cli-scan").json()}
    assert found["mi-revision"]["source"] == "claude_user"
    assert found["agy-global"]["source"] == "agy_global"
    assert found["del-repo"]["source"] == "claude_project"
    assert found["del-repo"]["project_id"] == project["id"]
    assert found["del-repo-agy"]["source"] == "agy_project"
    assert found["rota"]["error"]
    assert not any(s["imported"] for s in found.values())


def test_cli_skills_are_imported_each_to_its_level(client: TestClient, tmp_path, cli_home):
    agent = client.post("/api/agents", json={"name": "Dev"}).json()["id"]
    source = cli_home / ".claude" / "skills" / "mi-revision"
    before = _tree_hash(source)
    results = client.post(
        "/api/skills/cli-import",
        json={
            "items": [
                {"path": str(source), "scope": "agent", "agent_id": agent},
                {"path": str(cli_home / ".claude" / "skills" / "rota"), "scope": "general"},
                {"path": str(cli_home / ".gemini/config/skills/agy-global"), "scope": "general"},
            ]
        },
    ).json()
    assert results[0]["skill"]["scope"] == "agent"
    assert results[1]["error_code"] == "no_header"  # one failure leaves the others in
    assert results[2]["skill"]["name"] == "agy-global"
    assert _tree_hash(source) == before
    found = {s["name"]: s for s in client.get("/api/skills/cli-scan").json()}
    assert found["mi-revision"]["imported"] and not found["rota"]["imported"]


def test_a_zip_made_by_macos_finder_is_unwrapped(client: TestClient, tmp_path):
    """Code review: «Compress» on macOS adds __MACOSX/ with «._» files next to the folder."""
    archive = tmp_path / "informes.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("informes/SKILL.md", MD.format(name="informes", description="d"))
        z.writestr("__MACOSX/informes/._SKILL.md", "\0\0")
        z.writestr("informes/._plantilla.md", "\0")
    result = _import(client, archive)
    assert result["skill"]["files"] == 1, result
