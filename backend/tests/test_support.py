"""Logs to send (phase 20, block 8; CA12): the redacting filter, the zip and its contents."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import McpConnection
from agentic_os.services import redact, support
from agentic_os.services.connections import oauth, secrets

RUN_TOKEN = "Zx9_kq3LmN0pQrStUvWx-yz12345678901234567890"


@pytest.mark.parametrize(
    ("line", "leak"),
    [
        (f'"GET /r/{RUN_TOKEN}/mcp HTTP/1.1" 200', RUN_TOKEN),
        (f'"POST /a/{RUN_TOKEN}/mcp HTTP/1.1" 200', RUN_TOKEN),
        ("GET /api/x?api_key=sk-LEAK123456789&page=2", "LEAK123456789"),
        ("callback?code=AUTHCODE987&state=STATE654", "AUTHCODE987"),
        ("headers={'Authorization': 'Bearer abc.def.ghi'}", "abc.def.ghi"),
        ("Cookie: session=topsecretcookie", "topsecretcookie"),
        ('{"password": "hunter2hunter2"}', "hunter2hunter2"),
        ("token=ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghijklmnopqrstuvwxyz0123"),
        ("key sk-ant-api03-ABCDEFGHIJKLMNOPQRST in text", "ABCDEFGHIJKLMNOPQRST"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk", "eyJzdWIi"),
    ],
    ids=[
        "run",
        "architect",
        "query",
        "oauth-code",
        "bearer",
        "cookie",
        "json",
        "github",
        "anthropic",
        "jwt",
    ],
)
def test_the_patterns_hide_secrets(line: str, leak: str):
    assert leak not in redact.redact(line)
    assert redact.HIDDEN in redact.redact(line)


def test_ordinary_lines_stay_readable():
    for line in (
        "GET /api/agents?status=active&page=2 HTTP/1.1",
        "run_started run_id=4f1c agent=Dev",
        "GET /api/runs/abc/terminal",
    ):
        assert redact.redact(line) == line


def test_the_log_filter_hides_secrets_before_writing(tmp_path: Path):
    path = tmp_path / "test.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.addFilter(redact.RedactingFilter())
    logger = logging.getLogger("redact-test")
    logger.addHandler(handler)
    try:
        # Like uvicorn.access: the URL is an argument of the record.
        logger.warning(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1", "GET", f"/r/{RUN_TOKEN}/mcp", "1.1", 200
        )
        logger.warning("calling %s", "https://x.test/cb?code=SECRETCODE1&ok=1")
    finally:
        logger.removeHandler(handler)
        handler.close()
    text = path.read_text(encoding="utf-8")
    assert RUN_TOKEN not in text and "SECRETCODE1" not in text
    assert "/r/«oculto»/mcp" in text and "ok=1" in text


def test_the_bundle_hides_stored_secrets_emails_and_the_user(client: TestClient, tmp_path: Path):
    data_dir = Path(client.app.state.settings.data_dir)
    with client.app.state.sessionmaker() as db:
        connection = McpConnection(
            workspace_id=DEFAULT_WORKSPACE, name="notion", secret_keys=["TOKEN"]
        )
        db.add(connection)
        db.commit()
        secrets.put(connection.id, "TOKEN", "ntn_STOREDSECRET_42")
        secrets.put(
            connection.id,
            oauth.TOKENS_KEY,
            '{"access_token": "OAUTHACCESS_77", "expires_in": 3600}',
        )
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "backend.log").write_text(
        "\n".join(
            [
                "started ok",
                "connection notion env TOKEN=ntn_STOREDSECRET_42",
                "refresh got OAUTHACCESS_77",
                "user someone@example.com said hi",
                r"opened C:\Users\albano\AppData\Roaming\AgenticOS\agentic-os.db",
                f"GET /r/{RUN_TOKEN}/hook/stop",
            ]
        ),
        encoding="utf-8",
    )
    (logs / "backend.log.1").write_text("older line\n", encoding="utf-8")
    (logs / "desktop.log").write_text("sidecar started pid=42\n", encoding="utf-8")
    # A run's terminal log: never in the bundle.
    (data_dir / "runs").mkdir(exist_ok=True)
    (data_dir / "runs" / "r1.log").write_text("TERMINAL OUTPUT", encoding="utf-8")

    preview = client.get("/api/support/logs").json()
    assert [f["name"] for f in preview["files"]] == [
        "logs/backend.log",
        "logs/backend.log.1",
        "logs/desktop.log",
    ]
    target = tmp_path / "out" / "registros.zip"
    made = client.post("/api/support/logs/bundle", json={"path": str(target)})
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["files"] == [*[f["name"] for f in preview["files"]], "info.txt"]
    assert body["redactions"]["secret"] >= 2
    assert body["redactions"]["email"] == 1

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        everything = "\n".join(archive.read(n).decode("utf-8") for n in names)
    assert sorted(names) == sorted(body["files"])
    for leak in (
        "ntn_STOREDSECRET_42",
        "OAUTHACCESS_77",
        "someone@example.com",
        "albano",
        RUN_TOKEN,
        "TERMINAL OUTPUT",
    ):
        assert leak not in everything, leak
    assert "started ok" in everything and "older line" in everything
    assert r"C:\Users\<usuario>\AppData" in everything
    info = zipfile.ZipFile(target).read("info.txt").decode("utf-8")
    assert "Agentic OS" in info and "Agentes:" in info and "secretos de las conexiones" in info
    assert not list(target.parent.glob("*.part"))


def test_the_bundle_keeps_only_the_newest_lines(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(support, "MAX_LOG_BYTES", 1000)
    logs = Path(client.app.state.settings.data_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "backend.log").write_text(
        "".join(f"line {i:04d}\n" for i in range(500)), encoding="utf-8"
    )
    (logs / "backend.log.1").write_text("never\n", encoding="utf-8")
    target = tmp_path / "r.zip"
    client.post("/api/support/logs/bundle", json={"path": str(target)})
    text = zipfile.ZipFile(target).read("logs/backend.log").decode("utf-8")
    assert "line 0499" in text and "line 0000" not in text
    assert "logs/backend.log.1" not in zipfile.ZipFile(target).namelist()


def test_refuses_a_target_that_is_not_an_absolute_zip(client: TestClient):
    for path in ("relative.zip", "C:/tmp/registros.txt"):
        response = client.post("/api/support/logs/bundle", json={"path": path})
        assert response.status_code == 422
    assert client.post("/api/support/logs/reveal", json={"path": "C:/nope.zip"}).status_code == 404


def test_the_interface_errors_reach_the_log(client: TestClient):
    entries = [
        {"level": "error", "message": f"boom at /r/{RUN_TOKEN}/mcp", "source": "App.tsx:10"},
        {"level": "warn", "message": "slow query"},
    ]
    seen: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record)

    # The app replaces the root handlers when it starts: listen on the logger itself.
    keep = Keep(level=logging.WARNING)
    logging.getLogger("frontend").addHandler(keep)
    try:
        assert client.post("/api/support/client-log", json={"entries": entries}).status_code == 204
    finally:
        logging.getLogger("frontend").removeHandler(keep)
    assert [r.levelno for r in seen] == [logging.ERROR, logging.WARNING]
    too_many = client.post("/api/support/client-log", json={"entries": [entries[0]] * 51})
    assert too_many.status_code == 422


def test_a_zip_is_a_zip(client: TestClient, tmp_path: Path):
    target = tmp_path / "solo-info.zip"
    client.post("/api/support/logs/bundle", json={"path": str(target)})
    with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as archive:
        assert "info.txt" in archive.namelist()
