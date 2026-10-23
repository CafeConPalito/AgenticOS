"""Dictation end to end (phase 16): a real backend and the real `whisper-server`. With
AGENTIC_OS_E2E_BINARY it is the packaged sidecar that runs it, so it catches what the build is
missing and proves the engine starts from the data folder like the app's own download would.

Skipped unless the phase 16 spikes downloaded the engine and the base model.
"""

from __future__ import annotations

import httpx
import pytest
from dictation_helpers import SAMPLES, install_real_whisper, real_engine_downloaded
from live_server import live_server
from test_dictation_real import errors
from test_scheduler_e2e import Api, settings_for

pytestmark = pytest.mark.skipif(
    not real_engine_downloaded,
    reason="the whisper.cpp engine and the base model are not downloaded (spikes/dictation)",
)


def test_a_spanish_dictation_through_the_real_engine(tmp_path):
    settings = settings_for(tmp_path)
    install_real_whisper(settings.data_dir)
    with live_server(settings) as server:
        api = Api(server)
        # Nothing chosen yet: the engine and the model are there, the default (small) is not.
        assert api.get("/api/dictation/status")["reason"] == "no_model"
        httpx.put(
            f"{server.url}/api/settings/local-models", json={"speech": "whisper-base"}
        ).raise_for_status()
        status = api.get("/api/dictation/status")
        assert (status["ready"], status["state"], status["model"]) == (
            True,
            "stopped",
            "whisper-base",
        )

        # The model loads while the person talks...
        assert httpx.post(f"{server.url}/api/dictation/warmup", timeout=60).status_code == 202
        assert api.get("/api/dictation/status")["state"] == "ready"

        # ...and the dictation comes back as text, with the names that Whisper cannot know.
        httpx.put(
            f"{server.url}/api/settings/dictation",
            json={
                "vocabulary": [
                    "Kestrel",
                    "Mirlo",
                    "Zafiro",
                    "Triaje",
                    "Cobalto",
                    "Lince",
                    "Celery",
                    "Redis",
                ]
            },
        ).raise_for_status()
        response = httpx.post(
            f"{server.url}/api/dictation/transcribe",
            content=(SAMPLES / "nombres.wav").read_bytes(),
            headers={"Content-Type": "audio/wav"},
            timeout=120,
        )
        assert response.status_code == 200, response.text
        text = response.json()["text"]
        reference = (SAMPLES / "nombres.txt").read_text(encoding="utf-8-sig")
        assert errors(reference, text) < 0.35, text
        assert "Zafiro" in text and "\n" not in text

        # The audio was not kept anywhere in the data folder.
        kept = [p for p in settings.data_dir.rglob("*") if p.suffix in (".wav", ".webm", ".ogg")]
        assert kept == []
