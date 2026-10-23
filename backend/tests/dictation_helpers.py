"""Fakes for the dictation tests: an installed fake engine and model, and a `whisper-server`
that is a tiny HTTP server (see fake_whisper.py). Import `speech` in the test module."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_whisper import FakeWhisperProcess, speech_entries

from agentic_os.services.localmodels import catalog, selection
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
