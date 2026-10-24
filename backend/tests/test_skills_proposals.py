"""Skills the agents propose (phase 17, block 5) through the real MCP server: CA9 (a proposal waits
in the Inbox, invisible, until approved), CA10 (limits and reasons in words), CA11 (a new version
changes nothing until approved) and CA13 (no approval with unopened scripts)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from sqlalchemy import select
from test_mcp_server import call, events, mcp_url, seed_run

from agentic_os.config import Settings
from agentic_os.models import InboxItem, Run, SkillRejection

BODY = "# Migraciones\n1. Genera con autogenerate.\n2. Revisa el downgrade.\n"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def api(server: LiveServer, method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{server.url}/api{path}", timeout=60, **kwargs)


def new_run(server: LiveServer, tmp_path: Path) -> dict:
    """A run of a new agent in a new project (each seed needs its own folder)."""
    folder = tmp_path / f"p{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    run_id, token = seed_run(server, folder)
    with server.db() as db:
        agent_id = db.get(Run, run_id).agent_id
    return {"id": run_id, "url": mcp_url(server, token), "agent": agent_id}


def propose(run: dict, **args) -> str:
    defaults = {
        "name": "migraciones-alembic",
        "description": "Migraciones de Alembic.",
        "body": BODY,
    }
    return call(run["url"], "propose_skill", {**defaults, **args})


def pending(server: LiveServer) -> list[dict]:
    return api(server, "GET", "/skills/proposals/pending").json()


def test_a_proposal_waits_in_the_inbox_and_nobody_sees_it(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path)
    answer = propose(run, files={"scripts/check.py": "print(1)"}, note="Lo aprendí hoy")
    assert "Propuesta registrada: la skill «migraciones-alembic»" in answer
    [proposal] = pending(server)
    assert proposal["new_skill"] is True
    assert proposal["skill"]["review"] == "proposed" and proposal["skill"]["scope"] == "agent"
    assert proposal["skill"]["agent_id"] == run["agent"]
    assert proposal["executables"] == ["scripts/check.py"]
    assert proposal["version"]["author"]["kind"] == "agent"
    assert proposal["version"]["note"] == "Lo aprendí hoy"
    items = api(server, "GET", "/inbox").json()
    item = next(i for i in items if i["kind"] == "skill")
    assert item["skill_version_id"] == proposal["version"]["id"]
    assert item["title"] == "Skill propuesta: migraciones-alembic"
    assert "ejecutable" in item["detail"]
    other = new_run(server, tmp_path)
    assert "No tienes skills disponibles" in call(other["url"], "use_skill", {})
    assert ("propose_skill", "migraciones-alembic → propuesta (de agente)") in events(
        server, run["id"]
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"name": "Migraciones Alembic"}, "solo minúsculas"),
        ({"description": ""}, "Falta la descripción"),
        ({"files": {"../fuera.py": "x"}}, "no es válida"),
        ({"files": {"SKILL.md": "x"}}, "va en `name`"),
        ({"level": "galaxia"}, "`level` debe ser"),
        ({"replaces": "no-existe"}, "no tienes ninguna skill llamada «no-existe»"),
    ],
)
def test_bad_proposals_are_refused_in_words(server: LiveServer, tmp_path: Path, args, expected):
    run = new_run(server, tmp_path)
    assert expected in propose(run, **args)
    assert pending(server) == []


def test_one_proposal_per_run_by_default_and_a_switch_to_turn_them_off(
    server: LiveServer, tmp_path: Path
):
    run = new_run(server, tmp_path)
    propose(run)
    assert "el máximo es 1" in propose(run, name="otra-skill", description="Otra cosa.")
    api(server, "PUT", "/settings/skills", json={"proposals_enabled": False})
    assert "desactivadas" in propose(new_run(server, tmp_path), name="tercera")


def test_copies_taken_names_and_rejected_ones_are_refused(server: LiveServer, tmp_path: Path):
    api(
        server,
        "POST",
        "/skills",
        json={
            "scope": "general",
            "name": "migraciones-alembic",
            "description": "Migraciones de Alembic.",
            "body": BODY,
        },
    )
    copy = propose(new_run(server, tmp_path))
    assert "Ya hay una skill igual: «migraciones-alembic» (ya existe)" in copy
    taken = propose(new_run(server, tmp_path), body="Otro cuerpo distinto.", level="general")
    assert "Ya hay una skill llamada «migraciones-alembic»" in taken and "`replaces`" in taken
    run = new_run(server, tmp_path)
    propose(run, name="informes", description="Informes semanales.", body="Cuerpo.")
    [proposal] = pending(server)
    api(
        server,
        "POST",
        f"/skills/proposals/{proposal['version']['id']}/reject",
        json={"reason": "No la necesitamos"},
    )
    again = propose(
        new_run(server, tmp_path),
        name="informes",
        description="Informes semanales.",
        body="Cuerpo.",
    )
    assert "La persona ya rechazó una skill muy parecida («informes»" in again
    assert "Motivo: No la necesitamos" in again


def test_approving_with_scripts_needs_them_opened_and_keeps_the_edits(
    server: LiveServer, tmp_path: Path
):
    run = new_run(server, tmp_path)
    propose(run, files={"scripts/check.py": "print(1)", "reference/notas.md": "N"})
    [proposal] = pending(server)
    version = proposal["version"]["id"]
    refused = api(server, "POST", f"/skills/proposals/{version}/accept", json={})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "scripts_not_opened"
    assert refused.json()["detail"]["files"] == ["scripts/check.py"]
    accepted = api(
        server,
        "POST",
        f"/skills/proposals/{version}/accept",
        json={
            "opened_files": ["scripts/check.py"],
            "description": "Migraciones de Alembic, revisadas por la persona.",
            "files": {"reference/notas.md": None},
            "scope": "general",
        },
    )
    assert accepted.status_code == 200, accepted.text
    skill = accepted.json()
    assert (skill["review"], skill["scope"], skill["origin"], skill["version"]) == (
        "none",
        "general",
        "agent",
        1,
    )
    assert skill["description"] == "Migraciones de Alembic, revisadas por la persona."
    assert {f["path"] for f in skill["file_list"]} == {"SKILL.md", "scripts/check.py"}
    versions = api(server, "GET", f"/skills/{skill['id']}/versions").json()
    assert versions[0]["note"].endswith("editada al aprobar")
    assert versions[0]["author"] == {
        "kind": "agent",
        "label": "Dev",
        "agent_id": run["agent"],
        "run_id": run["id"],
        "task_id": None,
        "task_title": "",
    }
    resolved = api(server, "GET", "/inbox", params={"status": "resolved"}).json()
    item = next(i for i in resolved if i["kind"] == "skill")
    assert item["resolution"] == "approved"
    # now the next run gets it
    assert "migraciones-alembic" in call(new_run(server, tmp_path)["url"], "use_skill", {})


def test_a_new_version_changes_nothing_until_approved(server: LiveServer, tmp_path: Path):
    created = api(
        server,
        "POST",
        "/skills",
        json={
            "scope": "general",
            "name": "revision",
            "description": "Revisar ramas.",
            "body": "v1",
        },
    ).json()
    run = new_run(server, tmp_path)
    answer = call(
        run["url"],
        "propose_skill",
        {"replaces": "revision", "body": "v2 con más pasos", "note": "Añado pasos"},
    )
    assert "una versión nueva de «revision»" in answer
    [proposal] = pending(server)
    assert proposal["new_skill"] is False
    assert api(server, "GET", f"/skills/{created['id']}").json()["body"].strip() == "v1"
    diff = api(
        server,
        "GET",
        f"/skills/{created['id']}/diff",
        params={"to": proposal["version"]["id"]},
    ).json()
    lines = [line["text"] for f in diff["files"] for h in f["diff"]["hunks"] for line in h["lines"]]
    assert "v2 con más pasos" in lines and "v1" in lines
    # a new version keeps the level
    bad = api(
        server,
        "POST",
        f"/skills/proposals/{proposal['version']['id']}/accept",
        json={"scope": "agent", "agent_id": run["agent"]},
    )
    assert bad.json()["detail"]["code"] == "level_mismatch"
    ok = api(server, "POST", f"/skills/proposals/{proposal['version']['id']}/accept", json={})
    assert ok.json()["version"] == 2 and ok.json()["body"].strip() == "v2 con más pasos"


def test_rejecting_a_new_version_leaves_the_skill_and_drops_its_files(
    server: LiveServer, tmp_path: Path
):
    created = api(
        server,
        "POST",
        "/skills",
        json={
            "scope": "general",
            "name": "revision",
            "description": "Revisar ramas.",
            "body": "v1",
        },
    ).json()
    run = new_run(server, tmp_path)
    call(run["url"], "propose_skill", {"replaces": "revision", "body": "v2"})
    [proposal] = pending(server)
    response = api(server, "POST", f"/skills/proposals/{proposal['version']['id']}/reject", json={})
    assert response.status_code == 204
    skill = api(server, "GET", f"/skills/{created['id']}").json()
    assert (skill["version"], skill["body"].strip()) == (1, "v1")
    versions = api(server, "GET", f"/skills/{created['id']}/versions").json()
    assert [(v["number"], v["status"], v["files"]) for v in versions] == [
        (2, "rejected", 0),
        (1, "accepted", 1),
    ]
    with server.db() as db:
        assert db.scalar(select(SkillRejection.name)) == "revision"
        item = db.scalar(select(InboxItem).where(InboxItem.kind == "skill"))
        assert item.resolution == "rejected"


def test_rejecting_a_new_skill_deletes_it(server: LiveServer, tmp_path: Path):
    propose(new_run(server, tmp_path))
    [proposal] = pending(server)
    api(server, "POST", f"/skills/proposals/{proposal['version']['id']}/reject", json={})
    assert api(server, "GET", "/skills").json() == []
    again = api(server, "POST", f"/skills/proposals/{proposal['version']['id']}/accept", json={})
    assert again.status_code == 404 or again.json()["detail"]["code"] == "not_proposed"
