"""The dictation engine (phase 16, block 1): `whisper-server` as a managed local process."""

import shutil
import threading
import time
from types import SimpleNamespace

import pytest
from fake_whisper import FakeWhisperProcess, speech_entries

from agentic_os.services.localmodels import catalog, selection, store
from agentic_os.services.localmodels.whisper import WhisperError, WhisperServer

WAV = b"RIFF" + b"\x00" * 60


@pytest.fixture
def whisper(tmp_path):
    data_dir, engine, model = speech_entries(tmp_path)
    started: list[FakeWhisperProcess] = []
    argvs: list[list[str]] = []

    def launcher(argv, log_file):
        argvs.append(argv)
        process = FakeWhisperProcess(int(argv[argv.index("--port") + 1]))
        started.append(process)
        return process

    server = WhisperServer(
        data_dir, engine, model, threads=3, idle_seconds=0.3, launcher=launcher,
        memory=lambda: 10**12, reap_every=0.1,
    )  # fmt: skip
    yield SimpleNamespace(
        server=server, started=started, argvs=argvs, data_dir=data_dir, engine=engine, model=model
    )
    server.stop()


def test_it_starts_on_the_first_dictation_and_is_reused(whisper):
    assert whisper.server.state == "stopped"
    assert whisper.server.transcribe(WAV, "es", "Agentes: Kestrel.") == "Hola mundo."
    assert whisper.server.state == "ready"
    whisper.server.transcribe(WAV)
    assert len(whisper.started) == 1  # one process for both
    argv = whisper.argvs[0]
    assert argv[0].endswith("whisper-server.exe") and argv[argv.index("-t") + 1] == "3"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"  # never reachable from outside
    assert "--vad" in argv and argv[argv.index("-vm") + 1].endswith("vad.bin")
    assert "--convert" not in argv  # nothing is written to disk to decode the audio
    first = whisper.started[0].requests[0]
    assert first["audio"] == WAV
    assert first["fields"]["language"] == "es"
    assert first["fields"]["prompt"] == "Agentes: Kestrel."
    assert first["fields"]["temperature"] == "0.0"
    assert "prompt" not in whisper.started[0].requests[1]["fields"]


def test_it_leaves_when_it_has_no_work_and_comes_back(whisper):
    whisper.server.transcribe(WAV)
    first = whisper.started[0]
    deadline = time.monotonic() + 5
    while whisper.server.running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not whisper.server.running and first.returncode == 0  # its memory is free again
    whisper.server.transcribe(WAV)
    assert len(whisper.started) == 2


def test_warm_up_starts_it_without_transcribing(whisper):
    whisper.server.warm_up()
    assert whisper.server.running and whisper.started[0].requests == []
    whisper.server.transcribe(WAV)
    assert len(whisper.started) == 1  # the real request found it loaded


def test_two_dictations_at_once_are_done_one_after_the_other(tmp_path):
    data_dir, engine, model = speech_entries(tmp_path)
    started: list[FakeWhisperProcess] = []

    def launcher(argv, log_file):
        process = FakeWhisperProcess(int(argv[argv.index("--port") + 1]), delay=0.3)
        started.append(process)
        return process

    server = WhisperServer(
        data_dir, engine, model, 2, launcher=launcher, memory=lambda: 10**12, reap_every=0.1
    )
    threads = [threading.Thread(target=server.transcribe, args=(WAV,)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    server.stop()
    assert len(started[0].requests) == 3 and started[0].peak == 1


def test_it_refuses_to_start_without_its_files_or_memory(whisper):
    low = WhisperServer(
        whisper.data_dir, whisper.engine, whisper.model, 2, memory=lambda: 100, reap_every=0.1
    )
    with pytest.raises(WhisperError) as caught:
        low.transcribe(WAV)
    assert caught.value.code == "not_enough_memory" and "MB" in caught.value.message
    low.stop()
    nowhere = WhisperServer(whisper.data_dir / "nowhere", whisper.engine, whisper.model, 2)
    with pytest.raises(WhisperError) as caught:
        nowhere.transcribe(WAV)
    assert caught.value.code == "engine_missing"
    nowhere.stop()
    shutil.rmtree(store.downloaded_folder(whisper.data_dir, whisper.model))
    partial = WhisperServer(whisper.data_dir, whisper.engine, whisper.model, 2)
    with pytest.raises(WhisperError) as caught:
        partial.transcribe(WAV)
    assert caught.value.code == "model_missing"
    partial.stop()


def test_a_server_that_dies_while_loading_is_an_error_with_its_code(whisper):
    dying = WhisperServer(
        whisper.data_dir, whisper.engine, whisper.model, 2,
        launcher=lambda argv, log: FakeWhisperProcess(
            int(argv[argv.index("--port") + 1]), dies=True
        ),
        memory=lambda: 10**12, reap_every=0.1,
    )  # fmt: skip
    with pytest.raises(WhisperError) as caught:
        dying.transcribe(WAV)
    assert caught.value.code == "start_failed" and "code 1" in caught.value.message
    dying.stop()


def test_a_failing_request_is_an_error_and_the_next_one_still_works(tmp_path):
    data_dir, engine, model = speech_entries(tmp_path)
    codes = iter([500, 200])

    def launcher(argv, log_file):
        return FakeWhisperProcess(int(argv[argv.index("--port") + 1]), status=next(codes))

    server = WhisperServer(
        data_dir, engine, model, 2, launcher=launcher, memory=lambda: 10**12, reap_every=0.1
    )
    with pytest.raises(WhisperError) as caught:
        server.transcribe(WAV)
    assert caught.value.code == "request_failed" and "500" in caught.value.message
    assert server.running  # an error answer does not mean the process is gone
    server.stop()


def test_the_speech_models_are_in_the_catalog_and_can_be_chosen(client):
    speech = catalog.of_kind(catalog.SPEECH)
    assert {entry.id for entry in speech} == {"whisper-base", "whisper-small", "whisper-turbo"}
    assert catalog.default_of(catalog.SPEECH).id == "whisper-small"
    for entry in speech:  # each one carries the voice-activity model and says how it performs
        assert {"model", "vad", "speed", "quality"} <= set(entry.usage)
        assert len(entry.files) == 2 and entry.size < 700 * 2**20
    engine = catalog.entry("whisper-cpp")
    assert engine.kind == catalog.ENGINE and engine.unpack == "whisper-bin-x64.zip"
    with client.app.state.sessionmaker() as db:
        assert selection.chosen(db)[catalog.SPEECH] == "whisper-small"
        selection.choose(db, catalog.SPEECH, "whisper-base")
        db.commit()
        assert selection.chosen(db)[catalog.SPEECH] == "whisper-base"
        with pytest.raises(ValueError):
            selection.choose(db, catalog.SPEECH, "e5-small")  # not a speech model
    assert (
        client.put("/api/settings/local-models", json={"speech": "whisper-turbo"}).json()["speech"]
        == "whisper-turbo"
    )
