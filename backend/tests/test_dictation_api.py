"""Dictation (phase 16, block 2): the API, settings, hint, audio checks and queue."""

import io
import os
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fake_whisper import silent_wav, sine_wav
from fastapi.testclient import TestClient

from agentic_os.services.dictation import audio, config, hints
from agentic_os.services.dictation.service import clean, is_phantom

TRANSCRIBE = "/api/dictation/transcribe"
WAV = {"Content-Type": "audio/wav"}


def say(client: TestClient, data: bytes):
    return client.post(TRANSCRIBE, content=data, headers=WAV)


def listing(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


# ------------------------------------------------------------------------- transcribing
def test_a_dictation_comes_back_as_text(client: TestClient, speech):
    fake = speech(text=" Hola   mundo.\n Esto es una prueba. ")
    response = say(client, sine_wav(2))
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Hola mundo. Esto es una prueba."  # one line, no stray spaces
    assert body["model"] == "fake-whisper" and body["seconds"] == pytest.approx(2.0)
    sent = fake.started[0].requests[0]
    assert sent["audio"][:4] == b"RIFF"
    assert sent["fields"]["language"] == "es"


def test_without_a_model_the_error_says_what_to_download(client: TestClient, speech):
    response = say(client, sine_wav())
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "engine_missing")
    speech(choose=False)  # engine and model downloaded, none chosen: the default is not
    response = say(client, sine_wav())
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "no_model")


def test_turned_off_it_refuses_and_says_so(client: TestClient, speech):
    speech()
    client.put("/api/settings/dictation", json={"enabled": False})
    response = say(client, sine_wav())
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "disabled")
    status = client.get("/api/dictation/status").json()
    assert (status["enabled"], status["ready"], status["reason"]) == (False, False, "disabled")


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"not a wav at all", 422, "bad_audio"),
        (sine_wav(rate=44100), 422, "bad_audio"),  # the app records 16 kHz: anything else is a bug
        (sine_wav(0.1), 422, "no_speech"),  # shorter than a word
        (silent_wav(3), 422, "no_speech"),  # a muted microphone never reaches the engine
        (sine_wav(40), 422, "too_long"),
    ],
    ids=["not-wav", "wrong-rate", "too-short", "muted", "too-long"],
)
def test_unusable_audio_is_refused_before_the_engine(client, speech, data, status, code):
    fake = speech()
    client.put("/api/settings/dictation", json={"max_seconds": 30})
    response = say(client, data)
    assert (response.status_code, response.json()["detail"]["code"]) == (status, code)
    assert fake.started == []  # nothing was loaded for it


def test_an_oversized_body_is_refused(client: TestClient, speech):
    speech()
    big = b"\0" * (audio.MAX_BYTES + 1)
    assert say(client, big).status_code == 413


def test_whisper_inventing_text_for_silence_is_no_speech(client: TestClient, speech):
    for invented in (
        "[Música]",
        " (música) ",
        "Subtítulos realizados por la comunidad de Amara.org",
        "",
    ):
        speech(text=invented)
        response = say(client, sine_wav())
        assert response.status_code == 422, invented
        assert response.json()["detail"]["code"] == "no_speech"
    assert is_phantom("[silbido]") and not is_phantom("Gracias por la ayuda")
    assert clean("a \n b\t c") == "a b c"


def test_engine_failures_are_reported_with_their_code(client: TestClient, speech):
    speech(status=500)
    response = say(client, sine_wav())
    assert (response.status_code, response.json()["detail"]["code"]) == (502, "request_failed")
    assert "500" in response.json()["detail"]["message"]


# --------------------------------------------------------------------- nothing on disk
def test_the_audio_never_touches_the_disk(client: TestClient, speech, tmp_path):
    speech()
    data_dir = Path(client.app.state.settings.data_dir)
    temp = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or tmp_path)
    before = (listing(data_dir), listing(tmp_path) if temp != tmp_path else set())
    assert say(client, sine_wav()).status_code == 200  # a dictation that works
    speech(status=500)
    assert say(client, sine_wav()).status_code == 502  # and one that fails
    # Only the log may have grown; no audio, no temporary file.
    new = listing(data_dir) - before[0]
    assert all(name.startswith("logs") for name in new), new
    assert not any(name.endswith((".wav", ".webm", ".ogg", ".part")) for name in new)


