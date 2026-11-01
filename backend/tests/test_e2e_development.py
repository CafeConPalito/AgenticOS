"""«Desarrollo» end to end (phase 24, block 9; CA7): a new project takes the template, its agents
are created from their templates, and two tasks go through it with the fake CLI in a real ConPTY
and a decider that answers like the model would: a development task from the requirements to
the deployment through the architecture, and one that only asks for requirements and ends after
their validation."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from live_server import in_process_only, live_server
from test_scheduler_e2e import Api, settings_for, wait_until

BRANCH = re.compile(r"^- (?P<id>\S+) · (?P<name>[^:]+): ", re.M)


def decider_runner(argv, timeout, cwd=None, env=None, input=None):
    """Ends the task at the requirements validation when it «solo pide requisitos»; at the fork
    takes Backend for «API», Frontend for «UI» and Datos for «datos»; QA never ends it."""
    prompt = argv[argv.index("-p") + 1]
    title = re.search(r"^Tarea: (.*)$", prompt, re.M).group(1)
    stage = re.search(r"La etapa «([^»]+)»", prompt)
    ends = bool(stage and stage.group(1) == "Validación de requisitos" and "solo" in title)
    wanted = {"Backend": "API" in title, "Frontend": "UI" in title, "Datos": "datos" in title}
    rows = [
        {"id": m["id"], "take": wanted.get(m["name"].strip(), False), "reason": m["name"]}
        for m in BRANCH.finditer(prompt)
    ]
    answer: dict = {"branches": rows}
    if stage:
        answer["exit"] = {"take": ends, "reason": "solo requisitos" if ends else "sigue"}
    out = {
        "type": "result",
        "is_error": False,
        "structured_output": answer,
        "total_cost_usd": 0.0004,
        "usage": {"input_tokens": 400, "output_tokens": 90},
        "modelUsage": {"claude-haiku-5-5": {}},
    }
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(out), stderr="")


def approve_reviews_until_done(api: Api, task_id: str, timeout: float = 300) -> tuple[dict, list]:
    """Approves every human review on the way (validation, architecture, the end)."""
    reviewed: list[str] = []

    def step() -> bool:
        task = api.task(task_id)
        if task["status"] == "review":
            reviewed.append(task["stage_name"])
            api.post(f"/api/tasks/{task_id}/review", {"action": "approve"})
        return task["status"] in ("done", "waiting_human", "cancelled")

    assert wait_until(step, timeout), api.task(task_id)
    return api.task(task_id), reviewed


@in_process_only
def test_a_new_project_with_desarrollo_finishes_a_task_and_ends_another_early(tmp_path: Path):
    folder = tmp_path / "Tienda"
    folder.mkdir()
    with live_server(settings_for(tmp_path)) as server:
        server.app.state.scheduler.deciders._runner = decider_runner
        api = Api(server)
        project = api.post("/api/projects", {"name": "Tienda", "path": str(folder)})["id"]
        plan = api.get("/api/pipeline-templates/development/plan")
        assert all(stage["agent_id"] is None for stage in plan)
        pipeline = api.post(
            f"/api/projects/{project}/pipeline/template",
            {"template": "development", "create": {"cli": "claude"}},
        )
        assert all(s["agent_id"] for s in pipeline["stages"])
        assert len(api.get("/api/agents")) == 8

        full = api.post(
            "/api/tasks",
            {"project_id": project, "title": "endpoint de pedidos en la API; TERMINA: hecho"},
        )
        done, reviewed = approve_reviews_until_done(api, full["id"])
        assert done["status"] == "done", done
        assert done["exit_stage_id"] is None  # it went to the end
        assert reviewed == ["Validación de requisitos", "Arquitectura", "IT / despliegue"]
        runs = api.get(f"/api/runs?project_id={project}")
        stages = {r["stage_name"] for r in runs if r["task_id"] == full["id"]}
        stages |= {
            r["stage_name"] for lane in done["lanes"] for r in runs if r["task_id"] == lane["id"]
        }
        assert stages == {
            "Toma de requisitos",
            "Validación de requisitos",
            "Arquitectura",
            "Backend",
            "QA",
            "IT / despliegue",
        }
        assert sorted(lane["name"] for lane in done["lanes"]) == ["Backend"]

        short = api.post(
            "/api/tasks",
            {"project_id": project, "title": "solo requisitos del login; TERMINA: hecho"},
        )
        ended, reviewed = approve_reviews_until_done(api, short["id"])
        assert ended["status"] == "done", ended
        assert ended["exit_stage_name"] == "Validación de requisitos"
        assert reviewed == ["Validación de requisitos"]  # its own review, no second one
        runs = api.get(f"/api/runs?project_id={project}")
        assert {r["stage_name"] for r in runs if r["task_id"] == short["id"]} == {
            "Toma de requisitos",
            "Validación de requisitos",
        }
        kinds = [e["kind"] for e in api.get(f"/api/tasks/{short['id']}/events")]
        assert "exited" in kinds
