"""Accounts end to end (phase 10): a real backend and the fake CLI in a real ConPTY. Each run
starts with the login folder of its account, and the subscription windows its status line
reports land on that account."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from live_server import in_process_only, live_server
from test_scheduler_e2e import Api, settings_for, wait_until


def log_of(tmp_path: Path, run_id: str) -> str:
    log = tmp_path / "data" / "runs" / f"{run_id}.log"
    return log.read_text("utf-8", "replace") if log.exists() else ""


ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def screen_text(tmp_path: Path, run_id: str) -> str:
    """The run's log without the terminal's escape sequences."""
    return ANSI.sub("", log_of(tmp_path, run_id))


def claude_account(api: Api) -> dict:
    return next(a for a in api.get("/api/accounts") if a["cli"] == "claude" and a["is_system"])


def account_named(api: Api, account_id: str) -> dict:
    return next(a for a in api.get("/api/accounts") if a["id"] == account_id)


def test_a_run_uses_its_accounts_folder_and_its_quota_lands_on_that_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FAKE_CLI_SHOW_CONFIG", "1")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    resets = int(time.time()) + 3600
    monkeypatch.setenv(
        "FAKE_CLI_RATE_LIMITS",
        json.dumps(
            {
                "five_hour": {"used_percentage": 96, "resets_at": resets},
                "seven_day": {"used_percentage": 40, "resets_at": resets + 86400},
            }
        ),
    )
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        project = tmp_path / "web"
        project.mkdir()
        project_id = api.post("/api/projects", {"name": "Web", "path": str(project)})["id"]
        account = api.post("/api/accounts", {"cli": "claude", "label": "Personal"})
        folder = tmp_path / "data" / "accounts" / account["id"]
        own = api.post("/api/agents", {"name": "Propio", "account_id": account["id"]})
        plain = api.post("/api/agents", {"name": "Normal"})

        first = api.post(
            "/api/runs", {"agent_id": own["id"], "project_id": project_id, "prompt": "CONSUMO: 500"}
        )
        assert (first["account_id"], first["account_label"]) == (account["id"], "Personal")
        assert wait_until(lambda: f"CONFIG_DIR={folder}" in log_of(tmp_path, first["id"]), 30)
        # The windows its status line reported are on the account it ran with…
        assert wait_until(lambda: account_named(api, account["id"])["quota"], 30)
        quota = {w["id"]: w for w in account_named(api, account["id"])["quota"]}
        assert quota["five_hour"]["used_pct"] == 96 and not quota["five_hour"]["expired"]
        assert quota["seven_day"]["used_pct"] == 40

        # …and a run with no account of its own uses the system one: no folder added, and the
        # quota stays on the system account, not on the other.
        second = api.post(
            "/api/runs",
            {"agent_id": plain["id"], "project_id": project_id, "prompt": "CONSUMO: 500"},
        )
        system = next(
            a for a in api.get("/api/accounts") if a["cli"] == "claude" and a["is_system"]
        )
        assert second["account_id"] == system["id"]
        assert wait_until(lambda: "CONFIG_DIR=" in screen_text(tmp_path, second["id"]), 30)
        assert str(tmp_path / "data" / "accounts") not in screen_text(tmp_path, second["id"])
        assert wait_until(lambda: account_named(api, system["id"])["quota"], 30)

        # Each account lists who works with it.
        assert [a["name"] for a in account_named(api, account["id"])["agents"]] == ["Propio"]
        assert [a["name"] for a in account_named(api, system["id"])["agents"]] == ["Normal"]
        assert account_named(api, account["id"])["live_runs"] == 1
        busy = api.get_status(f"/api/accounts/{account['id']}", method="delete")
        assert busy == 409  # a live run keeps its account (and its agent does too)

        for run in (first, second):
            api.post(f"/api/runs/{run['id']}/stop")


@in_process_only
def test_the_session_check_at_startup_finds_a_logged_out_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FAKE_CLI_AUTH", "down")
    settings = settings_for(tmp_path).model_copy(update={"check_sessions_at_startup": True})
    with live_server(settings) as server:
        api = Api(server)
        assert claude_account(api)["session_state"] in ("unknown", "down")
        # The check runs in the background right after the start.
        assert wait_until(lambda: claude_account(api)["session_state"] == "down", 30)
        # Nobody used the account yet: no notice. Once an agent does, the next check raises it.
        assert [i for i in api.get("/api/inbox") if i["kind"] == "account"] == []
        api.post("/api/agents", {"name": "Dev"})
        api.post(f"/api/accounts/{claude_account(api)['id']}/probe")
        notices = [i for i in api.get("/api/inbox") if i["kind"] == "account"]
        assert len(notices) == 1 and "Claude Code" in notices[0]["title"]
