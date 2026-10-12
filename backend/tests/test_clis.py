import subprocess

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.clis import CliCatalog

AGY_MODELS = "Fetching available models...\ngemini-x-low\tGemini X (Low)\nclaude-y\tClaude Y\n"


class FakeCli:
    """Answers like the real CLIs; counts calls to check caching."""

    def __init__(
        self,
        installed: set[str],
        agy_models: str = AGY_MODELS,
        agy_rc: int = 0,
        claude_auth: str = '{"loggedIn": true, "authMethod": "claude.ai"}',
    ):
        self.installed = installed
        self.agy_models = agy_models
        self.agy_rc = agy_rc
        self.claude_auth = claude_auth
        self.calls: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return f"C:/bin/{name}.exe" if name in self.installed else None

    def run(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        name = argv[0].rsplit("/", 1)[-1].removesuffix(".exe")
        if argv[1:] == ["--version"]:
            out = "2.1.296 (Claude Code)\n" if name == "claude" else "1.3.2\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        if argv[1:] == ["auth", "status"]:
            return subprocess.CompletedProcess(argv, 0, self.claude_auth, "")
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
    assert (claude["logged_in"], agy["logged_in"]) == (True, True)
    assert claude["checked_at"] and agy["checked_at"]


def test_missing_cli_is_reported_without_error(client: TestClient):
    catalog_for(client, FakeCli({"claude"}))
    response = client.get("/api/clis")
    assert response.status_code == 200
    agy = response.json()[1]
    assert agy.pop("checked_at")
    assert agy == {
        "id": "agy",
        "name": "Antigravity CLI",
        "installed": False,
        "path": None,
        "version": None,
        "models": [],
        "models_error": None,
        "logged_in": None,
    }


def test_models_failure_is_reported(client: TestClient):
    catalog_for(client, FakeCli({"agy"}, agy_models="", agy_rc=1))
    agy = client.get("/api/clis").json()[1]
    assert agy["installed"] is True
    assert agy["models"] == []
    assert "not logged in" in agy["models_error"]
    assert agy["logged_in"] is False


@pytest.mark.parametrize(
    ("output", "logged_in"),
    [
        ('{"loggedIn": false}', False),
        ("Error: unknown command auth", None),  # an older Claude Code
        ('{"loggedIn": "yes"}', None),
    ],
)
def test_claude_session_from_auth_status(client: TestClient, output: str, logged_in):
    catalog_for(client, FakeCli({"claude"}, claude_auth=output))
    assert client.get("/api/clis").json()[0]["logged_in"] is logged_in


@pytest.mark.parametrize("refresh", [False, True])
def test_results_are_cached_unless_refreshed(client: TestClient, refresh: bool):
    fake = FakeCli({"claude", "agy"})
    catalog_for(client, fake)
    client.get("/api/clis")
    first = len(fake.calls)
    client.get("/api/clis", params={"refresh": refresh})
    assert len(fake.calls) == (2 * first if refresh else first)


def test_blank_or_failing_version_does_not_break_the_catalog():
    class BrokenVersion(FakeCli):
        def run(self, argv, timeout):
            if argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 1, "\n  \n", "boom")
            return super().run(argv, timeout)

    fake = BrokenVersion({"claude", "agy"})
    infos = CliCatalog(which=fake.which, run=fake.run).list()
    assert [i.installed for i in infos] == [True, True]
    assert [i.version for i in infos] == [None, None]
    assert infos[1].models  # models still listed


def test_clis_are_probed_in_parallel():
    import threading
    import time

    class Slow(FakeCli):
        active = 0
        peak = 0
        lock = threading.Lock()

        def run(self, argv, timeout):
            with Slow.lock:
                Slow.active += 1
                Slow.peak = max(Slow.peak, Slow.active)
            time.sleep(0.2)
            with Slow.lock:
                Slow.active -= 1
            return super().run(argv, timeout)

    fake = Slow({"claude", "agy"})
    CliCatalog(which=fake.which, run=fake.run).list()
    assert Slow.peak == 2
