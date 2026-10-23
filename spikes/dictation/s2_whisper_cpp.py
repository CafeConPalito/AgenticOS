"""S2 / S3: whisper.cpp `whisper-server` on CPU: speed, memory, WER, vocabulary hint, silence.

    uv run python dictation/s2_whisper_cpp.py [model ...] [--threads 4 8]

Needs the engine unpacked in dictation/engine and the models in dictation/models.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import struct
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path

import httpx
import psutil

HERE = Path(__file__).parent
SERVER = HERE / "engine" / "Release" / "whisper-server.exe"
MODELS = HERE / "models"
SAMPLES = HERE / "samples"
OUT = HERE / "out"

NAMES_HINT = "Agentes: Kestrel, Mirlo. Proyecto: Zafiro. Etapas: Triaje, Cobalto. Equipo: Lince. Celery, Redis."


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", text)


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / max(len(ref), 1)


def make_noise(path: Path, seconds: int = 10) -> None:
    """Quiet room noise, no voice: the case that makes Whisper invent subtitles."""
    import random

    random.seed(1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(random.gauss(0, 60) + 40 * math.sin(i / 90)))
                for i in range(16000 * seconds)
            )
        )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, model: str, threads: int, extra: list[str] | None = None):
        self.port = free_port()
        argv = [str(SERVER), "-m", str(MODELS / model), "-t", str(threads),
                "--host", "127.0.0.1", "--port", str(self.port), *(extra or os.environ.get("S2_EXTRA", "").split())]  # fmt: skip
        self.log = (OUT / "whisper-server.log").open("wb")
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(argv, stdout=self.log, stderr=self.log, cwd=SERVER.parent)
        with httpx.Client() as c:
            while True:
                if self.proc.poll() is not None:
                    raise SystemExit(
                        f"server died ({self.proc.returncode}); see out/whisper-server.log"
                    )
                try:
                    if c.get(f"http://127.0.0.1:{self.port}/", timeout=1).status_code < 500:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
        self.cold = time.perf_counter() - t0

    def memory_mb(self) -> float:
        return psutil.Process(self.proc.pid).memory_info().rss / 2**20

    def transcribe(
        self, wav: Path, prompt: str = "", language: str = "es", **extra
    ) -> tuple[str, float]:
        data = {"temperature": "0.0", "response_format": "json", "language": language, **extra}
        if prompt:
            data["prompt"] = prompt
        t0 = time.perf_counter()
        r = httpx.post(
            f"http://127.0.0.1:{self.port}/inference",
            files={"file": (wav.name, wav.read_bytes(), "audio/wav")},
            data=data,
            timeout=600,
        )
        elapsed = time.perf_counter() - t0
        r.raise_for_status()
        return r.json().get("text", "").strip(), elapsed

    def close(self) -> None:
        self.proc.kill()
        self.proc.wait()
        self.log.close()


def seconds_of(wav: Path) -> float:
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    args = sys.argv[1:]
    threads = [4, 8]
    if "--threads" in args:
        i = args.index("--threads")
        threads = [int(x) for x in args[i + 1 :]]
        args = args[:i]
    models = args or sorted(p.name for p in MODELS.glob("ggml-*.bin"))
    OUT.mkdir(exist_ok=True)
    noise = SAMPLES / "ruido.wav"
    if not noise.exists():
        make_noise(noise)
    dictado, nombres = SAMPLES / "dictado.wav", SAMPLES / "nombres.wav"
    ref_d = (SAMPLES / "dictado.txt").read_text(encoding="utf-8-sig")
    ref_n = (SAMPLES / "nombres.txt").read_text(encoding="utf-8-sig")

    results = []
    for model in models:
        for t in threads:
            server = Server(model, t)
            try:
                server.transcribe(nombres)  # first call loads kernels; not measured
                text_d, secs_d = server.transcribe(dictado)
                text_n0, _ = server.transcribe(nombres)
                text_n1, _ = server.transcribe(nombres, prompt=NAMES_HINT)
                text_s, _ = server.transcribe(noise)
                row = {
                    "model": model, "threads": t, "cold_s": round(server.cold, 1),
                    "mem_mb": round(server.memory_mb()), "audio_s": round(seconds_of(dictado), 1),
                    "time_s": round(secs_d, 1), "per_minute_s": round(secs_d / seconds_of(dictado) * 60, 1),
                    "wer_dictado": round(wer(ref_d, text_d), 3),
                    "wer_names_plain": round(wer(ref_n, text_n0), 3),
                    "wer_names_hint": round(wer(ref_n, text_n1), 3),
                    "silence_text": text_s,
                    "names_plain": text_n0, "names_hint": text_n1,
                }  # fmt: skip
            finally:
                server.close()
            results.append(row)
            print(json.dumps(row, ensure_ascii=False))
    (OUT / os.environ.get("S2_OUT", "s2_whisper_cpp.json")).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
