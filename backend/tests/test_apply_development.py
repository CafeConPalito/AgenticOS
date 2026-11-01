"""Applying «Desarrollo» and copying a pipeline (phase 24, blocks 6 and 7; CA4, CA6, CA8): the
missing agents are created from their templates in one step and one team, and a pipeline is
copied from another project with its agents and stage settings."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import Agent, CliAccount, McpConnection, McpExclusion, SkillMode, Team
from agentic_os.services import pipelines
from agentic_os.services.templates import BY_ID

DEVELOPMENT_AGENTS = [
    "analyst",
    "requirements_validator",
    "software_architect",
    "frontend_developer",
    "backend_developer",
    "data_scientist",
    "qa",
    "devops",
]


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        yield client


def project(api: TestClient, tmp_path: Path, name: str = "Web") -> str:
    folder = tmp_path / name
    folder.mkdir()
    return api.post("/api/projects", json={"name": name, "path": str(folder)}).json()["id"]


def account(api: TestClient, cli: str = "claude") -> str:
    with api.app.state.sessionmaker() as db:
        row = CliAccount(workspace_id=DEFAULT_WORKSPACE, cli=cli, label=f"cuenta {cli}")
        db.add(row)
        db.commit()
        return row.id


def test_the_eight_development_templates_exist_with_their_roles():
    for template_id in DEVELOPMENT_AGENTS:
        assert template_id in BY_ID, template_id
    assert BY_ID["software_architect"].name == "Arquitecto de software"
    assert "set_work_mode" in BY_ID["analyst"].instructions  # it decides about SDD
    assert BY_ID["requirements_validator"].model == "haiku"
    assert BY_ID["devops"].model == "sonnet"
    assert "no inventes un destino" in BY_ID["devops"].instructions
    assert {"developer", "writer", "sales"} <= set(BY_ID)


def test_the_plan_says_which_stages_have_an_agent_and_which_need_one(api: TestClient):
    analyst = api.post("/api/agents", json={"template": "analyst"}).json()
    plan = api.get("/api/pipeline-templates/development/plan").json()
    assert [s["template_id"] for s in plan] == [
        "analyst",
        "requirements_validator",
        "software_architect",
        "frontend_developer",
        "backend_developer",
        "data_scientist",
        "qa",
        "devops",
    ]
    assert plan[0]["agent_id"] == analyst["id"]
    assert all(s["agent_id"] is None for s in plan[1:])
    assert plan[2]["template_name"] == "Arquitecto de software"


def test_applying_creates_the_missing_agents_active_in_one_team(api: TestClient, tmp_path: Path):
    analyst = api.post("/api/agents", json={"template": "analyst"}).json()
    mine = api.post("/api/agents", json={"name": "Mi QA", "role": "QA"}).json()
    project_id = project(api, tmp_path)
    claude = account(api)
    created = api.post(
        f"/api/projects/{project_id}/pipeline/template",
        json={
            "template": "development",
            "assign": {"6": mine["id"]},  # QA: one the person already has
            "create": {"cli": "claude", "account_id": claude, "team_name": "Equipo web"},
        },
    )
    assert created.status_code == 201, created.json()
    stages = {s["name"]: s for s in created.json()["stages"]}
    assert stages["Toma de requisitos"]["agent_id"] == analyst["id"]  # reused
    assert stages["QA"]["agent_id"] == mine["id"]
    assert all(s["agent_id"] for s in stages.values())
    with api.app.state.sessionmaker() as db:
        team = db.scalar(select(Team).where(Team.name == "Equipo web"))
        made = list(db.scalars(select(Agent).where(Agent.team_id == team.id)))
        assert sorted(a.template for a in made) == sorted(
            t for t in DEVELOPMENT_AGENTS if t not in ("analyst", "qa")
        )
        assert all(a.status == "active" and a.account_id == claude for a in made)
        architect = next(a for a in made if a.template == "software_architect")
        assert (architect.cli, architect.model) == ("claude", "opus")


def test_with_another_cli_the_new_agents_take_the_chosen_model_or_its_default(
    api: TestClient, tmp_path: Path
):
    project_id = project(api, tmp_path)
    created = api.post(
        f"/api/projects/{project_id}/pipeline/template",
        json={"template": "development", "create": {"cli": "agy"}},
    )
    assert created.status_code == 201, created.json()
    with api.app.state.sessionmaker() as db:
        made = list(db.scalars(select(Agent)))
        assert len(made) == 8 and all(a.cli == "agy" and a.model == "" for a in made)
        assert db.scalar(select(Team.name)) == "Desarrollo"  # the default team


def test_applying_is_all_or_nothing(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    agy = account(api, "agy")
    refused = api.post(
        f"/api/projects/{project_id}/pipeline/template",
        json={"template": "development", "create": {"cli": "claude", "account_id": agy}},
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "account_cli_mismatch"
    bad_assign = api.post(
        f"/api/projects/{project_id}/pipeline/template",
        json={"template": "development", "assign": {"0": "nope"}, "create": {"cli": "claude"}},
    )
    assert bad_assign.status_code == 422
    with api.app.state.sessionmaker() as db:
        assert db.scalars(select(Agent)).all() == []
        assert db.scalars(select(Team)).all() == []
    assert api.get(f"/api/projects/{project_id}/pipeline").json() is None


def test_without_create_the_stages_with_no_agent_stay_empty(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    created = api.post(
        f"/api/projects/{project_id}/pipeline/template", json={"template": "development"}
    ).json()
    assert all(s["agent_id"] is None for s in created["stages"])


def test_a_pipeline_is_copied_with_its_agents_and_stage_settings(api: TestClient, tmp_path: Path):
    dev = api.post("/api/agents", json={"name": "Dev", "role": "Dev"}).json()
    old = api.post("/api/agents", json={"name": "Viejo", "role": "QA"}).json()
    source = project(api, tmp_path, "Origen")
    body = {
        "name": "Mío",
        "max_rejections": 5,
        "decider_model": "haiku",
        "stages": [
            {"name": "Diseño", "agent_id": dev["id"], "exit_condition": "Solo diseño"},
            {"name": "Código", "agent_id": dev["id"], "requires_review": True},
            {"name": "QA", "agent_id": old["id"], "reject_to": 1},
        ],
    }
    saved = api.put(f"/api/projects/{source}/pipeline", json=body).json()
    first = saved["stages"][0]["id"]
    lib = api.app.state.run_manager.skill_library
    from test_agent_io import _skill_files

    with api.app.state.sessionmaker() as db:
        skill, _ = lib.create(
            db, scope="general", project_id=None, agent_id=None, files=_skill_files("estilo")
        )
        connection = McpConnection(workspace_id=DEFAULT_WORKSPACE, name="github")
        db.add(connection)
        db.flush()
        db.add(SkillMode(skill_id=skill.id, stage_id=first, mode="always"))
        db.add(McpExclusion(connection_id=connection.id, stage_id=first))
        db.get(Agent, old["id"]).archived_at = utcnow()
        db.commit()
        skill_id, connection_id = skill.id, connection.id
    api.post("/api/tasks", json={"project_id": source, "title": "Una tarea del origen"})

    target = project(api, tmp_path, "Destino")
    copied = api.post(f"/api/projects/{target}/pipeline/copy", json={"from_project_id": source})
    assert copied.status_code == 201, copied.json()
    data = copied.json()
    assert (data["name"], data["max_rejections"], data["decider_model"]) == ("Mío", 5, "haiku")
    stages = data["stages"]
    assert [s["name"] for s in stages] == ["Diseño", "Código", "QA"]
    assert [s["agent_id"] for s in stages] == [dev["id"], dev["id"], None]
    assert stages[0]["exit_condition"] == "Solo diseño" and stages[1]["requires_review"]
    assert stages[2]["reject_to_stage_id"] == stages[1]["id"]
    assert data["warnings"] == [{"stage": "QA", "agent": "Viejo"}]
    with api.app.state.sessionmaker() as db:
        new_first = stages[0]["id"]
        assert db.scalar(select(SkillMode.mode).where(SkillMode.stage_id == new_first)) == "always"
        assert (
            db.scalar(select(McpExclusion.connection_id).where(McpExclusion.stage_id == new_first))
            == connection_id
        )
        assert skill_id
    tasks = api.get("/api/tasks", params={"project_id": target}).json()
    assert tasks == [] or all(t["project_id"] != target for t in tasks)

    again = api.post(f"/api/projects/{target}/pipeline/copy", json={"from_project_id": source})
    assert again.json()["detail"]["code"] == "pipeline_exists"
    empty = project(api, tmp_path, "Vacío")
    nothing = api.post(f"/api/projects/{target}/pipeline/copy", json={"from_project_id": empty})
    assert nothing.status_code in (409, 422)
    assert pipelines.TEMPLATES  # the module still exposes its templates
