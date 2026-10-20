"""Local models and engines (phase 14, block 3): the catalog, resumable checked downloads, the
choice of model for each job, and their API."""

import hashlib
import io
import re
import threading
import time
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agentic_os.api import local_models as models_api
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels import downloads as dl
from agentic_os.services.localmodels.catalog import CatalogEntry, RemoteFile
from agentic_os.services.localmodels.downloads import DownloadError, DownloadManager


# ------------------------------------------------------------------------- a test server
class Server:
    """Serves `files[path]` with Range support, and can misbehave on purpose."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.requests: list[tuple[str, str | None, str | None]] = []  # path, Range, Authorization
        self.cut_at: int | None = None  # close the connection after this many body bytes
        self.ignore_range = False
        self.pause = 0.0  # seconds between 64 KB blocks
        self.statuses: dict[str, int] = {}
        self.url = ""

    def count(self, path: str) -> int:
        return sum(1 for p, _, _ in self.requests if p == path)


@pytest.fixture
def server() -> Iterator[Server]:
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            wanted = self.headers.get("Range")
            state.requests.append((self.path, wanted, self.headers.get("Authorization")))
            if self.path in state.statuses:
                self.send_response(state.statuses[self.path])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = state.files.get(self.path)
            if body is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start = 0
            code = 200
            if wanted and not state.ignore_range:
                start = int(re.match(r"bytes=(\d+)-", wanted).group(1))
                code = 206
            chunk = body[start:]
            self.send_response(code)
            self.send_header("Content-Length", str(len(chunk)))
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
            self.end_headers()
            sent = 0
            try:
                while sent < len(chunk):
                    if state.cut_at is not None and sent >= state.cut_at:
                        self.connection.close()
                        return
                    block = chunk[sent : sent + 65536]
                    self.wfile.write(block)
                    sent += len(block)
                    if state.pause:
                        time.sleep(state.pause)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{httpd.server_port}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield state
    finally:
        httpd.shutdown()


def blob(size: int, seed: int = 0) -> bytes:
    return (hashlib.sha256(str(seed).encode()).digest() * (size // 32 + 1))[:size]


def make_entry(server: Server, files: dict[str, bytes], **options) -> CatalogEntry:
    remote = []
    for name, data in files.items():
        server.files["/" + name] = data
        remote.append(
            RemoteFile(name, len(data), hashlib.sha256(data).hexdigest(), (f"{server.url}/{name}",))
        )
    return CatalogEntry(
        options.pop("entry_id", "fake"),
        options.pop("kind", catalog.EMBEDDING),
        "Fake",
        "mit",
        tuple(remote),
        **options,
    )


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[DownloadManager]:
    events = KnowledgeEvents()
    events.seen = []
    events.publish = events.seen.append
    manager = DownloadManager(tmp_path / "data", events)
    try:
        yield manager
    finally:
        manager.stop()


def run(manager: DownloadManager, entry: CatalogEntry):
    manager.start(entry)
    manager.join(entry)
    return manager.state(entry)


# ------------------------------------------------------------------------------ catalog
def test_every_catalog_entry_is_pinned():
    ids = [e.id for e in catalog.CATALOG]
    assert len(ids) == len(set(ids))
    for entry in catalog.CATALOG:
        assert entry.files and entry.size > 0
        for f in entry.files:
            assert re.fullmatch(r"[0-9a-f]{64}", f.sha256), (entry.id, f.name)
            assert f.size > 0 and f.urls and all(u.startswith("https://") for u in f.urls)
            for url in f.urls:
                if "huggingface.co" in url:  # an exact revision, never a branch that may move
                    assert re.search(r"/resolve/[0-9a-f]{40}/", url), url
        assert entry.unpack is None or entry.unpack in {f.name for f in entry.files}


def test_each_job_has_one_default_and_the_known_models():
    for kind in (catalog.EMBEDDING, catalog.OCR, catalog.VISION):
        assert sum(1 for e in catalog.of_kind(kind) if e.default) == 1
    assert catalog.default_of(catalog.EMBEDDING).id == "e5-small"
    assert catalog.default_of(catalog.VISION).id == "gemma4-e2b"
    assert {e.id for e in catalog.of_kind(catalog.EMBEDDING)} == {
        "e5-small",
        "embeddinggemma-2",
        "bge-m3",
    }
    assert {e.id for e in catalog.of_kind(catalog.VISION)} == {
        "gemma4-e2b",
        "qwen3.5-2b",
        "qwen3.5-4b",
    }
    assert catalog.entry("llama-cpp").unpack and catalog.entry("llama-cpp").folder == "engines"
    assert catalog.entry("e5-small").folder == "models"
    assert catalog.entry("nope") is None


def test_the_downloads_total_matches_what_the_spikes_measured():
    assert round(catalog.entry("e5-small").size / 1e6) == 135
    assert round(catalog.entry("ocr-latin").size / 1e6) == 18
    assert round(catalog.entry("llama-cpp").size / 1e6) == 20


# ------------------------------------------------------------------------- downloading
def test_a_download_completes_checks_and_installs(manager: DownloadManager, server: Server):
    entry = make_entry(server, {"onnx/model.bin": blob(300_000, 1), "tokenizer.json": blob(900, 2)})
    assert manager.state(entry).state == "absent"
    state = run(manager, entry)
    assert (state.state, state.done, state.total) == ("ready", entry.size, entry.size)
    folder = store.folder_of(manager.data_dir, entry)
    assert (folder / "onnx" / "model.bin").read_bytes() == server.files["/onnx/model.bin"]
    assert not list(folder.rglob("*.part"))
    assert store.is_installed(manager.data_dir, entry)
    events = [e for e in manager.events.seen if e["type"] == "model" and e["id"] == "fake"]
    assert events[0]["state"] == "downloading" and events[-1]["state"] == "ready"
    assert any(0 < e["done"] < e["total"] for e in events) or len(events) >= 2


def test_a_file_that_is_not_the_expected_one_is_rejected(manager: DownloadManager, server: Server):
    entry = make_entry(server, {"model.bin": blob(5000, 1)})
    server.files["/model.bin"] = blob(5000, 99)  # same size, other content
    state = run(manager, entry)
    assert (state.state, state.error_code) == ("error", "checksum")
    folder = store.folder_of(manager.data_dir, entry)
    assert not (folder / "model.bin").exists() and not (folder / "model.bin.part").exists()
    assert not store.is_installed(manager.data_dir, entry)


def test_an_interrupted_download_continues_where_it_stopped(
    manager: DownloadManager, server: Server
):
    data = blob(3 * 1024 * 1024, 7)
    entry = make_entry(server, {"big.bin": data})
    server.cut_at = 1_200_000
    first = run(manager, entry)
    assert (first.state, first.error_code) == ("error", "network")
    part = store.folder_of(manager.data_dir, entry) / "big.bin.part"
    kept = part.stat().st_size
    assert 0 < kept < len(data)
    assert manager.state(entry).state == "error"  # the failure is remembered in this run

    server.cut_at = None
    server.requests.clear()
    done = run(manager, entry)
    assert done.state == "ready"
    assert server.requests[0][1] == f"bytes={kept}-"  # it asked only for the rest
    assert (store.folder_of(manager.data_dir, entry) / "big.bin").read_bytes() == data


def test_after_a_restart_an_interrupted_download_shows_as_partial(
    manager: DownloadManager, server: Server
):
    data = blob(2 * 1024 * 1024, 3)
    entry = make_entry(server, {"big.bin": data})
    server.cut_at = 1_100_000
    run(manager, entry)
    fresh = DownloadManager(manager.data_dir, manager.events)  # another run of the app
    state = fresh.state(entry)
    assert state.state == "partial" and 0 < state.done < state.total


def test_a_server_that_ignores_range_restarts_the_file(manager: DownloadManager, server: Server):
    data = blob(2 * 1024 * 1024, 4)
    entry = make_entry(server, {"big.bin": data})
    folder = store.folder_of(manager.data_dir, entry)
    folder.mkdir(parents=True)
    (folder / "big.bin.part").write_bytes(data[:500_000])
    server.ignore_range = True
    assert run(manager, entry).state == "ready"
    assert (folder / "big.bin").read_bytes() == data


def test_cancelling_keeps_the_partial_file_and_a_new_start_continues(
    manager: DownloadManager, server: Server
):
    data = blob(4 * 1024 * 1024, 5)
    entry = make_entry(server, {"big.bin": data})
    server.pause = 0.02
    manager.start(entry)
    deadline = time.monotonic() + 15
    part = store.folder_of(manager.data_dir, entry) / "big.bin.part"
    while (not part.exists() or part.stat().st_size < 1_100_000) and time.monotonic() < deadline:
        time.sleep(0.05)
    manager.cancel(entry)
    manager.join(entry)
    state = manager.state(entry)
    assert state.state == "partial" and state.error_code is None  # not a failure
    server.pause = 0
    assert run(manager, entry).state == "ready"


def test_an_address_that_fails_falls_back_to_the_next(manager: DownloadManager, server: Server):
    data = blob(4000, 6)
    server.files["/mirror.bin"] = data
    entry = CatalogEntry(
        "fake",
        catalog.EMBEDDING,
        "Fake",
        "mit",
        (
            RemoteFile(
                "model.bin",
                len(data),
                hashlib.sha256(data).hexdigest(),
                (f"{server.url}/missing.bin", f"{server.url}/mirror.bin"),
            ),
        ),
    )
    assert run(manager, entry).state == "ready"
    assert server.count("/missing.bin") == 1 and server.count("/mirror.bin") == 1


@pytest.mark.parametrize("code", [404, 500, 503])
def test_an_http_error_is_reported_with_its_code(
    manager: DownloadManager, server: Server, code: int
):
    entry = make_entry(server, {"model.bin": blob(1000, 1)})
    server.statuses["/model.bin"] = code
    state = run(manager, entry)
    assert (state.state, state.error_code) == ("error", f"http_{code}")


def test_it_refuses_to_start_without_room_on_the_disk(
    manager: DownloadManager, server: Server, monkeypatch: pytest.MonkeyPatch
):
    entry = make_entry(server, {"model.bin": blob(5000, 1)})
    monkeypatch.setattr(dl.shutil, "disk_usage", lambda _: SimpleNamespace(free=1000))
    state = run(manager, entry)
    assert (state.state, state.error_code) == ("error", "no_space")
    assert server.requests == []  # nothing was asked of the server


def test_a_file_left_complete_by_an_earlier_attempt_is_not_downloaded_again(
    manager: DownloadManager, server: Server
):
    first, second = blob(3000, 1), blob(3000, 2)
    entry = make_entry(server, {"a.bin": first, "b.bin": second})
    folder = store.folder_of(manager.data_dir, entry)
    folder.mkdir(parents=True)
    (folder / "a.bin").write_bytes(first)  # the manifest never got written
    assert run(manager, entry).state == "ready"
    assert server.count("/a.bin") == 0 and server.count("/b.bin") == 1


def test_starting_twice_is_refused_and_a_ready_model_can_be_removed(
    manager: DownloadManager, server: Server
):
    entry = make_entry(server, {"big.bin": blob(3 * 1024 * 1024, 8)})
    server.pause = 0.05
    manager.start(entry)
    with pytest.raises(DownloadError) as caught:
        manager.start(entry)
    assert caught.value.code == "already_downloading"
    with pytest.raises(DownloadError) as caught:
        manager.remove(entry)
    assert caught.value.code == "downloading"
    manager.cancel(entry)
    manager.join(entry)
    server.pause = 0
    run(manager, entry)
    manager.remove(entry)
    assert manager.state(entry).state == "absent"
    assert not store.folder_of(manager.data_dir, entry).exists()


def test_the_token_goes_only_to_hugging_face_and_only_when_asked(manager: DownloadManager):
    manager._token = lambda: "hf_secret"
    free = make_entry(Server(), {"x": b"1"})
    locked = make_entry(Server(), {"x": b"1"}, needs_account=True)
    hub, other = "https://huggingface.co/a/b/resolve/x/f", "https://example.com/f"
    assert "Authorization" not in manager._headers(hub, free, 0)
    assert manager._headers(hub, locked, 0)["Authorization"] == "Bearer hf_secret"
    assert "Authorization" not in manager._headers(other, locked, 0)
    assert manager._headers(other, locked, 10)["Range"] == "bytes=10-"


# ---------------------------------------------------------------------------- engines
def zipped(**members: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name.replace("__", "/"), data)
    return buffer.getvalue()


def test_an_engine_is_unpacked_and_its_archive_removed(manager: DownloadManager, server: Server):
    archive = zipped(**{"llama-server.exe": b"MZ", "ggml.dll": b"x", "sub__lib.dll": b"y"})
    entry = make_entry(
        server,
        {"engine.zip": archive},
        entry_id="engine",
        kind=catalog.ENGINE,
        unpack="engine.zip",
        usage={"executable": "bin/llama-server.exe"},
    )
    assert run(manager, entry).state == "ready"
    folder = store.folder_of(manager.data_dir, entry)
    assert (folder / "bin" / "llama-server.exe").read_bytes() == b"MZ"
    assert (folder / "bin" / "sub" / "lib.dll").is_file()
    assert not (folder / "engine.zip").exists()
    assert store.executable(manager.data_dir, entry) == folder / "bin" / "llama-server.exe"
    assert store.is_installed(manager.data_dir, entry)


def test_an_archive_that_escapes_its_folder_is_refused(manager: DownloadManager, server: Server):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("../escaped.txt", "no")
        bundle.writestr("llama-server.exe", "MZ")
    entry = make_entry(
        server,
        {"engine.zip": buffer.getvalue()},
        entry_id="engine",
        kind=catalog.ENGINE,
        unpack="engine.zip",
        usage={"executable": "bin/llama-server.exe"},
    )
    state = run(manager, entry)
    assert (state.state, state.error_code) == ("error", "unpack")
    assert not (manager.data_dir / "engines" / "escaped.txt").exists()
    assert not store.is_installed(manager.data_dir, entry)


# ------------------------------------------------------------------------------ choice
def test_each_job_uses_its_default_until_the_user_chooses(client: TestClient):
    with client.app.state.sessionmaker() as db:
        assert selection.chosen(db) == {
            "embedding": "e5-small",
            "ocr": "ocr-latin",
            "vision": "gemma4-e2b",
        }
        selection.choose(db, "embedding", "bge-m3")
        selection.choose(db, "vision", "qwen3.5-2b")
        db.commit()
        assert selection.chosen(db)["embedding"] == "bge-m3"
        selection.choose(db, "embedding", None)  # back to the default
        db.commit()
        assert selection.chosen(db)["embedding"] == "e5-small"
        with pytest.raises(ValueError):
            selection.choose(db, "embedding", "qwen3.5-2b")  # a vision model
        with pytest.raises(ValueError):
            selection.choose(db, "engine", "llama-cpp")  # an engine has no job
        with pytest.raises(ValueError):
            selection.choose(db, "vision", "nope")


def test_a_choice_only_counts_once_the_model_is_downloaded(client: TestClient, tmp_path: Path):
    data_dir = tmp_path / "models-here"
    entry = catalog.entry("e5-small")
    with client.app.state.sessionmaker() as db:
        assert selection.active(db, data_dir, "embedding") is None
        folder = store.folder_of(data_dir, entry)
        folder.mkdir(parents=True)
        for f in entry.files:
            (folder / f.name).parent.mkdir(parents=True, exist_ok=True)
            (folder / f.name).write_bytes(b"x" * f.size)
        assert selection.active(db, data_dir, "embedding") is None  # no manifest yet
        store.write_manifest(data_dir, entry)
        assert selection.active(db, data_dir, "embedding") == entry
        (folder / entry.files[0].name).write_bytes(b"short")  # a damaged file
        assert selection.active(db, data_dir, "embedding") is None


# -------------------------------------------------------------------------------- API
@pytest.fixture
def fake_catalog(monkeypatch: pytest.MonkeyPatch, server: Server):
    small = make_entry(server, {"model.bin": blob(20_000, 1)}, entry_id="small-emb", default=True)
    other = make_entry(
        server, {"other.bin": blob(20_000, 2)}, entry_id="other-emb", kind=catalog.EMBEDDING
    )
    vision = make_entry(
        server, {"v.bin": blob(5_000, 3)}, entry_id="small-vis", kind=catalog.VISION, default=True
    )
    ocr = make_entry(
        server, {"o.bin": blob(5_000, 4)}, entry_id="small-ocr", kind=catalog.OCR, default=True
    )
    entries = (small, other, vision, ocr)
    monkeypatch.setattr(catalog, "CATALOG", entries)
    monkeypatch.setattr(catalog, "BY_ID", {e.id: e for e in entries})
    return entries


def test_the_api_lists_every_model_with_its_state(client: TestClient, fake_catalog):
    body = client.get("/api/local-models").json()
    assert [m["id"] for m in body["models"]] == ["small-emb", "other-emb", "small-vis", "small-ocr"]
    first = body["models"][0]
    assert (first["state"], first["selected"], first["default"], first["available"]) == (
        "absent",
        True,
        True,
        True,
    )
    assert body["models"][1]["selected"] is False
    assert set(body["disk"]) == {"models", "engines", "free"} and body["disk"]["free"] > 0


def test_download_through_the_api_then_remove(client: TestClient, fake_catalog):
    response = client.post("/api/local-models/small-emb/download")
    assert response.status_code == 202 and response.json()["state"] == "downloading"
    manager = client.app.state.models
    manager.join(fake_catalog[0])
    listed = {m["id"]: m for m in client.get("/api/local-models").json()["models"]}
    assert listed["small-emb"]["state"] == "ready"
    assert client.get("/api/local-models").json()["disk"]["models"] >= 20_000

    again = client.post("/api/local-models/small-emb/download")
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "already_installed")
    assert client.delete("/api/local-models/small-emb").status_code == 204
    assert client.get("/api/local-models").json()["models"][0]["state"] == "absent"
    assert client.post("/api/local-models/nope/download").status_code == 404
    assert client.delete("/api/local-models/nope").status_code == 404


def test_cancel_through_the_api(
    client: TestClient, fake_catalog, server: Server, monkeypatch: pytest.MonkeyPatch
):
    server.pause = 0.05
    big = make_entry(server, {"big.bin": blob(6 * 1024 * 1024, 5)}, entry_id="big-emb")
    monkeypatch.setattr(catalog, "CATALOG", (*catalog.CATALOG, big))
    monkeypatch.setattr(catalog, "BY_ID", {**catalog.BY_ID, "big-emb": big})
    assert client.post("/api/local-models/big-emb/download").status_code == 202
    assert client.delete("/api/local-models/big-emb").status_code == 409  # still downloading
    assert client.post("/api/local-models/big-emb/cancel").status_code == 200
    client.app.state.models.join(big)
    state = {m["id"]: m for m in client.get("/api/local-models").json()["models"]}["big-emb"]
    assert state["state"] in ("partial", "absent")


def test_choosing_models_through_the_api(client: TestClient, fake_catalog):
    assert client.get("/api/settings/local-models").json() == {
        "embedding": "small-emb",
        "ocr": "small-ocr",
        "vision": "small-vis",
        "reindex": False,
    }
    changed = client.put("/api/settings/local-models", json={"embedding": "other-emb"}).json()
    assert (changed["embedding"], changed["reindex"]) == ("other-emb", True)
    same = client.put("/api/settings/local-models", json={"embedding": "other-emb"}).json()
    assert same["reindex"] is False  # nothing changed: nothing to index again
    other = client.put("/api/settings/local-models", json={"vision": "small-vis"}).json()
    assert (other["embedding"], other["reindex"]) == ("other-emb", False)
    back = client.put("/api/settings/local-models", json={"embedding": None}).json()
    assert (back["embedding"], back["reindex"]) == ("small-emb", True)
    refused = client.put("/api/settings/local-models", json={"embedding": "small-vis"})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (422, "invalid_model")
    assert client.put("/api/settings/local-models", json={"engine": "x"}).status_code == 422


def test_the_hugging_face_token_never_leaves_git_s_store(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    saved: list[str] = []
    state = {"token": None, "source": None}

    def save(value):
        saved.append(value)
        state.update(token=value, source="git")

    def forget():
        state.update(token=None, source=None)

    monkeypatch.setattr(models_api.hf_token, "find", lambda: (state["token"], state["source"]))
    monkeypatch.setattr(models_api.hf_token, "save", save)
    monkeypatch.setattr(models_api.hf_token, "forget", forget)

    assert client.get("/api/settings/huggingface-token").json() == {
        "configured": False,
        "source": None,
    }
    put = client.put("/api/settings/huggingface-token", json={"token": "  hf_abc  "}).json()
    assert put == {"configured": True, "source": "git"} and saved == ["hf_abc"]
    assert "hf_abc" not in client.get("/api/settings/huggingface-token").text
    assert client.put("/api/settings/huggingface-token", json={"token": None}).json() == {
        "configured": False,
        "source": None,
    }
