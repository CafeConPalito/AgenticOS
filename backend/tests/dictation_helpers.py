"""Fakes for the dictation tests: an installed fake engine and model, and a `whisper-server`
that is a tiny HTTP server (see fake_whisper.py). Import `speech` in the test module."""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_whisper import FakeWhisperProcess, speech_entries

from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.whisper import WhisperServer


@pytest.fixture
def speech(client, monkeypatch: pytest.MonkeyPatch, tmp_path):
    """`speech(**fake)` puts a fake Whisper engine and model in the data folder and the catalog
    and makes the service talk to a fake process (`fake` goes to `FakeWhisperProcess`)."""
    servers: list[WhisperServer] = []

    def install(choose: bool = True, **fake) -> SimpleNamespace:
        data_dir, engine, model = speech_entries(
            tmp_path,
            engine_id="whisper-cpp",
            data_dir=Path(client.app.state.settings.data_dir),
        )
        monkeypatch.setattr(catalog, "BY_ID", {**catalog.BY_ID, engine.id: engine, model.id: model})
        started: list[FakeWhisperProcess] = []

        def launcher(argv, log_file):
            process = FakeWhisperProcess(int(argv[argv.index("--port") + 1]), **fake)
            started.append(process)
            return process

        server = WhisperServer(
            data_dir, engine, model, threads=2, launcher=launcher, memory=lambda: 10**12,
            reap_every=0.1,
        )  # fmt: skip
        servers.append(server)
        service = client.app.state.dictation
        monkeypatch.setattr(service, "_server_for", lambda e, m: server)
        monkeypatch.setattr(service, "_server", server)  # what `status` looks at
        if choose:
            with client.app.state.sessionmaker() as db:
                selection.choose(db, catalog.SPEECH, model.id)
                db.commit()
        return SimpleNamespace(started=started, server=server, model=model, engine=engine)

    yield install
    for server in servers:
        server.stop()


# ----------------------------------------------------------------- the real engine (spikes)
SPIKE = Path(__file__).resolve().parents[2] / "spikes" / "dictation"
REAL_ENGINE = SPIKE / "engine" / "Release" / "whisper-server.exe"
REAL_MODEL = SPIKE / "models" / "ggml-base.bin"
REAL_VAD = SPIKE / "models" / "ggml-silero-v5.1.2.bin"
real_engine_downloaded = REAL_ENGINE.is_file() and REAL_MODEL.is_file() and REAL_VAD.is_file()
SAMPLES = Path(__file__).parent / "data" / "dictation"


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)  # no copy of 150 MB when both are on the same disk
    except OSError:
        shutil.copyfile(source, target)


def install_real_whisper(data_dir: Path) -> None:
    """The whisper.cpp engine and the base model the spikes downloaded, installed in `data_dir`
    as the app's own downloads would be."""
    engine, model = catalog.entry("whisper-cpp"), catalog.entry("whisper-base")
    folder = store.downloaded_folder(data_dir, engine)
    for source in REAL_ENGINE.parent.iterdir():
        if source.is_file():
            _link(source, folder / "bin" / "Release" / source.name)  # as _unpack leaves it
    store.write_manifest(data_dir, engine)
    for name, source in (("ggml-base.bin", REAL_MODEL), ("ggml-silero-v5.1.2.bin", REAL_VAD)):
        _link(source, store.downloaded_folder(data_dir, model) / name)
    store.write_manifest(data_dir, model)
    assert store.is_installed(data_dir, engine) and store.is_installed(data_dir, model)
