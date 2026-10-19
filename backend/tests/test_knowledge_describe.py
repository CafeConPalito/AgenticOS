"""Describing pictures with AI (phase 14, block 7): by a CLI or by a local vision model."""

import hashlib
import json
import shutil
import subprocess
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_knowledge_images import FakeOcr, ocr_ready  # noqa: F401 - a fixture

from agentic_os.models import Run, RunKind
from agentic_os.models.agent import Cli
from agentic_os.services import accounts as account_ops
from agentic_os.services.decider import Usage
from agentic_os.services.knowledge import describe
from agentic_os.services.knowledge.config import KnowledgeSettings
from agentic_os.services.knowledge.describe import (
    CliConfig,
    CliDescriber,
    Description,
    LlamaDescriber,
    parse_agy,
    parse_claude,
)
from agentic_os.services.localmodels import catalog, store
from agentic_os.services.localmodels.catalog import CatalogEntry, RemoteFile
from agentic_os.services.localmodels.llama import LlamaError, LlamaServer
from agentic_os.services.usage import stats

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
DOCS = "/api/knowledge/docs"
CLAUDE_REPLY = {
    "result": "  Gráfico de barras: Enero 412, Febrero 388, Marzo 455.  ",
    "total_cost_usd": 0.00097,
    "usage": {"input_tokens": 4, "output_tokens": 211, "cache_read_input_tokens": 9},
    "modelUsage": {"claude-haiku-5-5": {}},
}
AGY_REPLY = {
    "result": {
        "status": "SUCCESS",
        "response": "Una tabla con tres planes.",
        "usage": {"input_tokens": 24712, "output_tokens": 164, "thinking_tokens": 3},
    }
}


# -------------------------------------------------------------------- the CLI's answers
def test_claude_answers_come_with_their_usage_and_cost():
    result = parse_claude(json.dumps(CLAUDE_REPLY), "haiku")
    assert result.text == "Gráfico de barras: Enero 412, Febrero 388, Marzo 455."
    assert (result.usage.input_tokens, result.usage.output_tokens) == (4, 211)
    assert (result.usage.cache_read_tokens, result.usage.cost_usd) == (9, 0.00097)
    assert result.model == "claude-haiku-5-5" and result.error is None


def test_claude_errors_and_nonsense_are_errors_not_descriptions():
    assert (
        parse_claude(json.dumps({"is_error": True, "result": "sin cuota"}), "h").error
        == "sin cuota"
    )
    assert parse_claude("no es json", "h").error == "Claude Code no devolvió JSON"


def test_agy_answers_come_from_the_response_with_tokens_and_no_cost():
    result = parse_agy(json.dumps(AGY_REPLY), "flash")
    assert result.text == "Una tabla con tres planes." and result.usage.cost_usd is None
    assert (result.usage.input_tokens, result.usage.thinking_tokens) == (24712, 3)
    failed = parse_agy(json.dumps({"result": {"status": "ERROR"}}), "flash")
    assert failed.error == "agy terminó con ERROR"
    assert parse_agy("", "flash").error == "agy no devolvió JSON"


def test_a_description_is_cut_to_a_sane_length():
    long = json.dumps({"result": "palabra " * 1000})
    assert len(parse_claude(long, "h").text) == describe.MAX_CHARS


# --------------------------------------------------------------------- calling the CLI
def make(cli: Cli, runner, db_account) -> CliDescriber:
    config = CliConfig(cli, db_account, "haiku" if cli == Cli.CLAUDE else "flash", ("claude",))
    return CliDescriber(config, {"PATH": "x"}, runner)


@pytest.fixture
def account(client: TestClient):
    with client.app.state.sessionmaker() as db:
        account = account_ops.default_for(db, Cli.CLAUDE)
        db.expunge(account)
        return account


