"""A stand-in for `whisper-server` (phase 16): installed fake files and a tiny HTTP server that
plays the part of the process, recording what it was sent."""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agentic_os.services.localmodels import catalog, store
from agentic_os.services.localmodels.catalog import CatalogEntry, RemoteFile


def speech_entries(
    tmp_path: Path,
    model_id: str = "fake-whisper",
    engine_id: str = "fake-whisper-engine",
    data_dir: Path | None = None,
):
    """An installed engine and speech model (tiny files, with their manifests)."""
    data_dir = data_dir or tmp_path / "data"
    files = {"model.bin": b"m" * 100, "vad.bin": b"v" * 20}
    model = CatalogEntry(
        model_id,
        catalog.SPEECH,
        "Fake Whisper",
        "mit",
        tuple(RemoteFile(n, len(d), hashlib.sha256(d).hexdigest(), ()) for n, d in files.items()),
        usage={"model": "model.bin", "vad": "vad.bin", "speed": "medium", "quality": "good"},
    )
    engine = CatalogEntry(
        engine_id,
        catalog.ENGINE,
        "Fake engine",
        "mit",
        (RemoteFile("e.zip", 1, "0" * 64, ()),),
        usage={"executable": "Release/whisper-server.exe"},
        unpack="e.zip",
    )
    for entry in (model, engine):
        store.downloaded_folder(data_dir, entry).mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (store.downloaded_folder(data_dir, model) / name).write_bytes(data)
    store.write_manifest(data_dir, model)
    (store.downloaded_folder(data_dir, engine) / "Release").mkdir(exist_ok=True)
    program = store.downloaded_folder(data_dir, engine) / "Release" / "whisper-server.exe"
    program.write_bytes(b"MZ")
    store.write_manifest(data_dir, engine)
    return data_dir, engine, model


class FakeWhisperProcess:
    """What `Popen` returns, with a tiny HTTP server behind it playing whisper-server."""

    def __init__(
        self,
        port: int,
        text: str = " Hola mundo. ",
        dies: bool = False,
        delay: float = 0.0,
        status: int = 200,
    ) -> None:
        self.returncode: int | None = 1 if dies else None
        self.requests: list[dict] = []  # {"fields": {...}, "audio": bytes}
        self.active = 0
        self.peak = 0
        outer = self
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._reply(200, b'{"status":"ok"}')

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                boundary = self.headers["Content-Type"].split("boundary=")[1].encode()
                fields: dict[str, str] = {}
                audio = b""
                for part in raw.split(b"--" + boundary):
                    if b"Content-Disposition" not in part:
                        continue
                    head, _, body = part.partition(b"\r\n\r\n")
                    body = body.removesuffix(b"\r\n")
                    name = head.split(b'name="')[1].split(b'"')[0].decode()
                    if b"filename=" in head:
                        audio = body
                    else:
                        fields[name] = body.decode()
                with lock:
                    outer.active += 1
                    outer.peak = max(outer.peak, outer.active)
                outer.requests.append({"fields": fields, "audio": audio})
                if delay:
                    threading.Event().wait(delay)
                with lock:
                    outer.active -= 1
                self._reply(status, json.dumps({"text": text}).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        if not dies:
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0
        self.server.shutdown()

    kill = terminate

    def wait(self, timeout=None):
        return self.returncode


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sine_wav(seconds: float = 2.0, amplitude: int = 3000, rate: int = 16000) -> bytes:
    """A 16 kHz mono 16-bit WAV with a tone: loud enough not to count as silence."""
    import io
    import math
    import struct
    import wave

    count = int(seconds * rate)
    frames = b"".join(struct.pack("<h", int(amplitude * math.sin(i / 8))) for i in range(count))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return out.getvalue()


def silent_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    return sine_wav(seconds, amplitude=0, rate=rate)
