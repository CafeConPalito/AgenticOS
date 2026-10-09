"""P5 for agy in PTY: wait until the workspace-plugin MCP server shows as connected in /mcp,
then send the prompt. Only MCP permission prompts are approved (never shell commands).

Usage: uv run python scenarios/agy_mcp_connected.py
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
from pty_run import PtyRun, accept_trust, approve_only_agentic_os  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402


def main() -> None:
    log = evidence("p5-agy-mcp-connected-calls.jsonl")
    log.unlink(missing_ok=True)
    token = f"c-{uuid.uuid4().hex[:6]}"
    server = SpikeMcp({token}, log)
    server.start()
    cwd = sandbox("agy-mcp-connected")
    install_plugin(cwd, server.path_url(token))
    rec = Recorder(
        "agy · MCP del plugin conectado antes del prompt (P5)", evidence("p5-agy-mcp-connected.md")
    )
    run = PtyRun(["agy", "--model", MODEL], cwd, evidence("p5-agy-mcp-connected.raw.log"))
    rec.run = run
    try:
        accept_trust(run, "agy")
        run.wait_screen(r"\? for shortcuts", timeout=30)
        connected = False
        for _ in range(6):
            time.sleep(3)
            run.type_line("/mcp")
            time.sleep(3)
            screen = run.snapshot()
            connected = "agentic-os" in screen and "error" not in screen.lower()
            run.key("esc")
            time.sleep(1)
            if connected:
                break
        rec.step("Estado en /mcp antes del prompt", connected)
        run.type_line(PROMPT)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and len(server.calls()) < 2:
            request = approve_only_agentic_os(run)
            if request:
                rec.step(f"Diálogo de permiso ({request[0]}): {request[1]}", screen=False)
            time.sleep(1)
        run.wait_idle(3, 30)
        calls = server.calls()
        rec.step(
            "Llamadas recibidas",
            [c["tool"] for c in calls] == ["report_status", "complete_task"],
        )
        rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
        run.key("ctrl_c")
        time.sleep(0.5)
        run.key("ctrl_c")
        run.wait_exit(10)
    finally:
        run.close()
        server.stop()
        rec.save()


if __name__ == "__main__":
    main()
