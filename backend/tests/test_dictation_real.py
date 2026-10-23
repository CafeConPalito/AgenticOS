"""Dictation with the real engine (phase 16, block 7): `whisper-server` and a Whisper model.

Skipped unless the phase 16 spikes downloaded the engine and the base model
(`spikes/dictation/engine` and `models`). The audio is a synthetic Spanish voice.
"""

import re
import unicodedata
from pathlib import Path

import pytest
from dictation_helpers import SAMPLES, install_real_whisper, real_engine_downloaded
from fastapi.testclient import TestClient

from agentic_os.services.localmodels import catalog, selection

pytestmark = pytest.mark.skipif(
    not real_engine_downloaded,
    reason="the whisper.cpp engine and the base model are not downloaded (spikes/dictation)",
)


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", text)


def errors(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / max(len(ref), 1)


@pytest.fixture
def real(client: TestClient):
    """The real engine and the base model installed in the app's data folder."""
    install_real_whisper(Path(client.app.state.settings.data_dir))
    with client.app.state.sessionmaker() as db:
        selection.choose(db, catalog.SPEECH, "whisper-base")
        db.commit()
    return client


def say(client: TestClient, name: str = "nombres.wav"):
    return client.post(
        "/api/dictation/transcribe",
        content=(SAMPLES / name).read_bytes(),
        headers={"Content-Type": "audio/wav"},
    )


def test_a_real_dictation_in_spanish(real: TestClient):
    response = say(real)
    assert response.status_code == 200, response.text
    reference = (SAMPLES / "nombres.txt").read_text(encoding="utf-8-sig")
    text = response.json()["text"]
    assert "\n" not in text
    # Most of the sentence is understood even without help; the names are the hard part.
    assert errors(reference, text) < 0.5, text


def test_the_names_of_the_app_help_whisper_get_the_names_right(real: TestClient):
    """CA8: the hint makes the proper names come out right more often."""
    reference = (SAMPLES / "nombres.txt").read_text(encoding="utf-8-sig")
    plain = errors(reference, say(real).json()["text"])
    real.put(
        "/api/settings/dictation",
        json={"vocabulary": ["Kestrel", "Mirlo", "Zafiro", "Triaje", "Cobalto", "Lince"]},
    )
    hinted = errors(reference, say(real).json()["text"])
    assert hinted < plain, (plain, hinted)


def test_silence_is_not_turned_into_words(real: TestClient):
    import random
    import struct

    random.seed(1)
    import io
    import wave

    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(
            b"".join(struct.pack("<h", int(random.gauss(0, 400))) for _ in range(16000 * 4))
        )  # loud enough to reach the engine, with nothing to say
    response = real.post(
        "/api/dictation/transcribe", content=out.getvalue(), headers={"Content-Type": "audio/wav"}
    )
    assert response.status_code == 422 and response.json()["detail"]["code"] == "no_speech"
