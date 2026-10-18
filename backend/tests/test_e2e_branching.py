"""Branching pipelines end to end (phase 13): a real backend, its scheduler, the fake CLI in a
real ConPTY, and a decider that answers like the model would (a fake runner instead of the CLIs'
`-p`). One task goes only to the branches that fit; a rejection reopens only the branch that
failed."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from live_server import in_process_only, live_server
from test_scheduler_e2e import Api, settings_for

BRANCH = re.compile(r"^- (?P<id>\S+) · (?P<name>[^:]+): ", re.M)


def decider_runner(argv, timeout, cwd=None, env=None, input=None):
    """Takes «Backend» if the task's title says API and «Frontend» if it says UI."""
    prompt = argv[argv.index("-p") + 1]
    title = re.search(r"^Tarea: (.*)$", prompt, re.M).group(1)
    wanted = {"Backend": "API" in title, "Frontend": "UI" in title}
    rows = [
        {
            "id": m["id"],
            "take": wanted.get(m["name"].strip(), False),
            "reason": f"{m['name']}: {title[:30]}",
        }
        for m in BRANCH.finditer(prompt)
    ]
    out = {
        "type": "result",
        "is_error": False,
        "structured_output": {"branches": rows},
        "total_cost_usd": 0.0004,
        "usage": {"input_tokens": 400, "output_tokens": 90},
        "modelUsage": {"claude-haiku-5-5": {}},
    }
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(out), stderr="")


def setup(api: Api, tmp_path: Path) -> str:
    folder = tmp_path / "Web"
    folder.mkdir()
    project = api.post("/api/projects", {"name": "Web", "path": str(folder)})["id"]
    for template in ("analyst", "developer", "qa"):
        api.post("/api/agents", {"template": template})
    created = api.post(f"/api/projects/{project}/pipeline/template", {"template": "web_split"})
    assert [s["name"] for s in created["stages"]] == [
        "Requisitos",
        "Dev backend",
        "Dev frontend",
        "QA",
    ]
    assert all(s["agent_id"] for s in created["stages"])  # the template found its agents
    return project


@in_process_only
def test_each_task_goes_only_to_the_branches_that_fit(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        server.app.state.scheduler.deciders._runner = decider_runner
        api = Api(server)
        project = setup(api, tmp_path)
        api.post("/api/scheduler/pause")
        titles = {
            "api": "endpoint de clientes en la API; TERMINA: hecho",
            "ui": "boton de modo oscuro en la UI; TERMINA: hecho",
            "both": "filtro de pedidos en la API y la UI; TERMINA: hecho",
        }
        tasks = {
            key: api.post("/api/tasks", {"project_id": project, "title": title})
            for key, title in titles.items()
        }
        api.post("/api/scheduler/resume")

        done = {
            k: api.wait_status(t["id"], "done", "waiting_human", timeout=240)
            for k, t in tasks.items()
        }
        assert {k: t["status"] for k, t in done.items()} == {
            "api": "done",
            "ui": "done",
            "both": "done",
        }

        lanes = {k: sorted(x["name"] for x in t["lanes"]) for k, t in done.items()}
        assert lanes == {"api": ["Backend"], "ui": ["Frontend"], "both": ["Backend", "Frontend"]}

        for key, task in done.items():
            (decision,) = api.get(f"/api/tasks/{task['id']}/decisions")
            assert decision["decided_by"] == "model" and not decision["proposed"]
            assert any(decision["reasons"].values())  # why each branch was taken or not
            assert task["usage"]["cost_usd"] >= 0.0004  # the decision is part of its consumption
            kinds = [e["kind"] for e in api.get(f"/api/tasks/{task['id']}/events")]
            assert {"decision", "lane_started", "lane_finished", "joined", "done"} <= set(kinds), (
                key
            )

        runs = api.get(f"/api/runs?project_id={project}")
        by_task: dict[str, list[str]] = {}
        for run in runs:
            by_task.setdefault(run["task_id"], []).append(run["stage_name"])
        both_stages = by_task[tasks["both"]["id"]] + [
            r["stage_name"]
            for lane in done["both"]["lanes"]
            for r in runs
            if r["task_id"] == lane["id"]
        ]
        assert sorted(both_stages) == ["Dev backend", "Dev frontend", "QA", "Requisitos"]
        # the decider's calls are not sessions: only the agents' runs are listed
        assert all(r["agent_name"] != "Decisor" for r in runs)

        # their calls do count as usage, under their own name
        usage = api.get("/api/usage/breakdown?group=agent")
        assert "Decisor" in [row["name"] for row in usage["rows"]]


@in_process_only
def test_qa_sends_the_task_back_only_to_the_branch_that_failed(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        server.app.state.scheduler.deciders._runner = decider_runner
        api = Api(server)
        project = setup(api, tmp_path)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "title": "login en la API y la UI; DEVUELVE: Dev backend; "
                "RECHAZA1: falta validar la clave; TERMINA: hecho",
            },
        )
        done = api.wait_status(task["id"], "done", "waiting_human", timeout=240)
        assert done["status"] == "done", done
        assert done["rejections"] == 1

        events = api.get(f"/api/tasks/{task['id']}/events")
        rejected = next(e for e in events if e["kind"] == "rejected")
        assert rejected["stage_name"] == "QA" and "validar la clave" in rejected["detail"]
        started = [e["detail"] for e in events if e["kind"] == "lane_started"]
        assert "backend (reabierta)" in started and "frontend (reabierta)" not in started

        runs = sorted(api.get(f"/api/runs?project_id={project}"), key=lambda r: r["created_at"])
        assert [r["stage_name"] for r in runs] == [
            "Requisitos",
            "Dev backend",
            "Dev frontend",
            "QA",
            "Dev backend",  # only the branch that failed is done again
            "QA",
        ]
        by_lane = {x["name"]: api.get(f"/api/tasks/{x['id']}") for x in done["lanes"]}
        assert by_lane["Backend"]["status"] == by_lane["Frontend"]["status"] == "done"
