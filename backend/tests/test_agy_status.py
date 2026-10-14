"""agy's quota through its status line (phase 10, S2): an opt-in line in agy's global settings that
never overwrites a status line of the person's, never edits the file while agy is open, and
reports to the run through an environment variable."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.errors import ApiError
from agentic_os.models import Run, RunStatus
from agentic_os.services import agy_status

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"
OTHER = {"type": "command", "command": "C:/Users/marta/my-line.sh"}


@pytest.fixture(autouse=True)
def agy_closed(monkeypatch: pytest.MonkeyPatch):
    """No agy process is open unless a test says so (and never look at the real process list)."""
    monkeypatch.setattr(agy_status, "process_running", lambda image: False)


def settings_file(tmp_path: Path, content: dict | None) -> Path:
    path = tmp_path / "agy-settings.json"
    if content is not None:
        path.write_text(json.dumps(content, indent=2), "utf-8")
    return path


def test_the_script_does_nothing_outside_the_app(tmp_path: Path):
    command = agy_status.write_script(tmp_path)
    script = agy_status.script_path(tmp_path)
    text = script.read_text("ascii")
    assert Path(command).name.lower() == script.name.lower()
    # Guarded by the variable only an Agentic OS run sets; reports to it with curl; prints nothing.
    assert agy_status.ENV_URL in text and "curl" in text and "exit" in text
    assert text.index(agy_status.ENV_URL) < text.index("curl")


def test_enable_installs_our_line_next_to_the_rest_and_disable_removes_only_it(tmp_path: Path):
    file = settings_file(tmp_path, {"colorScheme": "dark", "trustedWorkspaces": ["C:/x"]})
    before = agy_status.state(file)
    assert (before.available, before.enabled, before.taken) == (True, False, False)

    after = agy_status.set_enabled(file, tmp_path, True)
    assert after.enabled and not after.taken
    saved = json.loads(file.read_text("utf-8"))
    assert saved["colorScheme"] == "dark" and saved["trustedWorkspaces"] == ["C:/x"]
    line = saved["statusLine"]
    assert line["type"] == "command" and line["stack_with_default"] is True
    assert Path(line["command"]).name.lower() == agy_status.SCRIPT.lower()

    # Turning it on again changes nothing; turning it off removes just that key.
    assert agy_status.set_enabled(file, tmp_path, True).enabled
    off = agy_status.set_enabled(file, tmp_path, False)
    assert not off.enabled
    assert json.loads(file.read_text("utf-8")) == {
        "colorScheme": "dark",
        "trustedWorkspaces": ["C:/x"],
    }


def test_a_status_line_of_the_person_is_never_overwritten(tmp_path: Path):
    file = settings_file(tmp_path, {"statusLine": OTHER})
    current = agy_status.state(file)
    assert current.taken and not current.enabled
    with pytest.raises(ApiError) as error:
        agy_status.set_enabled(file, tmp_path, True)
    assert error.value.status == 409 and error.value.code == "status_line_taken"
    # Turning off what is not ours is a no-op, not a deletion.
    assert agy_status.set_enabled(file, tmp_path, False).taken
    assert json.loads(file.read_text("utf-8"))["statusLine"] == OTHER


def test_the_file_is_left_alone_while_agy_is_open(tmp_path: Path, monkeypatch):
    file = settings_file(tmp_path, {"colorScheme": "dark"})
    monkeypatch.setattr(agy_status, "process_running", lambda image: image == "agy.exe")
    assert agy_status.state(file).running
    with pytest.raises(ApiError) as error:
        agy_status.set_enabled(file, tmp_path, True)
    assert error.value.code == "agy_running"
    assert json.loads(file.read_text("utf-8")) == {"colorScheme": "dark"}


def test_without_a_settings_file_there_is_nothing_to_edit(tmp_path: Path):
    file = settings_file(tmp_path, None)
    assert not agy_status.state(file).available
    with pytest.raises(ApiError) as error:
        agy_status.set_enabled(file, tmp_path, True)
    assert error.value.code == "agy_not_set_up" and not file.exists()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", "utf-8")
    assert not agy_status.state(broken).available  # a file we cannot read is never rewritten
    assert broken.read_text("utf-8") == "{not json"


def test_an_agy_run_gets_the_address_to_report_to(tmp_path: Path):
    from agentic_os.models import Cli, PermissionMode
    from agentic_os.services.adapters import LaunchContext, adapter_for
    from agentic_os.services.runs import launcher

    launcher.shutil.which = lambda name: f"C:/bin/{name}.exe"  # type: ignore[assignment]
    project = tmp_path / "project"
    project.mkdir()
    ctx = LaunchContext(
        run_id="run-1",
        cli=Cli.AGY,
        model="",
        prompt="hola",
        permission_mode=PermissionMode.ASK,
        allowed_tools=(),
        cwd=project,
        run_dir=tmp_path / "runs" / "run-1",
        base_url="http://127.0.0.1:9999",
        token="tok-abc",
        instructions="",
        hook_command="C:/hook.cmd",
    )
    spec = adapter_for(Cli.AGY).prepare(ctx)
    assert spec.env[agy_status.ENV_URL] == "http://127.0.0.1:9999/r/tok-abc/hook/StatusLine"


def test_the_api_turns_it_on_and_off(client: TestClient, settings):
    file = Path(settings.agy_settings_file)
    assert client.get("/api/clis/agy/quota").json() == {
        "available": False,
        "enabled": False,
        "taken": False,
        "running": False,
    }
    refused = client.put("/api/clis/agy/quota", json={"enabled": True})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "agy_not_set_up"

    file.write_text(json.dumps({"colorScheme": "dark"}), "utf-8")
    on = client.put("/api/clis/agy/quota", json={"enabled": True}).json()
    assert (on["available"], on["enabled"], on["taken"]) == (True, True, False)
    assert "statusLine" in json.loads(file.read_text("utf-8"))
    assert client.get("/api/clis/agy/quota").json()["enabled"] is True
    assert client.put("/api/clis/agy/quota", json={"enabled": False}).json()["enabled"] is False
    assert "statusLine" not in json.loads(file.read_text("utf-8"))
    assert client.put("/api/clis/agy/quota", json={"on": True}).status_code == 422


def test_agys_status_line_reaches_the_quota_of_its_account(client: TestClient):
    """The real payload of agy 1.3.5 (evidence S2) posted to the run's hook endpoint."""
    with client.app.state.sessionmaker() as db:
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_name="Gema",
            agent_color="#fff",
            project_name="p",
            cli="agy",
            prompt="hola",
            cwd="C:/p",
            status=RunStatus.RUNNING.value,
            account_id=next(
                a["id"] for a in client.get("/api/accounts").json() if a["cli"] == "agy"
            ),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    token = client.app.state.run_manager.tokens.issue(run_id)

    # The capture's reset times are from the day it was taken: move them ahead so the windows are
    # open whenever the test runs (a window past its reset reads as reset).
    data = json.loads((FIXTURES / "agy-1.3.5-statusline-quota.json").read_text("utf-8"))
    soon = (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for bucket in data["quota"].values():
        bucket["reset_time"] = soon
    payload = json.dumps(data)
    response = client.post(
        f"/r/{token}/hook/StatusLine", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 204

    agy = next(a for a in client.get("/api/accounts").json() if a["cli"] == "agy")
    assert (agy["email"], agy["plan"], agy["name"]) == (
        "user@example.com",
        "Google AI Pro",
        "user@example.com",
    )
    windows = {w["id"]: w for w in agy["quota"]}
    assert set(windows) == {"gemini-5h", "gemini-weekly", "3p-5h", "3p-weekly"}
    assert windows["gemini-5h"]["used_pct"] == pytest.approx(1.72, abs=0.01)
    assert windows["3p-weekly"]["used_pct"] == 0