def completed(stdout: str = "", code: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_the_cli_is_asked_to_read_the_picture_from_an_empty_folder(account, tmp_path: Path):
    picture = tmp_path / "grafico.PNG"
    picture.write_bytes(b"png-bytes")
    seen = {}

    def runner(argv, timeout, cwd, env):
        seen.update(argv=argv, cwd=cwd, files=sorted(p.name for p in Path(cwd).iterdir()))
        seen["content"] = (Path(cwd) / "imagen.png").read_bytes()
        return completed(json.dumps(CLAUDE_REPLY))

    result = make(Cli.CLAUDE, runner, account).describe(picture, "«Informe» (p. 3)")
    assert result.text.startswith("Gráfico de barras")
    argv = seen["argv"]
    assert argv[0] == "claude" and argv[1] == "-p"
    assert "imagen.png" in argv[2] and "«Informe» (p. 3)" in argv[2]
    for flag, value in (("--model", "haiku"), ("--tools", "Read"), ("--allowedTools", "Read"),
                        ("--max-budget-usd", "0.10")):  # fmt: skip
        assert argv[argv.index(flag) + 1] == value
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert seen["files"] == ["imagen.png"] and seen["content"] == b"png-bytes"
    assert not Path(seen["cwd"]).exists()  # the temporary folder is gone


def test_agy_gets_no_tool_flags_and_its_text_is_read(account, tmp_path: Path):
    picture = tmp_path / "a.png"
    picture.write_bytes(b"x")
    calls = []
    describer = make(
        Cli.AGY,
        lambda argv, t, cwd, env: calls.append(argv) or completed(json.dumps(AGY_REPLY)),
        account,
    )
    assert describer.describe(picture, "ctx").text == "Una tabla con tres planes."
    assert "--tools" not in calls[0] and calls[0][-2:] == ["--output-format", "json"]


@pytest.mark.parametrize(
    ("runner", "expected"),
    [
        (lambda *a, **k: completed("", 3, "sin sesión"), "sin sesión"),
        (lambda *a, **k: completed("{}", 0), "el CLI no describió la imagen"),
        (lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("c", 1)), "tardó más de"),
        (lambda *a, **k: (_ for _ in ()).throw(OSError("no existe")), "no se pudo lanzar el CLI"),
    ],
)
def test_a_cli_that_fails_gives_an_error_not_an_exception(account, tmp_path, runner, expected):
    picture = tmp_path / "a.png"
    picture.write_bytes(b"x")
    result = make(Cli.CLAUDE, runner, account).describe(picture, "ctx")
    assert result.text == "" and expected in result.error


# ------------------------------------------------------------------ choosing a describer
def test_the_cli_is_resolved_like_the_decider_does(client: TestClient, monkeypatch):
    monkeypatch.setattr(describe, "resolve_executable", lambda cli, overrides: ["fake-" + cli])
    with client.app.state.sessionmaker() as db:
        found = describe.resolve_cli(db, KnowledgeSettings())
        assert isinstance(found, CliConfig)
        assert (found.cli, found.model, found.prefix) == (Cli.CLAUDE, "haiku", ("fake-claude",))
        agy = describe.resolve_cli(db, KnowledgeSettings(describer_cli="agy", describer_model="m"))
        assert (agy.cli, agy.model) == (Cli.AGY, "m")
        monkeypatch.setattr(describe.usage_limits, "blocked", lambda db, account: "límite diario")
        blocked = describe.resolve_cli(db, KnowledgeSettings())
        assert isinstance(blocked, str) and "límite diario" in blocked


def test_the_default_factory_says_why_there_is_no_describer(
    client: TestClient, monkeypatch, tmp_path
):
    data_dir = Path(client.app.state.settings.data_dir)
    factory = describe.default_factory(data_dir, None, lambda *a: None)
    with client.app.state.sessionmaker() as db:
        # Local: nothing downloaded.
        assert factory(db, KnowledgeSettings(describer="local")) == (None, describe.MISSING)
        # CLI: the account cannot be used.
        monkeypatch.setattr(describe, "resolve_executable", lambda cli, overrides: ["c"])
        monkeypatch.setattr(describe.usage_limits, "blocked", lambda db, account: "cuota")
        assert factory(db, KnowledgeSettings()) == (None, describe.BLOCKED)
        monkeypatch.setattr(describe.usage_limits, "blocked", lambda db, account: None)
        describer, notice = factory(db, KnowledgeSettings())
        assert notice is None and isinstance(describer, CliDescriber)


# ----------------------------------------------------------------- the run it records
def fake_describer(account_id: str | None):
    return SimpleNamespace(name="claude:haiku", account_id=account_id)


