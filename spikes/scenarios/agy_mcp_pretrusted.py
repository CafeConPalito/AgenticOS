"""P5 for agy in PTY: does a workspace plugin load when the folder was trusted beforehand?

Launch 1 only accepts the trust dialog and exits. Launch 2 (same folder) runs the prompt.

Usage: uv run python scenarios/agy_mcp_pretrusted.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agy_mcp import MODEL, PROMPT, install_plugin  # noqa: E402
from common import evidence, sandbox  # noqa: E402
from pty_run import PtyRun  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402


def main() -> None:
    log = evidence("p5-agy-mcp-pretrusted-calls.jsonl")
    log.unlink(missing_ok=True)
    token = f"pt-{uuid.uuid4().hex[:6]}"
    server = SpikeMcp({token}, log)
    server.start()
    cwd = sandbox("agy-mcp-pretrusted")
    install_plugin(cwd, server.path_url(token))
    rec = Recorder(
        "agy · plugin MCP en carpeta ya de confianza (P5)", evidence("p5-agy-mcp-pretrusted.md")
    )
    try:
        first = PtyRun(["agy", "--model", MODEL], cwd, evidence("p5-agy-pretrust-1.raw.log"))
        try:
            first.wait_screen(r"trust the contents", timeout=30)
            for _ in range(10):
                time.sleep(0.5)
                first.key("enter")
                time.sleep(1)
                if "trust the contents" not in first.snapshot():
                    break
            first.wait_screen(r"\? for shortcuts", timeout=30)
            rec.run = first
            rec.step("Lanzamiento 1: confianza aceptada")
            first.key("ctrl_c")
            time.sleep(0.5)
            first.key("ctrl_c")
            first.wait_exit(10)
        finally:
            first.close()

        second = PtyRun(
            ["agy", "--model", MODEL, "-i", PROMPT], cwd, evidence("p5-agy-pretrust-2.raw.log")
        )
        rec.run = second
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if len(server.calls()) >= 2:
                    break
                screen = second.snapshot()
                if "trust the contents" in screen or "Allow" in screen or "allow" in screen:
                    rec.step("Diálogo en el lanzamiento 2")
                    second.key("enter")
                    time.sleep(2)
                time.sleep(1)
            second.wait_idle(3, 30)
            calls = server.calls()
            rec.step(
                "Lanzamiento 2: llamadas recibidas",
                [c["tool"] for c in calls] == ["report_status", "complete_task"],
            )
            rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
            second.key("ctrl_c")
            time.sleep(0.5)
            second.key("ctrl_c")
            second.wait_exit(10)
        finally:
            second.close()
    finally:
        server.stop()
        rec.save()


if __name__ == "__main__":
    main()
