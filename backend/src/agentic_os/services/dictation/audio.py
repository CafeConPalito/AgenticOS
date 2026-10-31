"""What arrives from the microphone: a 16 kHz mono 16-bit WAV, checked in memory.

The audio is never written to disk: it is read from the request, looked at here and sent to the
engine from the same bytes (privacy, CA7).
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000
MAX_BYTES = 30 * 1024 * 1024
WINDOW = SAMPLE_RATE * 30 // 1000  # 30 ms
# A quiet room with the microphone's noise suppression on sits far below this (S3). The engine's
# voice-activity detection does the fine work; this only spares it audio that is dead (a muted
# microphone) or too short to hold a word.
SILENCE_RMS = 150.0
MIN_SECONDS = 0.3
SLACK_SECONDS = 5  # the recorder stops at the limit, a little late


class DictationError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AudioInfo:
    seconds: float
    loudest_rms: float


def inspect(data: bytes, max_seconds: int) -> AudioInfo:
    """Raises `DictationError` unless `data` is usable speech-sized audio."""
    if len(data) > MAX_BYTES:
        raise DictationError(413, "too_large", "the recording is too big")
    try:
        with wave.open(io.BytesIO(data)) as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as error:
        raise DictationError(422, "bad_audio", f"not a WAV file: {error}") from error
    if (channels, width, rate) != (1, 2, SAMPLE_RATE):
        raise DictationError(
            422,
            "bad_audio",
            f"expected 16 kHz mono 16-bit, got {rate} Hz, {channels} ch, {width * 8} bit",
        )
    samples = np.frombuffer(frames, dtype="<i2")
    seconds = len(samples) / SAMPLE_RATE
    if seconds > max_seconds + SLACK_SECONDS:
        raise DictationError(
            422, "too_long", f"the recording lasts {seconds:.0f} s and the limit is {max_seconds} s"
        )
    if seconds < MIN_SECONDS:
        raise DictationError(422, "no_speech", "the recording is too short")
    return AudioInfo(seconds=seconds, loudest_rms=loudest_window(samples))


def loudest_window(samples: np.ndarray) -> float:
    """RMS of the loudest 30 ms window."""
    usable = len(samples) // WINDOW * WINDOW
    if usable == 0:
        return float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    windows = samples[:usable].astype(np.float64).reshape(-1, WINDOW)
    return float(np.sqrt(np.mean(np.square(windows), axis=1)).max())


def is_silent(info: AudioInfo) -> bool:
    return info.loudest_rms < SILENCE_RMS


# Phase 23 (ADR 0029): whisper-server runs with a ~10 s audio window (`-ac 512`), which takes a
# third of the time and gives the same text up to 10 s. Longer audio is cut in pieces of at most
# CHUNK_SECONDS, each at the quietest 30 ms of the last SEARCH_SECONDS before the limit.
CHUNK_SECONDS = 9.0
SEARCH_SECONDS = 2.0


def split(data: bytes) -> list[bytes]:
    """The WAV in pieces the engine reads whole, cut where nobody is speaking if possible."""
    with wave.open(io.BytesIO(data)) as wav:
        frames = wav.readframes(wav.getnframes())
    samples = np.frombuffer(frames, dtype="<i2")
    limit, search = int(CHUNK_SECONDS * SAMPLE_RATE), int(SEARCH_SECONDS * SAMPLE_RATE)
    pieces: list[np.ndarray] = []
    start = 0
    while len(samples) - start > limit:
        window = samples[start + limit - search : start + limit].astype(np.float64)
        usable = len(window) // WINDOW * WINDOW
        energy = np.sqrt(np.mean(np.square(window[:usable].reshape(-1, WINDOW)), axis=1))
        cut = start + limit - search + int(np.argmin(energy)) * WINDOW + WINDOW // 2
        pieces.append(samples[start:cut])
        start = cut
    pieces.append(samples[start:])
    return [_wav(piece) for piece in pieces]


def _wav(samples: np.ndarray) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.astype("<i2").tobytes())
    return out.getvalue()
