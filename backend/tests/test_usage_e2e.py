"""Usage end to end (phase 07): a real backend and the fake CLI in a real ConPTY. `CONSUMO: n`
writes a model call to the CLI's transcript (in the CLI's own format) and `CUOTA:` shows the
CLI's out-of-quota notice."""

from __future__ import annotations

import pytest
from live_server import live_server
from test_hitl_e2e import pending, setup, wait_item
from test_scheduler_e2e import Api, settings_for, wait_until

PRICE = 0.000002  # fake_cli.PRICE


def usage_of(api: Api, run_id: str) -> dict:
    return api.get(f"/api/runs/{run_id}")["usage"]


@pytest.mark.parametrize("cli", ["claude", "agy"])
def test_usage_goes_live_then_final(tmp_path, cli):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, cli)
        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": agent, "title": "x; CONSUMO: 1000; TERMINA: ok"},
        )
        done = api.wait_status(task["id"], "done")
        run_id = done["last_run_id"]
        assert wait_until(lambda: usage_of(api, run_id)["status"] == "final", 30), usage_of(
            api, run_id
        )
        usage = usage_of(api, run_id)
        if cli == "claude":
            # The exact figures written on close (with Claude's internal call).
            assert usage["source"] == "cost-state"
            assert usage["input_tokens"] == 1100
            assert usage["cost_usd"] == pytest.approx((1100 + 100) * PRICE)
        else:
            assert usage["source"] == "transcript_full"
            assert (usage["input_tokens"], usage["output_tokens"]) == (1000, 100)
            assert usage["cost_usd"] is None
        task_usage = api.task(task["id"])["usage"]
        assert task_usage["input_tokens"] == usage["input_tokens"]
        sessions = api.get("/api/usage/sessions")
        assert [s["run_id"] for s in sessions] == [run_id]


def test_claude_live_cost_from_the_status_line(tmp_path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        run = api.post(
            "/api/runs", {"agent_id": agent, "project_id": project, "prompt": "CONSUMO: 500"}
        )
        assert run["warning"] is None
        assert wait_until(lambda: usage_of(api, run["id"])["cost_usd"] is not None, 30)
        usage = usage_of(api, run["id"])
        assert usage["status"] == "partial"
        assert usage["input_tokens"] == 500
        assert usage["cost_usd"] == pytest.approx(550 * PRICE)
        assert usage["cli_version"] == "9.9"
        # Over the daily limit a manual run still starts, with a warning.
        api.post("/api/runs/" + run["id"] + "/stop")
        assert wait_until(lambda: usage_of(api, run["id"])["status"] == "final", 30)
        response = api.client_put("/api/settings/usage-limits", {"claude_usd": 0.0001})
        assert response["claude_usd"] == 0.0001
        assert [i["kind"] for i in pending(api, "limit")] == ["limit"]
        second = api.post("/api/runs", {"agent_id": agent, "project_id": project, "prompt": "hola"})
        assert second["warning"] == "limit_reached"
        api.post("/api/runs/" + second["id"] + "/stop")


@pytest.mark.parametrize("cli", ["agy", "claude"])
def test_out_of_quota_waits_for_the_person(tmp_path, cli):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, cli)
        task = api.post(
            "/api/tasks", {"project_id": project, "agent_id": agent, "title": "x; CUOTA:"}
        )
        item = wait_item(api, "quota")
        expected = "Quota exhausted" if cli == "agy" else "Usage limit reached"
        assert item["detail"].startswith(expected)
        waiting = api.task(task["id"])
        assert (waiting["status"], waiting["waiting_reason"]) == ("waiting_human", "quota")
        today = api.get("/api/usage/today")
        assert {s["cli"]: s["quota_exhausted"] for s in today["limits"]}[cli] is True

        resumed = api.post(f"/api/inbox/{item['id']}/resume")
        assert resumed["resolution"] == "approved"
        assert api.task(task["id"])["status"] == "running"
        run_id = api.task(task["id"])["active_run_id"]
        events = api.get(f"/api/runs/{run_id}/events")
        assert "quota_exhausted" in [e["name"] for e in events]
        log = tmp_path / "data" / "runs" / f"{run_id}.log"
        assert wait_until(lambda: "RESPUESTA: continúa" in log.read_text("utf-8", "replace"), 30)
        api.post(f"/api/runs/{run_id}/stop")
