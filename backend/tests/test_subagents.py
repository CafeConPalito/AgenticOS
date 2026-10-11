"""Subagents and subtasks end to end (phase 06): a real backend and the fake CLI in a real
ConPTY. Directives in the task title: `SUBAGENTE: [agente|]prompt`, `SUBTAREA: título`,
`NATIVO: descripción` (see fake_cli.use_tools)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from live_server import live_server
from test_scheduler_e2e import Api, settings_for, wait_until

from agentic_os.models import Run, RunEvent


def seed(api: Api, root, cli: str = "claude", **permissions) -> tuple[str, str]:
    folder = root / f"web-{cli}"
    folder.mkdir(exist_ok=True)
    project = api.post("/api/projects", {"name": f"Web {cli}", "path": str(folder)})["id"]
    agent = api.post("/api/agents", {"name": f"Dev{cli}", "cli": cli, **permissions})["id"]
    return agent, project


def runs_of(api: Api, task_id: str) -> list[dict]:
    return api.get(f"/api/runs?task_id={task_id}")


def test_a_subagent_works_in_parallel_and_reports_to_its_parent(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = seed(api, tmp_path, can_spawn_subagents=True)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "reparto; SUBAGENTE: TERMINA: archivos contados",
            },
        )
        done = api.wait_status(task["id"], "done", "waiting_human", timeout=90)
        assert done["status"] == "done", done
        runs = runs_of(api, task["id"])
        parent = next(r for r in runs if r["parent_run_id"] is None)
        child = next(r for r in runs if r["parent_run_id"] == parent["id"])
        assert child["summary"] == "archivos contados"
        assert child["cwd"] == parent["cwd"] and child["task_id"] == task["id"]
        assert "Resultado del subagente Devclaude: archivos contados" in parent["summary"]

        [root] = api.get(f"/api/tasks/{task['id']}/tree")
        assert (root["kind"], root["id"]) == ("run", parent["id"])
        assert [(c["kind"], c["id"]) for c in root["children"]] == [("run", child["id"])]
        names = [e["name"] for e in api.get(f"/api/runs/{parent['id']}/events")]
        assert "spawn_subagent" in names and "subagent_finished" in names


def test_spawn_subagent_needs_the_permission_and_respects_agy(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = seed(api, tmp_path, "agy", can_spawn_subagents=False)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "solo; SUBAGENTE: hola; TERMINA: ok",
            },
        )
        api.wait_status(task["id"], "done", timeout=90)
        assert len(runs_of(api, task["id"])) == 1  # no child

        api.post("/api/agents", {"name": "Ayudante", "cli": "claude"})
        httpx.patch(
            f"{server.url}/api/agents/{agent}", json={"can_spawn_subagents": True}, timeout=30
        )
        second = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                # Another agy in the same folder is refused; a Claude helper is fine.
                "title": "dos; SUBAGENTE: TERMINA: x; SUBAGENTE: Ayudante|TERMINA: hecho",
            },
        )
        done = api.wait_status(second["id"], "done", timeout=120)
        runs = runs_of(api, second["id"])
        children = [r for r in runs if r["parent_run_id"]]
        assert [(r["agent_name"], r["cli"]) for r in children] == [("Ayudante", "claude")]
        log = tmp_path / "data" / "runs" / f"{done['last_run_id']}.log"
        assert "ya hay un agente de agy trabajando en esta carpeta" in log.read_text(
            "utf-8", errors="replace"
        )


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_native_subagents_show_in_the_tree(tmp_path, cli):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = seed(api, tmp_path, cli)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "nativo; NATIVO: Contar archivos; TERMINA: ok",
            },
        )
        api.wait_status(task["id"], "done", timeout=90)
        [root] = api.get(f"/api/tasks/{task['id']}/tree")
        natives = [c for c in root["children"] if c["kind"] == "native"]
        assert len(natives) == 1, root  # Claude's internal SubagentStop is ignored
        assert "Contar archivos" in natives[0]["label"]
        assert natives[0]["status"] == "done" and natives[0]["ended_at"]


def test_create_subtask_and_the_parent_counts_it(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = seed(api, tmp_path, can_create_tasks=True)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "plan; SUBTAREA: Documentar la API; TERMINA: planificado",
            },
        )
        api.wait_status(task["id"], "done", timeout=90)
        [sub] = api.get(f"/api/tasks?parent_task_id={task['id']}")
        assert (sub["title"], sub["parent_code"], sub["agent_id"]) == (
            "Documentar la API",
            task["code"],
            agent,
        )
        parent = api.task(task["id"])
        assert (parent["subtasks_done"], parent["subtasks_total"]) == (0, 1)
        kinds = [e["kind"] for e in api.get(f"/api/tasks/{task['id']}/events")]
        assert "subtask" in kinds


def test_stopping_the_parent_stops_its_subagents(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = seed(api, tmp_path, can_spawn_subagents=True)
        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": agent, "title": "largo; SUBAGENTE: espera"},
        )
        assert wait_until(lambda: len(runs_of(api, task["id"])) == 2, 60)
        api.post(f"/api/tasks/{task['id']}/cancel")
        assert wait_until(
            lambda: all(
                r["status"] not in ("starting", "running", "intervening")
                for r in runs_of(api, task["id"])
            ),
            60,
        ), runs_of(api, task["id"])


FIXTURES = Path(__file__).parent / "fixtures" / "hooks"


def fixture(name: str) -> tuple[str, dict]:
    data = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return data["event"], data["payload"]


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_native_subagents_from_the_real_hook_payloads(tmp_path, cli):
    """The payloads captured from Claude Code 2.1.296 and agy 1.3.3 (ADR 0010)."""
    with live_server(settings_for(tmp_path)) as server:
        with server.db() as db:
            run = Run(
                agent_name="Dev",
                agent_color="#fff",
                project_name="Web",
                cli=cli,
                prompt="x",
                cwd=str(tmp_path),
                status="exited",
            )
            db.add(run)
            db.commit()
            run_id = run.id
        if cli == "claude":
            start = fixture("claude-SubagentStart")[1]
            sequence = [
                fixture("claude-PreToolUse-Agent"),
                ("SubagentStart", start),
                fixture("claude-SubagentStop-internal"),  # never announced: ignored
                # Its own stop: the real SubagentStop shape with the started agent's id.
                (
                    "SubagentStop",
                    fixture("claude-SubagentStop-internal")[1]
                    | {"agent_id": start["agent_id"], "agent_type": start["agent_type"]},
                ),
            ]
        else:
            sequence = [
                fixture("agy-PreInvocation-main"),
                fixture("agy-PreToolUse-invoke_subagent"),
                fixture("agy-PostToolUse-invoke_subagent"),
                fixture("agy-PreInvocation-subagent-conversation"),
                fixture("agy-Stop-not-fully-idle"),
                ("PreInvocation", fixture("agy-PreInvocation-main")[1] | {"invocationNum": 0}),
            ]
        for event, payload in sequence:
            server.manager.on_hook(run_id, event, payload)
        with server.db() as db:
            events = [
                (e.name, json.loads(e.detail))
                for e in db.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.at)
                if e.name.startswith("subagent_")
            ]
            session_id = db.get(Run, run_id).cli_session_id
        assert [name for name, _ in events] == ["subagent_start", "subagent_stop"]
        assert events[0][1]["id"] == events[1][1]["id"]
        expected = "Contar archivos de la carpeta" if cli == "claude" else "File Reader"
        assert expected in events[0][1]["description"]
        if cli == "agy":  # the subagent's conversation never replaced the run's
            assert session_id == fixture("agy-PreInvocation-main")[1]["conversationId"]
