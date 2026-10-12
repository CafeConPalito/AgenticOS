"""«Reanudar sesión» end to end (phase 08): a real backend restarted with a task running, and
the fake CLI continuing its session (`--resume` / `--conversation`) in a real ConPTY."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from live_server import live_server
from test_hitl_e2e import setup
from test_scheduler_e2e import Api, settings_for, wait_until

from agentic_os.models import Run
from agentic_os.services.runs import resume as resume_ops

PRICE = 0.000002  # fake_cli.PRICE


def interrupted_task(tmp_path: Path, cli: str) -> tuple[str, str]:
    """A task whose run was cut by a backend restart: (task id, run id)."""
    settings = settings_for(tmp_path)
    with live_server(settings) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, cli)
        task = api.post(
            "/api/tasks", {"project_id": project, "agent_id": agent, "title": "x; CONSUMO: 1000"}
        )
        api.wait_status(task["id"], "running")
        run_id = api.task(task["id"])["last_run_id"]
        assert wait_until(lambda: api.get(f"/api/runs/{run_id}")["usage"]["input_tokens"] > 0)
    return task["id"], run_id


def attention_items(api: Api, task_id: str) -> list[dict]:
    return [
        i for i in api.get("/api/inbox") if i["task_id"] == task_id and i["kind"] == "attention"
    ]


def hook_names(api: Api, run_id: str) -> list[str]:
    return [e["name"] for e in api.get(f"/api/runs/{run_id}/events") if e["kind"] == "hook"]


def transcript_of(server, run_id: str) -> Path:
    with server.db() as db:
        return Path(db.get(Run, run_id).transcript_path)


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_an_interrupted_task_resumes_its_session(tmp_path: Path, cli: str):
    task_id, old_id = interrupted_task(tmp_path, cli)
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        task = api.task(task_id)
        assert (task["status"], task["waiting_reason"]) == ("waiting_human", "interrupted")
        assert attention_items(api, task_id)
        old = api.get(f"/api/runs/{old_id}")
        assert old["resumable"] is True

        run = api.post(f"/api/runs/{old_id}/resume")

        assert run["resumed_from_id"] == old_id
        assert run["cli_session_id"] == old["cli_session_id"]
        assert run["task_id"] == task_id
        assert api.task(task_id)["status"] == "running"
        assert not attention_items(api, task_id)
        old = api.get(f"/api/runs/{old_id}")
        assert (old["resumed_by_id"], old["resumable"]) == (run["id"], False)
        # Its hooks speak for the resumed conversation (agy: confirmed, not a foreign one), and
        # it answers the resume prompt before the next message is typed.
        assert wait_until(lambda: "Stop" in hook_names(api, run["id"]), 30)

        server.manager.deliver(run["id"], "CONSUMO: 300; TERMINA: listo")
        api.wait_status(task_id, "done")
        assert wait_until(lambda: api.get(f"/api/runs/{run['id']}")["usage"]["status"] == "final")
        usage = api.get(f"/api/runs/{run['id']}")["usage"]
        # Only what the resumed session used, although it writes to the same transcript.
        assert usage["input_tokens"] == 300
        if cli == "claude":
            assert usage["source"] == "cost-state"
            assert usage["cost_usd"] == pytest.approx((300 + 30) * PRICE)
        task_usage = api.task(task_id)["usage"]
        assert task_usage["input_tokens"] == (
            300 + api.get(f"/api/runs/{old_id}")["usage"]["input_tokens"]
        )


def test_a_lost_transcript_cannot_be_resumed(tmp_path: Path):
    task_id, old_id = interrupted_task(tmp_path, "claude")
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        transcript_of(server, old_id).unlink()
        response = httpx.post(f"{server.url}/api/runs/{old_id}/resume", timeout=30)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "session_unavailable"
        assert api.task(task_id)["waiting_reason"] == "interrupted"


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_a_cli_without_the_conversation_fails_the_resumed_run(
    tmp_path: Path, cli: str, monkeypatch: pytest.MonkeyPatch
):
    task_id, old_id = interrupted_task(tmp_path, cli)
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        transcript_of(server, old_id).unlink()
        # The transcript was there when checked, and gone when the CLI started.
        monkeypatch.setattr(resume_ops, "check", lambda db, run, transcript: {"offset": 0})

        run = api.post(f"/api/runs/{old_id}/resume")

        assert wait_until(lambda: api.get(f"/api/runs/{run['id']}")["status"] == "failed", 30)
        assert api.get(f"/api/runs/{run['id']}")["error"] == "session_missing"
        task = api.wait_status(task_id, "waiting_human")
        assert task["waiting_reason"] == "run_failed"
        assert api.get(f"/api/runs/{run['id']}")["resumable"] is False
