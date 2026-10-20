"""Models that ship inside the installer (phase 14, block 3): the OCR."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_local_models import Server, blob, make_entry, server  # noqa: F401 - a fixture

from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.downloads import DownloadError, DownloadManager
from agentic_os.services.localmodels.stage import main as stage_main
from agentic_os.services.localmodels.stage import stage


def lay_out(root: Path, entry, *, broken: str | None = None) -> None:
    """Puts the entry's files where a build would, with the right sizes."""
    folder = root / entry.id
    for f in entry.files:
        (folder / f.name).parent.mkdir(parents=True, exist_ok=True)
        size = f.size + 1 if f.name == broken else f.size
        (folder / f.name).write_bytes(b"x" * size)


def fake(server: Server, **options):
    return make_entry(
        server,
        {"det.onnx": blob(3000, 1), "rec.onnx": blob(2000, 2)},
        entry_id="fake-ocr",
        kind=catalog.OCR,
        default=True,
        bundled=True,
        **options,
    )


@pytest.fixture
def manager(tmp_path: Path):
    manager = DownloadManager(tmp_path / "data", KnowledgeEvents())
    yield manager
    manager.stop()


def test_only_the_ocr_ships_inside_the_installer():
    assert [e.id for e in catalog.CATALOG if e.bundled] == ["ocr-latin"]
    assert catalog.entry("ocr-latin").size < 20_000_000  # ~18 MB, nothing like the others


def test_there_is_no_bundle_in_development(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENTIC_OS_BUNDLED_MODELS", raising=False)
    assert store.bundled_root() is None
    assert not store.is_bundled(catalog.entry("ocr-latin"))


def test_the_packaged_app_looks_inside_its_own_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv("AGENTIC_OS_BUNDLED_MODELS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert store.bundled_root() is None  # a frozen build without the folder (an old one)
    (tmp_path / "bundled_models").mkdir()
    assert store.bundled_root() == tmp_path / "bundled_models"


def test_a_bundled_model_is_ready_from_the_start_and_cannot_be_removed(
    manager: DownloadManager, server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entry = fake(server)
    bundle = tmp_path / "bundle"
    lay_out(bundle, entry)
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(bundle))

    assert store.is_bundled(entry) and store.is_installed(manager.data_dir, entry)
    state = manager.state(entry)
    assert (state.state, state.bundled, state.done, state.total) == ("ready", True, 5000, 5000)
    # Read in place, from the bundle; nothing in the data folder.
    assert store.file_path(manager.data_dir, entry, "det.onnx") == bundle / "fake-ocr" / "det.onnx"
    assert not (manager.data_dir / "models").exists()
    with pytest.raises(DownloadError) as caught:
        manager.remove(entry)
    assert caught.value.code == "bundled"
    assert (bundle / "fake-ocr" / "det.onnx").exists()
    assert server.requests == []  # and it never went to the network


def test_a_damaged_bundle_falls_back_to_downloading(
    manager: DownloadManager, server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entry = fake(server)
    bundle = tmp_path / "bundle"
    lay_out(bundle, entry, broken="rec.onnx")  # one file with the wrong size
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(bundle))
    assert not store.is_bundled(entry)
    assert manager.state(entry).state == "absent"
    manager.start(entry)
    manager.join(entry)
    state = manager.state(entry)
    assert (state.state, state.bundled) == ("ready", False)
    # Downloaded into the data folder, never into the bundle.
    assert (manager.data_dir / "models" / "fake-ocr" / "det.onnx").is_file()
    assert (bundle / "fake-ocr" / "rec.onnx").stat().st_size == 2001
    manager.remove(entry)  # and a download can be removed


def test_a_bundled_model_counts_as_the_one_in_use(
    client: TestClient, server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entry = fake(server)
    monkeypatch.setattr(catalog, "CATALOG", (entry,))
    monkeypatch.setattr(catalog, "BY_ID", {entry.id: entry})
    with client.app.state.sessionmaker() as db:
        assert selection.active(db, tmp_path / "data", "ocr") is None
        lay_out(tmp_path / "bundle", entry)
        monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(tmp_path / "bundle"))
        assert selection.active(db, tmp_path / "data", "ocr") == entry


def test_the_api_shows_it_ready_and_refuses_to_download_or_delete_it(
    client: TestClient, server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entry = fake(server)
    monkeypatch.setattr(catalog, "CATALOG", (entry,))
    monkeypatch.setattr(catalog, "BY_ID", {entry.id: entry})
    lay_out(tmp_path / "bundle", entry)
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(tmp_path / "bundle"))
    listed = client.get("/api/local-models").json()["models"][0]
    assert (listed["state"], listed["bundled"], listed["selected"]) == ("ready", True, True)
    again = client.post("/api/local-models/fake-ocr/download")
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "already_installed")
    gone = client.delete("/api/local-models/fake-ocr")
    assert (gone.status_code, gone.json()["detail"]["code"]) == (409, "bundled")


# --------------------------------------------------------------------------- the build
def test_staging_downloads_what_the_installer_carries_and_is_repeatable(
    server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entry = fake(server)
    root = tmp_path / "staged"
    messages: list[str] = []
    assert stage(root, [entry], log=messages.append) is True
    assert (root / "models" / "fake-ocr" / "det.onnx").read_bytes() == server.files["/det.onnx"]
    requests = len(server.requests)
    assert stage(root, [entry], log=messages.append) is True
    assert len(server.requests) == requests  # already there: nothing asked
    assert any("ready" in m for m in messages)

    # What the build produced is exactly what the packaged app looks for.
    monkeypatch.setenv("AGENTIC_OS_BUNDLED_MODELS", str(root / "models"))
    assert store.is_bundled(entry)


def test_staging_fails_loudly_when_a_file_is_not_the_pinned_one(server: Server, tmp_path: Path):
    entry = fake(server)
    server.files["/det.onnx"] = blob(3000, 99)  # another content under the same name
    messages: list[str] = []
    assert stage(tmp_path / "staged", [entry], log=messages.append) is False
    assert any("FAILED" in m and "checksum" in m for m in messages)


def test_the_staging_command_needs_a_folder(capsys: pytest.CaptureFixture[str]):
    assert stage_main([]) == 2
    assert "usage" in capsys.readouterr().err
