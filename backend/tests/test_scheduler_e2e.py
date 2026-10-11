"""Tasks end to end: a real backend, its scheduler and the fake CLI in a real ConPTY (phase 05).

The fake CLI reads directives from the task title (see fake_cli.use_tools): `TERMINA: x`
completes, `CONTEXTO: <file>` saves what get_context returns, `SALE: n` exits with n.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server

from agentic_os.config import Settings

FAKE = str(Path(__file__).with_name("fake_cli.py"))


def settings_for(tmp_path: Path) -> Settings:
    command = [sys.executable, FAKE]
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        cli_command_overrides={"claude": command, "agy": command},
    )


def wait_until(check: Callable[[], bool], timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.2)
    return False


class Api:
    def __init__(self, server: LiveServer) -> None:
        self.url = server.url

    def get(self, path: str):
        return httpx.get(self.url + path, timeout=30).json()

    def post(self, path: str, body: dict | None = None):
        response = httpx.post(self.url + path, json=body, timeout=30)
        assert response.status_code < 300, response.text
        return response.json()

    def task(self, task_id: str) -> dict:
        return self.get(f"/api/tasks/{task_id}")

    def wait_status(self, task_id: str, *statuses: str, timeout: float = 60) -> dict:
        assert wait_until(lambda: self.task(task_id)["status"] in statuses, timeout), self.task(
            task_id
        )
        return self.task(task_id)


def seed(api: Api, root: Path, name: str, cli: str = "claude") -> tuple[str, str]:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    project = api.post("/api/projects", {"name": name, "path": str(folder)})
    agents = {a["name"]: a["id"] for a in api.get("/api/agents")}
    agent_id = (
        agents.get("Dev")
        or api.post("/api/agents", {"name": "Dev", "role": "Desarrollador", "cli": cli})["id"]
    )
    return agent_id, project["id"]


def test_one_agent_works_through_tasks_of_two_projects(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.post("/api/scheduler/pause")  # both tasks queued before anything starts
        dev, tienda = seed(api, tmp_path, "Tienda")
        _, blog = seed(api, tmp_path, "Blog")
        api.post(f"/api/projects/{tienda}/memory", {"text": "Secreto de la tienda"})
        api.post(f"/api/projects/{blog}/memory", {"text": "Secreto del blog"})
        ctx_a, ctx_b = tmp_path / "ctx-a.txt", tmp_path / "ctx-b.txt"
        first = api.post(
            "/api/tasks",
            {
                "project_id": tienda,
                "agent_id": dev,
                "title": f"carrito; CONTEXTO: {ctx_a}; TERMINA: carrito hecho",
                "description": "El carrito pierde los productos.",
            },
        )
        second = api.post(
            "/api/tasks",
            {
                "project_id": blog,
                "agent_id": dev,
                "title": f"rss; CONTEXTO: {ctx_b}; TERMINA: rss hecho",
            },
        )
        assert api.get(f"/api/agents/{dev}")["queued_count"] == 2
        api.post("/api/scheduler/resume")

        done_a = api.wait_status(first["id"], "done")
        done_b = api.wait_status(second["id"], "done")

        # One after the other (concurrency 1), each in its own fresh session.
        run_a, run_b = (
            api.get(f"/api/runs/{done_a['last_run_id']}"),
            api.get(f"/api/runs/{done_b['last_run_id']}"),
        )
        assert run_a["status"] == run_b["status"] == "completed"
        assert run_a["ended_at"] <= run_b["started_at"]
        assert run_a["summary"] == "carrito hecho" and run_a["task_id"] == first["id"]
        assert run_b["cwd"] == str((tmp_path / "Blog").resolve())

        # No context is shared between projects.
        a, b = ctx_a.read_text("utf-8"), ctx_b.read_text("utf-8")
        assert "# Proyecto: Tienda" in a and "Secreto de la tienda" in a
        assert "Secreto del blog" not in a and "T-2" not in a
        assert "# Tarea T-1: carrito" in a and "El carrito pierde los productos." in a
        assert "# Proyecto: Blog" in b and "Secreto del blog" in b
        assert "Secreto de la tienda" not in b and "# Tarea T-2: rss" in b

        kinds = [e["kind"] for e in api.get(f"/api/tasks/{first['id']}/events")]
        assert kinds == ["created", "queued", "stage_started", "stage_completed", "done"]
        assert api.get(f"/api/agents/{dev}")["queued_count"] == 0


def test_failures_manual_completion_and_cancel(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        api.post("/api/scheduler/pause")
        dev, web = seed(api, tmp_path, "Web")
        _, blog = seed(api, tmp_path, "Blog")
        failing = api.post(
            "/api/tasks", {"project_id": web, "agent_id": dev, "title": "rompe; SALE: 3"}
        )
        silent = api.post(  # the model never calls complete_task
            "/api/tasks", {"project_id": blog, "agent_id": dev, "title": "no termina"}
        )
        api.post("/api/scheduler/resume")

        waiting = api.wait_status(failing["id"], "waiting_human")
        assert (waiting["waiting_reason"], waiting["waiting_detail"]) == (
            "run_exited",
            "exit code 3",
        )

        # The agent goes on with its queue; that run stays open, idle.
        running = api.wait_status(silent["id"], "running")
        run_id = running["active_run_id"]
        assert wait_until(lambda: api.get(f"/api/runs/{run_id}")["activity"] == "idle")
        done = api.post(f"/api/tasks/{silent['id']}/complete", {"summary": "Lo doy por hecho"})
        assert done["status"] == "running"  # it moves on once its run has closed
        done = api.wait_status(silent["id"], "done")
        assert api.get(f"/api/runs/{run_id}")["status"] == "stopped"
        events = api.get(f"/api/tasks/{silent['id']}/events")
        assert ("completed_manually", "Lo doy por hecho") in [
            (e["kind"], e["detail"]) for e in events
        ]

        # Retry the failed task, then cancel it while it runs.
        api.post(f"/api/tasks/{failing['id']}/retry")
        api.wait_status(failing["id"], "running", "waiting_human")
        cancelled = api.post(f"/api/tasks/{failing['id']}/cancel")
        assert cancelled["status"] == "cancelled"


@pytest.mark.parametrize("cli", ["claude"])
def test_a_restart_leaves_the_running_task_waiting(tmp_path: Path, cli: str):
    settings = settings_for(tmp_path)
    with live_server(settings) as server:
        api = Api(server)
        dev, web = seed(api, tmp_path, "Web", cli)
        task = api.post("/api/tasks", {"project_id": web, "agent_id": dev, "title": "larga"})
        api.wait_status(task["id"], "running")
    with live_server(settings) as server:
        api = Api(server)
        task = api.task(task["id"])
        assert (task["status"], task["waiting_reason"]) == ("waiting_human", "interrupted")
        assert api.get(f"/api/runs/{task['last_run_id']}")["status"] in ("stopped", "interrupted")


def test_a_pipeline_with_a_rejection_and_an_agy_stage(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        folder = tmp_path / "Web"
        folder.mkdir()
        project = api.post("/api/projects", {"name": "Web", "path": str(folder)})["id"]
        ana = api.post("/api/agents", {"name": "Ana", "cli": "claude"})["id"]
        dev = api.post("/api/agents", {"name": "Dev", "cli": "claude"})["id"]
        gema = api.post("/api/agents", {"name": "Gema", "cli": "agy"})["id"]
        api_put = httpx.put(
            f"{server.url}/api/projects/{project}/pipeline",
            json={
                "name": "Desarrollo web",
                "stages": [
                    {"name": "Requisitos", "agent_id": ana},
                    {"name": "Desarrollo", "agent_id": dev},
                    {"name": "QA", "agent_id": gema, "reject_to": 1},
                ],
            },
            timeout=30,
        )
        assert api_put.status_code == 200, api_put.text
        ctx = tmp_path / "ctx-dev.txt"
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "title": f"login; CONTEXTO: {ctx}; RECHAZA1: falta el test del callback; "
                "TERMINA: hecho",
            },
        )
        done = api.wait_status(task["id"], "done", "waiting_human", timeout=180)
        assert done["status"] == "done", done
        assert done["rejections"] == 1

        events = api.get(f"/api/tasks/{task['id']}/events")
        steps = [
            (e["kind"], e["stage_name"])
            for e in events
            if e["kind"] in ("stage_completed", "rejected", "done")
        ]
        assert steps == [
            ("stage_completed", "Requisitos"),
            ("stage_completed", "Desarrollo"),
            ("rejected", "QA"),
            ("stage_completed", "Desarrollo"),
            ("stage_completed", "QA"),
            ("done", "QA"),
        ]
        rejected = next(e for e in events if e["kind"] == "rejected")
        assert rejected["detail"] == "falta el test del callback"
        assert rejected["agent_name"] == "Gema"

        runs = api.get(f"/api/runs?project_id={project}")
        assert sorted(r["agent_name"] for r in runs) == ["Ana", "Dev", "Dev", "Gema", "Gema"]
        assert {r["verdict"] for r in runs if r["agent_name"] == "Gema"} == {"rejected", "approved"}
        # Every stage writes the context file: the last one is the second QA run's, which
        # carries the whole history (the reason reaching Desarrollo is unit-tested).
        last_qa = ctx.read_text("utf-8")
        assert "Etapa 3 de 3: QA" in last_qa and 'verdict="rejected"' in last_qa
        assert "- QA · Gema rechazó: falta el test del callback" in last_qa
        assert not (folder / ".agents" / "plugins" / "agentic-os").exists()
