"""Phase 10 · S3: the opt-in agy status line end to end, with the real agy.

Installs our status line in agy's global settings through `agentic_os.services.agy_status`, runs
agy in a PTY with AGENTIC_OS_STATUS_URL pointing to a local listener, and prints what the script
posted. The settings file is restored byte for byte at the end, whatever happens.

    uv run --project ../backend python agy_status_probe.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agentic_os.services import agy_status  # noqa: E402

from pty_run import PtyRun, accept_trust, clean_env  # noqa: E402

SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
received: list[bytes] = []


class Listener(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        received.append(self.rfile.read(length))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args) -> None:  # silence
        pass


def main() -> None:
    backup = SETTINGS.read_bytes()
    server = HTTPServer(("127.0.0.1", 0), Listener)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/r/test/hook/StatusLine"
    data_dir = Path(tempfile.mkdtemp(prefix="agy-status-"))
    project = Path(tempfile.mkdtemp(prefix="agy-status-project-"))
    try:
        state = agy_status.set_enabled(SETTINGS, data_dir, True)
        print("enabled:", state.enabled, "| taken:", state.taken)
        print("settings statusLine:", json.loads(SETTINGS.read_text("utf-8"))["statusLine"])

        env = clean_env({agy_status.ENV_URL: url})
        run = PtyRun([shutil.which("agy") or "agy"], project, data_dir / "pty.log", env=env)
        try:
            accept_trust(run, "agy", timeout=30)
            time.sleep(5)
            run.type_line("Responde solo con la palabra: ok")
            run.wait_idle(quiet=8, timeout=90)
            time.sleep(2)
            screen = run.snapshot()
            run.type_line("/exit")
            run.wait_exit(15)
        finally:
            run.close()
        print("--- screen (last lines) ---")
        print("\n".join(screen.splitlines()[-6:]))
    finally:
        # Never leave the person's settings changed.
        time.sleep(1)
        SETTINGS.write_bytes(backup)
        server.shutdown()
        print("restored identical:", SETTINGS.read_bytes() == backup)
    print("posts received:", len(received))
    if received:
        last = json.loads(received[-1])
        print("keys:", sorted(last))
        print("email:", last.get("email"), "| plan:", last.get("plan_tier"))
        print("quota buckets:", sorted(last.get("quota", {})))
        Path(__file__).parent.joinpath("out", "agy-status-last.json").write_bytes(received[-1])


if __name__ == "__main__":
    main()
