"""Accounts end to end (phase 10): a real backend and the fake CLI in a real ConPTY. Each run
starts with the login folder of its account, and the subscription windows its status line
reports land on that account."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx
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


def test_logging_an_account_in_runs_the_cli_in_a_terminal_and_checks_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Add an account → its login terminal → the CLI writes the login into the account's own
    folder → the app asks again and the account has its email and a live session."""
    from websockets.sync.client import connect

    monkeypatch.setenv("FAKE_CLI_REQUIRE_LOGIN", "1")
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        account = api.post("/api/accounts", {"cli": "claude", "label": "Personal"})
        folder = tmp_path / "data" / "accounts" / account["id"]
        # A new account has no session yet.
        probed = api.post(f"/api/accounts/{account['id']}/probe")
        assert (probed["session_state"], probed["email"]) == ("down", "")

        started = api.post(f"/api/accounts/{account['id']}/login", {"email": "marta@estudio.es"})
        assert started["logging_in"] is True
        # The same call again attaches to the open login instead of starting another.
        assert api.post(f"/api/accounts/{account['id']}/login", {})["logging_in"] is True

        url = server.url.replace("http", "ws") + f"/api/accounts/{account['id']}/login/terminal"
        output = ""
        with connect(f"{url}?client_id=test") as ws:
            while True:
                message = json.loads(ws.recv(timeout=30))
                output += (
                    message.get("data", "") if message["type"] in ("snapshot", "output") else ""
                )
                if message["type"] == "exit":
                    break
        assert "Login successful." in ANSI.sub("", output)
        assert (folder / "fake-login.json").is_file()  # the login landed in the account's folder

        # The session was checked BEFORE the exit was announced: no stale «logged out».
        assert account_named(api, account["id"])["session_state"] == "ok"
        # When the terminal closes, the app checks the session by itself.
        assert wait_until(lambda: account_named(api, account["id"])["session_state"] == "ok", 30), (
            account_named(api, account["id"])
        )
        done = account_named(api, account["id"])
        assert (done["email"], done["name"], done["logging_in"]) == (
            "marta@estudio.es",
            "marta@estudio.es",
            False,
        )
        # No login is open any more: its terminal says so and closes.
        with connect(f"{url}?client_id=again") as ws:
            assert json.loads(ws.recv(timeout=10))["type"] == "exit"


def test_a_login_can_be_cancelled_and_blocks_removing_the_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    settings = settings_for(tmp_path)
    # A CLI that never finishes its login: it prints and waits.
    slow = [sys.executable, "-c", "import time; print('esperando…', flush=True); time.sleep(120)"]
    settings = settings.model_copy(update={"cli_command_overrides": {"claude": slow, "agy": slow}})
    with live_server(settings) as server:
        api = Api(server)
        account = api.post("/api/accounts", {"cli": "claude"})
        api.post(f"/api/accounts/{account['id']}/login", {})
        assert api.get_status(f"/api/accounts/{account['id']}", method="delete") == 409
        assert httpx.delete(f"{server.url}/api/accounts/{account['id']}/login").status_code == 204
        assert wait_until(lambda: not account_named(api, account["id"])["logging_in"], 30)
        assert api.get_status(f"/api/accounts/{account['id']}", method="delete") == 204
