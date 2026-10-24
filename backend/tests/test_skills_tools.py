"""use_skill and read_skill_file through the real MCP server (phase 17, block 3, CA7): only the
skills the run can see, never a path outside the skill, and every load recorded."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from sqlalchemy import select
from test_mcp_server import call, events, mcp_url, seed_run

from agentic_os.config import Settings
from agentic_os.models import Agent, Run, RunSkill


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def api(server: LiveServer, method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{server.url}/api{path}", timeout=60, **kwargs)


def _skill(server: LiveServer, name: str, **level) -> dict:
    body = {
        "scope": "general",
        "name": name,
        "description": f"Descripción de {name}.",
        "body": f"Instrucciones de {name}.",
        "files": {
            "reference/guia.md": {"text": "Guía de apoyo."},
            "scripts/run.py": {"text": "print(1)"},
        },
        **level,
    }
    response = api(server, "POST", "/skills", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def run(server: LiveServer, tmp_path: Path) -> dict:
    run_id, token = seed_run(server, tmp_path)
    with server.db() as db:
        agent_id = db.get(Run, run_id).agent_id
        other = Agent(name="Otro")
        db.add(other)
        db.commit()
        other_id = other.id
    _skill(server, "revision")
    _skill(server, "ajena", scope="agent", agent_id=other_id)
    prohibida = _skill(server, "prohibida")
    api(
        server, "PUT", f"/agents/{agent_id}/skill-modes", json={"modes": {prohibida["id"]: "never"}}
    )
    return {"id": run_id, "url": mcp_url(server, token)}


def test_use_skill_lists_and_loads_and_records(server: LiveServer, run: dict):
    listing = call(run["url"], "use_skill", {})
    assert "- revision:" in listing
    assert "ajena" not in listing and "prohibida" not in listing
    answer = call(run["url"], "use_skill", {"name": "aos:revision"})  # the CLI's own prefix
    assert "# Skill «revision» (versión 1)" in answer
    assert "- scripts/run.py (ejecutable)" in answer
    assert "Instrucciones de revision." in answer
    folder = Path(answer.split("Carpeta: ", 1)[1].splitlines()[0])
    assert (folder / "scripts" / "run.py").read_text("utf-8") == "print(1)"
    with server.db() as db:
        row = db.scalar(select(RunSkill).where(RunSkill.run_id == run["id"]))
        assert (row.skill_name, row.offered, row.loaded_via) == ("revision", "requested", "tool")
    assert ("use_skill", "revision v1") in events(server, run["id"])


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        ("revision", "reference/guia.md", "Guía de apoyo."),
        ("revision", "../../../etc/passwd", "no es válida"),
        ("revision", "C:/Windows/win.ini", "no es válida"),
        ("revision", "otro.md", "no tiene el fichero «otro.md»"),
        ("ajena", "reference/guia.md", "No tienes ninguna skill llamada «ajena»"),
        ("prohibida", "reference/guia.md", "No tienes ninguna skill llamada «prohibida»"),
    ],
)
def test_read_skill_file_never_leaves_the_visible_skills(
    run: dict, name: str, path: str, expected: str
):
    assert expected in call(run["url"], "read_skill_file", {"name": name, "path": path})


def test_an_unknown_skill_says_which_ones_there_are(run: dict):
    answer = call(run["url"], "use_skill", {"name": "nada"})
    assert "No tienes ninguna skill llamada «nada»" in answer
    assert "revision" in answer
