"""Human in the loop end to end (phase 06): a real backend, the scheduler and the fake CLI in a
real ConPTY. The fake reads directives from the task title: `PREGUNTA: …` calls request_human,
`PERMISO: …` shows the CLI's permission dialog (Claude's or agy's real texts)."""

from __future__ import annotations

import json

import httpx
import pytest
from live_server import live_server
from test_scheduler_e2e import Api, settings_for, wait_until
from websockets.sync.client import connect


def setup(api: Api, root, cli: str) -> tuple[str, str]:
    folder = root / f"web-{cli}"
    folder.mkdir()
    project = api.post("/api/projects", {"name": f"Web {cli}", "path": str(folder)})["id"]
    agent = api.post("/api/agents", {"name": f"Dev {cli}", "cli": cli})["id"]
    return agent, project


def pending(api: Api, kind: str) -> list[dict]:
    return [i for i in api.get("/api/inbox") if i["kind"] == kind]


def wait_item(api: Api, kind: str) -> dict:
    assert wait_until(lambda: pending(api, kind), 60), api.get("/api/inbox")
    return pending(api, kind)[0]


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_a_question_is_answered_from_the_inbox(tmp_path, cli):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, cli)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "base de datos; PREGUNTA: ¿Postgres o SQLite?|Postgres|SQLite",
            },
        )
        item = wait_item(api, "question")
        assert (item["title"], item["options"]) == ("¿Postgres o SQLite?", ["Postgres", "SQLite"])
        assert (item["task_code"], item["agent_name"]) == (task["code"], f"Dev {cli}")
        waiting = api.task(task["id"])
        assert (waiting["status"], waiting["waiting_reason"]) == ("waiting_human", "human_request")
        assert api.get("/api/inbox/summary")["pending"] == 1

        answered = api.post(f"/api/inbox/{item['id']}/answer", {"text": "SQLite"})
        assert (answered["status"], answered["response"]) == ("resolved", "SQLite")
        done = api.wait_status(task["id"], "done")
        run = api.get(f"/api/runs/{done['last_run_id']}")
        assert "Respuesta de la persona a «¿Postgres o SQLite?»: SQLite" in run["summary"]
        kinds = [e["kind"] for e in api.get(f"/api/tasks/{task['id']}/events")]
        assert "human_request" in kinds and "human_answered" in kinds
        assert len(pending(api, "delivery")) == 1  # «Tarea completada»


@pytest.mark.parametrize(("cli", "approve"), [("claude", True), ("agy", False)])
def test_a_permission_dialog_is_answered_from_the_inbox(tmp_path, cli, approve):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, cli)
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "publicar; PERMISO: git push; TERMINA: listo",
            },
        )
        item = wait_item(api, "approval")
        expected = "Bash: git push" if cli == "claude" else "git push"
        assert item["command"] == expected
        waiting = api.task(task["id"])
        assert (waiting["status"], waiting["waiting_reason"]) == ("waiting_human", "permission")

        action = "approve" if approve else "reject"
        resolved = api.post(f"/api/inbox/{item['id']}/{action}")
        assert resolved["resolution"] == ("approved" if approve else "rejected")
        api.wait_status(task["id"], "done")
        events = api.get(f"/api/runs/{api.task(task['id'])['last_run_id']}/events")
        names = [e["name"] for e in events]
        assert "permission_requested" in names and "permission_answered" in names
        log = tmp_path / "data" / "runs" / f"{api.task(task['id'])['last_run_id']}.log"
        text = log.read_text("utf-8", errors="replace")
        assert ("Ran git push" in text) is approve


def test_a_dialog_answered_in_the_terminal_resolves_its_item(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": agent, "title": "x; PERMISO: rm -rf build"},
        )
        item = wait_item(api, "approval")
        run_id = api.task(task["id"])["active_run_id"]
        # The person takes the control (no Esc over the dialog) and approves in the terminal.
        api.post(f"/api/runs/{run_id}/control", {"action": "take", "client_id": "me"})
        url = server.url.replace("http", "ws") + f"/api/runs/{run_id}/terminal?client_id=me"
        with connect(url, open_timeout=10) as ws:
            ws.send(json.dumps({"type": "input", "data": "\r"}))
            assert wait_until(
                lambda: (
                    api.get("/api/inbox?status=resolved")
                    and api.get("/api/inbox?status=resolved")[0]["id"] == item["id"]
                ),
                30,
            )
        resolved = api.get("/api/inbox?status=resolved")[0]
        assert resolved["resolution"] == "answered_in_terminal"
        assert api.task(task["id"])["status"] == "running"
        conflict = httpx.post(f"{server.url}/api/inbox/{item['id']}/approve", timeout=30)
        assert conflict.status_code == 409