# -------------------------------------------------------------------------------- queue
def test_dictations_at_once_wait_for_each_other_and_the_api_stays_up(client, speech):
    fake = speech(delay=0.4)
    results: list[int] = []

    def go():
        results.append(say(client, sine_wav()).status_code)

    threads = [threading.Thread(target=go) for _ in range(3)]
    for thread in threads:
        thread.start()
    # Busy transcribing, the API still answers at once (CA9) and shows who is waiting.
    status: dict = {}
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        status = client.get("/api/dictation/status").json()
        assert time.monotonic() - t0 < 1.5  # answered while the engine was busy for 0.4 s each
        if status["queued"] >= 1:
            break
        time.sleep(0.02)
    assert status["state"] == "busy" and status["queued"] >= 1
    for thread in threads:
        thread.join()
    assert results == [200, 200, 200]
    assert fake.started[0].peak == 1  # one at a time
    assert len(fake.started[0].requests) == 3


def test_warming_up_loads_the_model_and_a_missing_one_is_not_an_error(client, speech):
    assert client.post("/api/dictation/warmup").status_code == 202  # nothing downloaded: quiet
    fake = speech()
    assert client.post("/api/dictation/warmup").status_code == 202
    assert fake.server.running and fake.started[0].requests == []
    status = client.get("/api/dictation/status").json()
    assert (status["ready"], status["state"], status["queued"]) == (True, "ready", 0)


def test_status_before_anything_is_downloaded(client: TestClient):
    status = client.get("/api/dictation/status").json()
    assert (status["ready"], status["reason"], status["state"]) == (
        False,
        "engine_missing",
        "stopped",
    )
    assert status["model"] == "whisper-small"  # what would be used


# ------------------------------------------------------------------------------ settings
def test_settings_have_defaults_and_validate(client: TestClient):
    first = client.get("/api/settings/dictation").json()
    assert first == {
        "enabled": True,
        "language": "es",
        "shortcut": "Ctrl+Space",
        "max_seconds": 300,
        "vocabulary": [],
    }
    saved = client.put(
        "/api/settings/dictation",
        json={"language": "auto", "max_seconds": 120, "shortcut": "F9",
              "vocabulary": ["Kestrel", "  Zafiro ", "kestrel"]},
    ).json()  # fmt: skip
    assert saved["language"] == "auto" and saved["max_seconds"] == 120 and saved["shortcut"] == "F9"
    assert saved["vocabulary"] == ["Kestrel", "Zafiro"]  # trimmed, no repeats
    assert client.get("/api/settings/dictation").json() == saved
    for bad in ({"max_seconds": 5}, {"max_seconds": 5000}, {"language": "spanish!"}, {"nope": 1}):
        assert client.put("/api/settings/dictation", json=bad).status_code == 422


def test_settings_that_were_stored_badly_fall_back_to_the_defaults():
    base = config.DictationSettings()
    fixed = config.normalized(
        base, {"enabled": "yes", "language": "??", "max_seconds": True, "vocabulary": "x"}
    )
    assert fixed == base
    assert config.normalized(base, {"max_seconds": 10**6}).max_seconds == 900


# --------------------------------------------------------------------------------- hint
def test_the_hint_lists_the_names_the_model_cannot_know(client: TestClient):
    client.post("/api/agents", json={"name": "Kestrel", "cli": "claude"})
    with client.app.state.sessionmaker() as db:
        text = hints.build(db, config.DictationSettings(vocabulary=["Zafiro", "kestrel"]))
        assert text.startswith("Términos: Zafiro, kestrel.")
        assert "Agentes:" not in text  # «Kestrel» is already in the user's terms: no repeats
        english = hints.build(db, config.DictationSettings(language="en", vocabulary=["Zafiro"]))
        assert english.startswith("Terms: Zafiro.")


def test_the_hint_fits_what_whisper_reads(client: TestClient):
    terms = [f"término-{i:03d}" for i in range(200)]
    with client.app.state.sessionmaker() as db:
        text = hints.build(db, config.DictationSettings(vocabulary=terms))
    assert 0 < len(text) <= hints.BUDGET + 20
    assert text.count("término") < 200  # the end was dropped, not the start
    assert "término-000" in text


