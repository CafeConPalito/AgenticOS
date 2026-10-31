"""Terminals of the person's own (phase 23, ADR 0029): a CLI opened by hand with an account and
a folder. A run of kind «terminal»: out of Ejecuciones and of the account's limit, in Consumo."""

import json
import sys
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import Run, RunKind, RunStatus
from agentic_os.services.usage import limits

FAKE = Path(__file__).parent / "fixtures" / "fake_terminal_cli.py"


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[TestClient]:
    command = [sys.executable, str(FAKE)]
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        cli_command_overrides={"claude": command, "agy": command},
        check_sessions_at_startup=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def seen(folder: Path, timeout: float = 20) -> dict:
    file = folder / "terminal-seen.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if file.is_file():
            return json.loads(file.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise AssertionError("the CLI never started")


def account(client: TestClient, label: str) -> dict:
    return client.post("/api/accounts", json={"cli": "claude", "label": label}).json()


def test_opens_the_cli_with_the_account_in_the_folder_and_closes_it(
    app_client: TestClient, tmp_path: Path
):
    folder = tmp_path / "cualquier carpeta"
    folder.mkdir()
    work = account(app_client, "Trabajo")
    opened = app_client.post(
        "/api/terminals", json={"cli": "claude", "account_id": work["id"], "cwd": str(folder)}
    )
    assert opened.status_code == 201, opened.text
    run = opened.json()
    assert run["kind"] == "terminal"
    assert run["agent_id"] is None and run["task_id"] is None
    started = seen(folder)
    assert Path(started["cwd"]) == folder
    # Its own account's folder, and only the hooks of the app: no prompt, MCP or instructions.
    assert started["config_dir"] and work["id"] in started["config_dir"]
    assert "--settings" in started["argv"]
    assert not {"--mcp-config", "--append-system-prompt-file", "--tools"} & set(started["argv"])

    assert [t["id"] for t in app_client.get("/api/terminals").json()] == [run["id"]]
    # The view that opens it takes the keyboard, the last one wins, and nothing is interrupted.
    for viewer in ("pestaña-1", "pestaña-2"):
        taken = app_client.post(
            f"/api/runs/{run['id']}/control", json={"action": "take", "client_id": viewer}
        )
        assert taken.status_code == 200, taken.text
        assert taken.json()["status"] == "running"

    # Not in Ejecuciones.
    assert run["id"] not in [r["id"] for r in app_client.get("/api/runs").json()]

    assert app_client.delete(f"/api/terminals/{run['id']}").status_code == 204
    deadline = time.monotonic() + 20
    while app_client.get("/api/terminals").json() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert app_client.get("/api/terminals").json() == []


def test_the_default_account_and_folders_that_do_not_exist(app_client: TestClient, tmp_path: Path):
    missing = app_client.post(
        "/api/terminals", json={"cli": "claude", "cwd": str(tmp_path / "no-existe")}
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["field"] == "cwd"
    other_cli = account(app_client, "Trabajo")
    wrong = app_client.post(
        "/api/terminals",
        json={"cli": "agy", "account_id": other_cli["id"], "cwd": str(tmp_path)},
    )
    assert wrong.status_code == 404
    opened = app_client.post("/api/terminals", json={"cli": "claude", "cwd": str(tmp_path)})
    assert opened.status_code == 201
    app_client.delete(f"/api/terminals/{opened.json()['id']}")


def test_its_usage_shows_in_consumo_but_not_in_the_accounts_limit(app_client: TestClient):
    now = utcnow()
    with app_client.app.state.sessionmaker() as db:
        accounts = app_client.get("/api/accounts").json()
        claude = next(a for a in accounts if a["cli"] == "claude" and a["is_default"])
        for kind, cost in ((RunKind.TERMINAL, 4.0), (RunKind.AGENT, 1.5)):
            db.add(
                Run(
                    workspace_id=DEFAULT_WORKSPACE,
                    kind=kind,
                    agent_name="Terminal" if kind == RunKind.TERMINAL else "Dev",
                    agent_color="#C9D4E8",
                    project_name="",
                    account_id=claude["id"],
                    account_label="",
                    cli="claude",
                    model="",
                    prompt="",
                    cwd=".",
                    status=RunStatus.EXITED,
                    started_at=now - timedelta(minutes=5),
                    ended_at=now,
                    cost_usd=cost,
                )
            )
        db.commit()
        used = limits.used_by_account(db, limits.local_day(now))
    assert used[claude["id"]] == pytest.approx(1.5)
    rows = app_client.get("/api/usage/breakdown", params={"group": "agent"}).json()["rows"]
    costs = {row["name"]: row["cost_usd"] for row in rows}
    assert costs["Terminal"] == pytest.approx(4.0)
    assert costs["Dev"] == pytest.approx(1.5)
