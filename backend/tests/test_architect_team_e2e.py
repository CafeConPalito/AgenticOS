"""A team designed by the Architect end to end (phase 19, block 11; CA15): new and reused agents
and a project's pipeline, approved in one go, and a task that goes through every stage. Only
the API is used, so it also runs against the packaged backend."""

from __future__ import annotations

import json
from pathlib import Path

from live_server import live_server
from test_architect_e2e import converse
from test_scheduler_e2e import Api, settings_for


def tool(name: str, args: dict, out: Path) -> str:
    return f"HERRAMIENTA: {name}|{json.dumps(args)}|{out}"


def test_a_team_with_a_pipeline_is_approved_and_a_task_goes_through_it(tmp_path: Path):
    folder = tmp_path / "blog"
    folder.mkdir()
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.client_put("/api/settings/architect", {"cli": "claude"})
        project = api.post("/api/projects", {"name": "Blog", "path": str(folder)})
        api.post("/api/agents", {"name": "QA", "role": "QA", "cli": "claude", "instructions": "x"})
        conversation = api.post("/api/architect/conversations", {"mode": "team"})
        writer = {
            "name": "Redactor",
            "role": "Redactor",
            "cli": "claude",
            "instructions": "Escribe.",
        }
        orders = [
            tool("set_team", {"name": "Contenidos", "description": "Posts"}, tmp_path / "a.json"),
            tool(
                "update_sheet",
                {"patch": writer, "agent_ref": "redactor"},
                tmp_path / "b.json",
            ),
            tool("use_existing_agent", {"name": "QA"}, tmp_path / "c.json"),
            tool(
                "set_pipeline",
                {
                    "project": "Blog",
                    "stages": [
                        {"name": "Redacción", "agent": "redactor"},
                        {"name": "Pruebas", "agent": "QA"},
                    ],
                },
                tmp_path / "d.json",
            ),
            "RESPUESTA: Equipo listo",
        ]
        after = converse(api, conversation["id"], "Un equipo\n" + "\n".join(orders), replies=1)
        assert after["sheet"]["ready"] is True, after["sheet"]["issues"]

        proposal = api.post(f"/api/architect/conversations/{conversation['id']}/propose")
        assert proposal["kind"] == "team"
        review = proposal["team"]
        assert [a["name"] for a in review["new_agents"]] == ["Redactor"]
        assert [a["name"] for a in review["existing_agents"]] == ["QA"]
        assert review["pipeline"]["added"] == ["Redacción", "Pruebas"]

        api.post(f"/api/proposals/{proposal['id']}/approve", {})
        agents = {a["name"]: a for a in api.get("/api/agents")}
        assert agents["Redactor"]["status"] == "active"
        team = next(t for t in api.get("/api/teams") if t["name"] == "Contenidos")
        assert set(team["agent_ids"]) == {agents["Redactor"]["id"], agents["QA"]["id"]}
        pipeline = api.get(f"/api/projects/{project['id']}/pipeline")
        assert [s["name"] for s in pipeline["stages"]] == ["Redacción", "Pruebas"]

        task = api.post(
            "/api/tasks",
            {"project_id": project["id"], "title": "escribe y prueba el post; TERMINA: hecho"},
        )
        done = api.wait_status(task["id"], "done", "waiting_human", timeout=240)
        assert done["status"] == "done", done