def test_the_hint_reaches_the_engine(client: TestClient, speech):
    client.put("/api/settings/dictation", json={"vocabulary": ["Zafiro"], "language": "es"})
    fake = speech()
    say(client, sine_wav())
    assert "Zafiro" in fake.started[0].requests[0]["fields"]["prompt"]


# ---------------------------------------------------------------------------------- audio
def test_the_audio_checks_read_the_wav_in_memory():
    info = audio.inspect(sine_wav(1.5), 300)
    assert info.seconds == pytest.approx(1.5) and not audio.is_silent(info)
    assert audio.is_silent(audio.inspect(silent_wav(1.5), 300))
    out = io.BytesIO()
    with wave.open(out, "wb") as stereo:
        stereo.setnchannels(2)
        stereo.setsampwidth(2)
        stereo.setframerate(16000)
        stereo.writeframes(b"\0" * 64000)
    with pytest.raises(audio.DictationError) as caught:
        audio.inspect(out.getvalue(), 300)
    assert caught.value.code == "bad_audio" and "2 ch" in caught.value.message


# -------------------------------------------------------------------------- review fixes
def test_a_long_dictation_that_mentions_a_known_phrase_is_kept():
    note = (
        "Para el vídeo del canal, al final dile que suscríbete y gracias por ver el video, "
        "y que lo publicamos el lunes."
    )
    assert len(note) > 100 and not is_phantom(note)
    assert is_phantom("Suscríbete") and is_phantom("Subtítulos por Amara.org")


# ------------------------------------------------------------------------- phase 23: in pieces
def voice_with_pauses(seconds: float, pauses: list[float]) -> bytes:
    """A tone of `seconds` with 0.4 s of silence starting at each of `pauses`."""
    rate = audio.SAMPLE_RATE
    t = np.arange(int(seconds * rate)) / rate
    samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2")
    for start in pauses:
        samples[int(start * rate) : int((start + 0.4) * rate)] = 0
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return out.getvalue()


def lengths(pieces: list[bytes]) -> list[float]:
    out = []
    for piece in pieces:
        with wave.open(io.BytesIO(piece)) as wav:
            out.append(wav.getnframes() / wav.getframerate())
    return out


def test_long_audio_is_cut_in_pieces_of_at_most_9_s_at_the_pauses():
    pieces = audio.split(voice_with_pauses(25, pauses=[7.5, 15.8]))
    seconds = lengths(pieces)
    assert all(s <= audio.CHUNK_SECONDS for s in seconds)
    assert sum(seconds) == pytest.approx(25, abs=0.01)  # nothing lost
    # Each cut falls inside a pause, not in the middle of the voice.
    assert 7.5 <= seconds[0] <= 7.9
    assert 15.8 <= seconds[0] + seconds[1] <= 16.2
    assert lengths(audio.split(voice_with_pauses(5, []))) == [pytest.approx(5)]


def test_a_long_dictation_goes_to_the_engine_in_pieces_and_comes_back_whole(
    client: TestClient, speech
):
    fake = speech(text=" trozo. ")
    response = say(client, voice_with_pauses(20, pauses=[8.0]))
    assert response.status_code == 200
    assert response.json()["text"] == "trozo. trozo. trozo."
    assert len(fake.started[0].requests) == 3


def test_the_engine_reads_a_short_window(client: TestClient, speech):
    fake = speech()
    say(client, sine_wav(1))
    assert fake.server._argv(1234)[-2:] == ["-ac", "512"]


def test_a_partial_text_gives_way_when_the_engine_is_busy(client: TestClient, speech):
    speech()
    service = client.app.state.dictation
    assert client.post(f"{TRANSCRIBE}?partial=true", content=sine_wav(1), headers=WAV).json()[
        "text"
    ]
    service._pending += 1  # another transcription is running
    try:
        busy = client.post(f"{TRANSCRIBE}?partial=true", content=sine_wav(1), headers=WAV)
        assert busy.status_code == 409
        assert busy.json()["detail"]["code"] == "busy"
    finally:
        service._pending -= 1
