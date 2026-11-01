"""«Añadir CLI» (phase 23, ADR 0029): the official installer in a terminal, and the new CLI found
without restarting the app."""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.models import Cli
from agentic_os.services import cli_paths, clis
from agentic_os.services.cli_install import powershell_argv

FAKE = Path(__file__).parent / "fixtures" / "fake_installer.py"


def installer(client: TestClient, folder: Path, code: int = 0) -> None:
    client.app.state.installs.argv_for = lambda cli: [
        sys.executable,
        str(FAKE),
        str(folder),
        clis.SPECS[0].executable if cli == Cli.CLAUDE else "agy",
        str(code),
    ]


def finished(client: TestClient, cli: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = client.app.state.installs.get(cli)
        if session is not None and not session.alive:
            with client.websocket_connect(f"/api/clis/{cli}/install/terminal") as ws:
                snapshot = ws.receive_json()
                return {"output": snapshot["data"], "exit": ws.receive_json()}
        time.sleep(0.1)
    raise AssertionError("the installer never ended")


def test_installs_and_the_new_cli_is_found_without_restarting(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    folder = tmp_path / "bin"
    # The installer's folder is where cli_paths looks after the process PATH.
    monkeypatch.setattr(cli_paths, "search_path", lambda: str(folder))
    monkeypatch.setenv("PATH", str(tmp_path / "vacia"))
    installer(client, folder)
    before = {c["id"]: c["installed"] for c in client.get("/api/clis?refresh=true").json()}
    assert before["agy"] is False

    assert client.post("/api/clis/agy/install").status_code == 202
    result = finished(client, "agy")
    assert "Instalación completa" in result["output"]
    assert result["exit"]["code"] == 0
    after = {c["id"]: c["installed"] for c in client.get("/api/clis").json()}
    assert after["agy"] is True


def test_a_failed_installation_says_how_it_ended(client: TestClient, tmp_path: Path):
    installer(client, tmp_path / "bin", code=1)
    client.post("/api/clis/claude/install")
    result = finished(client, "claude")
    assert "Network or DNS issue" in result["output"]
    assert result["exit"]["code"] == 1


def test_each_cli_brings_its_official_installer_on_windows():
    for cli in (Cli.CLAUDE, Cli.AGY):
        found = clis.installer_for(cli)
        if sys.platform != "win32":
            assert found is None
            continue
        assert found is not None
        assert found.command.startswith("irm https://")
        assert found.command.endswith("/install.ps1 | iex")
        assert found.docs_url.startswith("https://")
    assert powershell_argv("irm x | iex") == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "irm x | iex",
    ]


def test_a_cli_without_installer_here_is_refused(client: TestClient):
    client.app.state.installs.argv_for = lambda cli: None
    response = client.post("/api/clis/claude/install")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_installer"
