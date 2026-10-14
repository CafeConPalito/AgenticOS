"""The secondary CLI end to end (phase 10 amendment): a real backend, its scheduler and the fake
CLI. The Claude account of an agent reaches the threshold, its queued task waits for the
person's choice and, after switching, runs with agy and the secondary model."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from live_server import in_process_only, live_server
from test_scheduler_e2e import Api, settings_for, wait_until

from agentic_os.db.base import utcnow
from agentic_os.models import CliAccount
from agentic_os.services import accounts
from agentic_os.services.quota import QuotaWindow


def fill_quota(server, account_id: str, pct: float) -> None:
    now = utcnow()
    with server.db() as db:
        account = db.get(CliAccount, account_id)
        accounts.record_quota(
            account, [QuotaWindow("five_hour", pct, now + timedelta(hours=3))], now
        )
        db.commit()
    server.app.state.scheduler.check_limits(force=True)


@in_process_only
def test_switching_to_the_secondary_cli_runs_the_queue_with_it(tmp_path: Path):
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        folder = tmp_path / "Tienda"
        folder.mkdir()
        project = api.post("/api/projects", {"name": "Tienda", "path": str(folder)})["id"]
        claude = next(a for a in api.get("/api/accounts") if a["cli"] == "claude")
        agy = next(a for a in api.get("/api/accounts") if a["cli"] == "agy")
        dev = api.post(
            "/api/agents",
            {
                "name": "Dev",
                "cli": "claude",
                "model": "opus",
                "fallback_account_id": agy["id"],
                "fallback_model": "gemini-3",
            },
        )["id"]

        fill_quota(server, claude["id"], 93)
        item = next(i for i in api.get("/api/inbox") if i["kind"] == "switch")
        assert len(item["options"]) == 2

        task = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": dev, "title": "uno; TERMINA: hecho"},
        )
        # The queue waits for the person: nothing starts, and the task says why.
        assert not wait_until(lambda: api.task(task["id"])["status"] != "queued", timeout=4)
        assert api.task(task["id"])["blocked"] == "decision"

        api.post(f"/api/inbox/{item['id']}/switch", {"choice": "switch"})
        assert api.get(f"/api/agents/{dev}")["using_fallback"] is True
        home = {a["id"]: a for a in api.get("/api/home")["agents"]}
        assert home[dev]["cli"] == "agy" and home[dev]["using_fallback"] is True

        done = api.wait_status(task["id"], "done")
        run = api.get(f"/api/runs/{done['last_run_id']}")
        assert (run["cli"], run["model"], run["account_id"]) == ("agy", "gemini-3", agy["id"])

        # Back to the main CLI: the next task runs with Claude and the agent's own model.
        api.post(f"/api/agents/{dev}/fallback/clear")
        again = api.post(
            "/api/tasks",
            {"project_id": project, "agent_id": dev, "title": "dos; TERMINA: hecho"},
        )
        done = api.wait_status(again["id"], "done")
        run = api.get(f"/api/runs/{done['last_run_id']}")
        assert (run["cli"], run["model"], run["account_id"]) == ("claude", "opus", claude["id"])
