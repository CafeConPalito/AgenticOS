"""Phase 23, spike S1: how long whisper-server takes on 3, 6, 10 and 20 s of audio (live dictation).

Uses the phase 16 spike engine and models (spikes/dictation/engine, models) and the sample
`samples/dictado.wav` (16 kHz mono). Prints seconds per request, twice each (the first warms up).
Extra arguments go to whisper-server (e.g. `-ac 512`, a shorter audio window).
"""

import io
import os
import socket
import subprocess
import sys
import time
import wave
from pathlib import Path

import httpx

HERE = Path(__file__).parent
SERVER = HERE / "engine" / "Release" / "whisper-server.exe"
SAMPLE = HERE / "samples" / "dictado.wav"


def clip(seconds: float) -> bytes:
    with wave.open(str(SAMPLE)) as source:
        frames = source.readframes(int(source.getframerate() * seconds))
        out = io.BytesIO()
        with wave.open(out, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(source.getsampwidth())
            target.setframerate(source.getframerate())
            target.writeframes(frames)
        return out.getvalue()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(model: str, extra: list[str]) -> None:
    port = free_port()
    threads = str(max(1, (os.cpu_count() or 4) // 2))
    server = subprocess.Popen(
        [str(SERVER), "-m", str(HERE / "models" / model), "-t", threads,
         "--host", "127.0.0.1", "--port", str(port),
         "--vad", "-vm", str(HERE / "models" / "ggml-silero-v5.1.2.bin"), *extra],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        with httpx.Client(timeout=120) as client:
            for _ in range(120):
                try:
                    client.get(f"http://127.0.0.1:{port}/")
                    break
                except httpx.HTTPError:
                    time.sleep(0.5)
            for seconds in [float(s) for s in os.environ.get("CLIPS", "3 6 10 20").split()]:
                for attempt in (1, 2):
                    start = time.perf_counter()
                    answer = client.post(
                        f"http://127.0.0.1:{port}/inference",
                        files={"file": ("a.wav", clip(seconds), "audio/wav")},
                        data={"temperature": "0.0", "response_format": "json", "language": "es"},
                    )
                    took = time.perf_counter() - start
                    text = answer.json().get("text", "").strip()
                    print(
                        f"{model} {' '.join(extra)} {seconds:>4}s #{attempt}: {took:5.2f}s  {text!r}"
                    )
    finally:
        server.terminate()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ggml-small-q5_1.bin", sys.argv[2:])
