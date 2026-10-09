import subprocess

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.clis import CliCatalog

AGY_MODELS = "Fetching available models...\ngemini-x-low\tGemini X (Low)\nclaude-y\tClaude Y\n"


class FakeCli:
    """Answers like the real CLIs; counts calls to check caching."""

    def __init__(self, installed: set[str], agy_models: str = AGY_MODELS, agy_rc: int = 0):
        self.installed = installed
        self.agy_models = agy_models
        self.agy_rc = agy_rc
        self.calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return f"C:/bin/{name}.exe" if name in self.installed else None

    def run(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        name = argv[0].rsplit("/", 1)[-1].removesuffix(".exe")
        if argv[1:] == ["--version"]:
            out = "2.1.296 (Claude Code)\n" if name == "claude" else "1.3.2\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        if argv[1:] == ["models"]:
            return subprocess.CompletedProcess(argv, self.agy_rc, self.agy_models, "not logged in")
        raise AssertionError(argv)


def catalog_for(client: TestClient, fake: FakeCli) -> CliCatalog:
    catalog = CliCatalog(which=fake.which, run=fake.run)
    client.app.state.cli_catalog = catalog
    return catalog


def test_both_installed(client: TestClient):
    catalog_for(client, FakeCli({"claude", "agy"}))
    claude, agy = client.get("/api/clis").json()
    assert claude["id"] == "claude" and claude["installed"] is True
    assert claude["version"] == "2.1.296 (Claude Code)"
    assert [m["id"] for m in claude["models"]] == ["sonnet", "opus", "haiku"]
    assert agy["version"] == "1.3.2"
    assert agy["models"] == [
        {"id": "gemini-x-low", "label": "Gemini X (Low)"},
        {"id": "claude-y", "label": "Claude Y"},
    ]
    assert agy["models_error"] is None


def test_missing_cli_is_reported_without_error(client: TestClient):
    catalog_for(client, FakeCli({"claude"}))
    response = client.get("/api/clis")
    assert response.status_code == 200
    agy = response.json()[1]
    assert agy == {
        "id": "agy",
        "name": "Antigravity CLI",
        "installed": False,
        "path": None,
        "version": None,
        "models": [],
        "models_error": None,
    }


def test_models_failure_is_reported(client: TestClient):
    catalog_for(client, FakeCli({"agy"}, agy_models="", agy_rc=1))
    agy = client.get("/api/clis").json()[1]
    assert agy["installed"] is True
    assert agy["models"] == []
    assert "not logged in" in agy["models_error"]


@pytest.mark.parametrize("refresh", [False, True])
def test_results_are_cached_unless_refreshed(client: TestClient, refresh: bool):
    fake = FakeCli({"claude", "agy"})
    catalog_for(client, fake)
    client.get("/api/clis")
    first = len(fake.calls)
    client.get("/api/clis", params={"refresh": refresh})
    assert len(fake.calls) == (2 * first if refresh else first)