def test_a_describe_call_is_recorded_as_usage_of_the_project_and_the_account(
    client: TestClient, tmp_path: Path, account
):
    project = client.post("/api/projects", json={"name": "Web", "path": str(tmp_path / "w")})
    (tmp_path / "w").mkdir()
    project = client.post("/api/projects", json={"name": "Web", "path": str(tmp_path / "w")}).json()
    path = tmp_path / "a.md"
    path.write_text("# A\n\nx", encoding="utf-8")
    record = client.post(
        f"{DOCS}/files",
        json={"scope": "project", "project_id": project["id"], "paths": [str(path)]},
    ).json()[0]["doc"]
    result = Description(
        text="Un gráfico",
        usage=Usage(input_tokens=4, output_tokens=211, cost_usd=0.00097),
        model="claude-haiku-5-5",
    )
    with client.app.state.sessionmaker() as db:
        from agentic_os.models import KnowledgeDoc

        doc = db.get(KnowledgeDoc, record["id"])
        describe.record_run(db, doc, fake_describer(account.id), result)
        describe.record_run(
            db, doc, fake_describer(None), result
        )  # a local model: nothing to count
        db.commit()
        runs = db.query(Run).filter_by(kind=RunKind.DESCRIBE).all()
        assert len(runs) == 1
        run = runs[0]
        assert (run.agent_name, run.cli, run.model) == (
            "Describir imágenes",
            "claude",
            "claude-haiku-5-5",
        )
        assert (run.input_tokens, run.output_tokens, run.cost_usd) == (4, 211, 0.00097)
        assert (run.project_id, run.account_id) == (project["id"], account.id)
        # It counts where the consumption is computed, by project and by account…
        today = date.today()
        by_project = stats.totals(stats.runs_between(db, today, today, project_id=project["id"]))
        by_account = stats.totals(stats.runs_between(db, today, today, account_id=account.id))
        assert by_project.cost_usd == by_account.cost_usd == 0.00097
    # …but it is not an agent's run: it is not in the lists.
    assert (
        client.get("/api/runs").json()["items"] == []
        if "items" in client.get("/api/runs").json()
        else (client.get("/api/runs").json() == [])
    )


# ------------------------------------------------------------------ llama-server
def entries(tmp_path: Path):
    """An installed engine and vision model (tiny files, with their manifests)."""
    data_dir = tmp_path / "data"
    files = {"model.gguf": b"m" * 100, "mmproj.gguf": b"p" * 50}
    vision = CatalogEntry(
        "fake-vis",
        catalog.VISION,
        "Fake Vision",
        "mit",
        tuple(RemoteFile(n, len(d), hashlib.sha256(d).hexdigest(), ()) for n, d in files.items()),
        usage={"model": "model.gguf", "projector": "mmproj.gguf"},
    )
    engine = CatalogEntry(
        "fake-engine",
        catalog.ENGINE,
        "Fake engine",
        "mit",
        (RemoteFile("e.zip", 1, "0" * 64, ()),),
        usage={"executable": "bin/llama-server.exe"},
        unpack="e.zip",
    )
    for entry in (vision, engine):
        folder = store.downloaded_folder(data_dir, entry)
        folder.mkdir(parents=True)
    for name, data in files.items():
        (store.downloaded_folder(data_dir, vision) / name).write_bytes(data)
    store.write_manifest(data_dir, vision)
    (store.downloaded_folder(data_dir, engine) / "bin").mkdir()
    (store.downloaded_folder(data_dir, engine) / "bin" / "llama-server.exe").write_bytes(b"MZ")
    store.write_manifest(data_dir, engine)
    return data_dir, engine, vision


