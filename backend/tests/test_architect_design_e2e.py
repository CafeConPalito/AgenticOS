"""The Architect where it is needed (phase 24, block 8; CA9): designing the team and pipeline of
a project that has none, from that project, and a team of agents without a pipeline. The fake
CLI plays the model; only the API is used."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from live_server import live_server
from test_architect_e2e import converse
from test_architect_team_e2e import tool
from test_scheduler_e2e import Api, settings_for

from agentic_os.models import ArchitectMode
from agentic_os.services.architect import prompts, tools

WRITER = {"name": "Redactor", "role": "Redactor", "cli": "claude", "instructions": "Escribe."}
EDITOR = {"name": "Editor", "role": "Editor", "cli": "claude", "instructions": "Revisa."}


def test_the_team_toolset_has_the_pipeline_templates_and_the_prompt_names_the_project():
    class Backend:
        def mcp_connected(self, run_id: str) -> None: ...
        def call_tool(self, run_id: str, name: str, args: dict) -> str:
            return ""

    def names(toolset: str) -> set[str]:
        return {t.name for t in asyncio.run(tools.build(Backend(), toolset).list_tools())}

    assert "get_pipeline_templates" in names(tools.TEAM)
    assert "get_pipeline_templates" not in names(tools.AGENT)
    with_project = prompts.instructions(None, ArchitectMode.TEAM, "Blog")
    assert "El proyecto elegido es **Blog**" in with_project
    assert "«Desarrollo»" in with_project and "exit_condition" in with_project
    assert "El proyecto elegido" not in prompts.instructions(None, ArchitectMode.TEAM, "")


def test_the_pipeline_of_an_empty_project_is_designed_from_the_project(tmp_path: Path):
    folder = tmp_path / "blog"
    folder.mkdir()
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.client_put("/api/settings/architect", {"cli": "claude"})
        project = api.post("/api/projects", {"name": "Blog", "path": str(folder)})
        conversation = api.post(
            "/api/architect/conversations", {"mode": "team", "project_id": project["id"]}
        )
        assert conversation["title"] == "Equipo y pipeline de Blog"
        templates_out = tmp_path / "templates.json"
        orders = [
            tool("get_pipeline_templates", {}, templates_out),
            tool("set_team", {"name": "Contenidos"}, tmp_path / "a.json"),
            tool("update_sheet", {"patch": WRITER, "agent_ref": "redactor"}, tmp_path / "b.json"),
            tool("update_sheet", {"patch": EDITOR, "agent_ref": "editor"}, tmp_path / "c.json"),
            tool(
                "set_pipeline",
                {
                    "project": "Blog",
                    "stages": [
                        {
                            "name": "Redacción",
                            "agent": "redactor",
                            "exit_condition": "La tarea solo pide un borrador",
                        },
                        {"name": "Edición", "agent": "editor", "requires_review": True},
                    ],
                },
                tmp_path / "d.json",
            ),
            "RESPUESTA: Equipo y pipeline listos",
        ]
        after = converse(api, conversation["id"], "Un blog\n" + "\n".join(orders), replies=1)
        assert after["sheet"]["ready"] is True, after["sheet"]["issues"]
        offered = json.loads(templates_out.read_text(encoding="utf-8"))
        text = json.dumps(offered, ensure_ascii=False)
        assert "Desarrollo" in text and "software_architect" in text

        proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose")
        api.post(f"/api/proposals/{proposal['id']}/approve", {})
        pipeline = api.get(f"/api/projects/{project['id']}/pipeline")
        assert [s["name"] for s in pipeline["stages"]] == ["Redacción", "Edición"]
        assert pipeline["stages"][0]["exit_condition"] == "La tarea solo pide un borrador"


def test_a_team_of_agents_without_a_pipeline_is_a_proposal_too(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.client_put("/api/settings/architect", {"cli": "claude"})
        conversation = api.post("/api/architect/conversations", {"mode": "team"})
        orders = [
            tool("set_team", {"name": "Contenidos"}, tmp_path / "a.json"),
            tool("update_sheet", {"patch": WRITER, "agent_ref": "redactor"}, tmp_path / "b.json"),
            "RESPUESTA: Equipo listo",
        ]
        after = converse(api, conversation["id"], "Un equipo\n" + "\n".join(orders), replies=1)
        assert after["sheet"]["ready"] is True, after["sheet"]["issues"]
        proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose")
        assert proposal["kind"] == "team"
        api.post(f"/api/proposals/{proposal['id']}/approve", {})
        agents = {a["name"]: a for a in api.get("/api/agents")}
        assert agents["Redactor"]["status"] == "active"
        team = next(t for t in api.get("/api/teams") if t["name"] == "Contenidos")
        assert team["agent_ids"] == [agents["Redactor"]["id"]]
