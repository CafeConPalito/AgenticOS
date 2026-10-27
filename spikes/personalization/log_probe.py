"""S4: start a throwaway backend that logs to a file, hit token-bearing routes, look for leaks.

usage: log_probe.py <scratch folder>
Only the backend this script starts is stopped at the end.
"""

import contextlib
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 8766
MARKERS = ["SECRETRUNTOKEN123", "ARCHTOKEN456", "sk-ant-LEAKME", "hunter2", "probe@example.com"]


def hit(path: str, method: str = "GET") -> None:
    body = b"{}" if method == "POST" else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method, data=body)
    with contextlib.suppress(urllib.error.URLError, OSError):
        urllib.request.urlopen(req, timeout=10).read()


def main(scratch: Path) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    log = scratch / "backend.log"
    env = dict(
        os.environ,
        AGENTIC_OS_DATA_DIR=str(scratch / "data"),
        AGENTIC_OS_LOG_FILE=str(log),
        APPDATA=str(scratch / "appdata"),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "agentic_os", "--port", str(PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        hit("/r/SECRETRUNTOKEN123/mcp")
        hit("/r/SECRETRUNTOKEN123/hook/stop", "POST")
        hit("/a/ARCHTOKEN456/mcp")
        hit("/api/agents?api_key=sk-ant-LEAKME&password=hunter2&email=probe@example.com")
        time.sleep(1)
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    text = log.read_text(encoding="utf-8", errors="replace")
    print(f"{len(text.splitlines())} lines")
    for marker in MARKERS:
        lines = [line[:180] for line in text.splitlines() if marker in line]
        print(f"{marker}: {len(lines)}", *lines[:2], sep="\n  ")
    home = re.escape(str(Path.home()))
    print("home path lines:", len(re.findall(home, text)))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