class FakeProcess:
    """What `Popen` returns, with a tiny HTTP server behind it playing llama-server."""

    def __init__(self, port: int, dies: bool = False, answer: dict | None = None) -> None:
        self.returncode: int | None = 1 if dies else None
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                reply = json.dumps(
                    answer
                    or {
                        "choices": [{"message": {"content": " Un diagrama de flujo. "}}],
                        "usage": {"prompt_tokens": 388, "completion_tokens": 72},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        if not dies:
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0
        self.server.shutdown()

    kill = terminate

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def llama(tmp_path: Path):
    data_dir, engine, vision = entries(tmp_path)
    started: list[FakeProcess] = []
    argvs: list[list[str]] = []

    def launcher(argv, log_file):
        argvs.append(argv)
        process = FakeProcess(int(argv[argv.index("--port") + 1]))
        started.append(process)
        return process

    server = LlamaServer(
        data_dir, engine, vision, threads=3, idle_seconds=0.3, launcher=launcher,
        memory=lambda: 10**12, reap_every=0.1,
    )  # fmt: skip
    yield SimpleNamespace(server=server, started=started, argvs=argvs, data_dir=data_dir,
                          engine=engine, vision=vision)  # fmt: skip
    server.stop()


def ask(server: LlamaServer) -> dict:
    return server.chat([{"role": "user", "content": "describe"}])


def test_llama_server_starts_on_the_first_picture_and_is_reused(llama):
    assert not llama.server.running
    answer = ask(llama.server)
    assert answer["choices"][0]["message"]["content"].strip() == "Un diagrama de flujo."
    ask(llama.server)
    assert len(llama.started) == 1  # one process for both
    argv = llama.argvs[0]
    assert argv[0].endswith("llama-server.exe") and argv[argv.index("-t") + 1] == "3"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"  # never reachable from outside
    for flag in ("--mmproj", "--no-webui", "--jinja"):
        assert flag in argv
    body = llama.started[0].requests[0]
    assert body["chat_template_kwargs"] == {"enable_thinking": False} and body["max_tokens"] == 300


def test_llama_server_leaves_when_it_has_no_work_and_comes_back(llama):
    ask(llama.server)
    first = llama.started[0]
    deadline = __import__("time").monotonic() + 5
    while llama.server.running and __import__("time").monotonic() < deadline:
        __import__("time").sleep(0.05)
    assert not llama.server.running and first.returncode == 0  # its memory is free again
    ask(llama.server)
    assert len(llama.started) == 2


def test_llama_server_refuses_to_start_without_its_files_or_memory(llama):
    server = LlamaServer(
        llama.data_dir, llama.engine, llama.vision, 2, memory=lambda: 100, reap_every=0.1
    )
    with pytest.raises(LlamaError) as caught:
        ask(server)
    assert caught.value.code == "not_enough_memory" and "MB" in caught.value.message
    server.stop()
    empty = LlamaServer(llama.data_dir / "nowhere", llama.engine, llama.vision, 2, reap_every=0.1)
    with pytest.raises(LlamaError) as caught:
        ask(empty)
    assert caught.value.code == "engine_missing"
    empty.stop()
    shutil.rmtree(store.downloaded_folder(llama.data_dir, llama.vision))
    partial = LlamaServer(llama.data_dir, llama.engine, llama.vision, 2, reap_every=0.1)
    with pytest.raises(LlamaError) as caught:
        ask(partial)
    assert caught.value.code == "model_missing"
    partial.stop()


def test_a_server_that_dies_while_loading_is_an_error_with_its_code(llama):
    server = LlamaServer(
        llama.data_dir,
        llama.engine,
        llama.vision,
        2,
        launcher=lambda argv, log: FakeProcess(int(argv[argv.index("--port") + 1]), dies=True),
        memory=lambda: 10**12,
        reap_every=0.1,
    )
    with pytest.raises(LlamaError) as caught:
        ask(server)
    assert caught.value.code == "start_failed" and "code 1" in caught.value.message
    server.stop()
    broken = LlamaServer(
        llama.data_dir, llama.engine, llama.vision, 2,
        launcher=lambda argv, log: (_ for _ in ()).throw(OSError("access denied")),
        memory=lambda: 10**12, reap_every=0.1,
    )  # fmt: skip
    with pytest.raises(LlamaError) as caught:
        ask(broken)
    assert caught.value.code == "start_failed" and "access denied" in caught.value.message
    broken.stop()


def test_the_local_describer_sends_the_picture_as_a_data_uri(llama, tmp_path: Path):
    picture = tmp_path / "grafico.png"
    picture.write_bytes(b"\x89PNG-bytes")
    describer = LlamaDescriber(llama.server)
    result = describer.describe(picture, "«Informe» (p. 3)")
    assert (result.text, result.error, result.model) == (
        "Un diagrama de flujo.",
        None,
        "local:fake-vis",
    )
    assert (result.usage.input_tokens, result.usage.output_tokens) == (388, 72)
    assert describer.account_id is None  # nothing paid: nothing recorded
    parts = llama.started[0].requests[0]["messages"][0]["content"]
    text = next(p["text"] for p in parts if p["type"] == "text")
    assert "«Informe» (p. 3)" in text and "Lee la imagen" not in text  # no file to read here
    url = next(p["image_url"]["url"] for p in parts if p["type"] == "image_url")
    assert url.startswith("data:image/png;base64,")


def test_the_local_describer_turns_a_server_error_into_a_description_error(llama, tmp_path):
    picture = tmp_path / "a.png"
    picture.write_bytes(b"x")
    shutil.rmtree(store.downloaded_folder(llama.data_dir, llama.engine))
    result = LlamaDescriber(llama.server).describe(picture, "ctx")
    assert result.text == "" and "llama.cpp" in result.error


# ----------------------------------------------------------------------- in the pipeline
class FakeDescriber:
    name = "fake:vision"
    account_id = None

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.seen: list[str] = []

    def describe(self, image: Path, context: str) -> Description:
        self.seen.append(context)
        if self.fail:
            return Description(error="sin cuota")
        return Description(text="Un flujo de tres pasos", model="fake")


def add_report(client: TestClient, tmp_path: Path, **extra) -> dict:
    copy = tmp_path / "docs" / "informe.docx"
    copy.parent.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "informe.docx", copy)
    response = client.post(f"{DOCS}/files", json={"scope": "general", "paths": [str(copy)]})
    record = response.json()[0]["doc"]
    if extra:
        record = client.patch(f"{DOCS}/{record['id']}", json=extra).json()
    return record


def run_with(client: TestClient, describer, notice: str | None = None) -> None:
    service = client.app.state.knowledge
    service.describers = lambda db, limits: (describer, notice)
    service.run_pending(FakeOcr({0: "Emitida Enviada"}))


def test_pictures_are_not_described_unless_asked(client, tmp_path: Path, ocr_ready):
    record = add_report(client, tmp_path)
    describer = FakeDescriber()
    run_with(client, describer)
    assert describer.seen == []
    images = client.get(f"{DOCS}/{record['id']}/images").json()
    assert images[0]["description"] == ""


def test_the_document_flag_asks_for_descriptions_and_they_go_under_the_picture(
    client, tmp_path: Path, ocr_ready
):
    record = add_report(client, tmp_path, describe_images=True)
    describer = FakeDescriber()
    run_with(client, describer)
    assert len(describer.seen) == 1 and "informe" in describer.seen[0]
    text = client.get(f"{DOCS}/{record['id']}/markdown").json()["markdown"]
    assert "Un flujo de tres pasos" in text and "Emitida Enviada" in text
    image = client.get(f"{DOCS}/{record['id']}/images").json()[0]
    assert (image["description"], image["described_by"]) == (
        "Un flujo de tres pasos",
        "fake:vision",
    )
    assert client.get(f"{DOCS}/{record['id']}").json()["notice"] is None


def test_the_global_setting_applies_but_the_document_flag_overrides_it(
    client, tmp_path: Path, ocr_ready
):
    assert client.put("/api/settings/knowledge", json={"describe_images": True}).status_code == 200
    on = add_report(client, tmp_path)
    describer = FakeDescriber()
    run_with(client, describer)
    assert len(describer.seen) == 1
    client.patch(f"{DOCS}/{on['id']}", json={"describe_images": False})
    client.post(f"{DOCS}/{on['id']}/reprocess")
    describer.seen.clear()
    run_with(client, describer)
    assert describer.seen == []
    # Reprocessing without descriptions removes the old ones.
    assert client.get(f"{DOCS}/{on['id']}/images").json()[0]["description"] == ""


def test_no_describer_or_all_calls_failing_is_a_notice_not_a_failure(
    client, tmp_path: Path, ocr_ready
):
    record = add_report(client, tmp_path, describe_images=True)
    run_with(client, None, describe.BLOCKED)
    done = client.get(f"{DOCS}/{record['id']}").json()
    assert (done["status"], done["notice"]) == ("ready", describe.BLOCKED)
    client.post(f"{DOCS}/{record['id']}/reprocess")
    run_with(client, FakeDescriber(fail=True))
    done = client.get(f"{DOCS}/{record['id']}").json()
    assert (done["status"], done["notice"]) == ("ready", describe.FAILED)


# ------------------------------------------------------------------------- the settings
def test_settings_can_be_read_and_changed_in_part(client: TestClient):
    first = client.get("/api/settings/knowledge").json()
    assert first["describe_images"] is False and first["describer"] == "cli"
    changed = client.put(
        "/api/settings/knowledge",
        json={"describe_images": True, "describer": "local", "context_budget": 4000},
    ).json()
    assert (changed["describe_images"], changed["describer"], changed["context_budget"]) == (
        True,
        "local",
        4000,
    )
    assert changed["max_file_mb"] == first["max_file_mb"]
    assert client.get("/api/settings/knowledge").json() == changed


@pytest.mark.parametrize(
    "body",
    [{"concurrency": 99}, {"describer": "cloud"}, {"context_budget": 1}, {"nope": 1}],
)
def test_invalid_settings_are_refused(client: TestClient, body):
    assert client.put("/api/settings/knowledge", json=body).status_code == 422
