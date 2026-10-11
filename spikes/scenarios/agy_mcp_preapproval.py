"""Phase 04, task 1: can a workspace/plugin file pre-approve our MCP tools in agy (so "ask" and
"restricted" agents do not prompt for every report_status), without touching the user's global
settings? Also checks the hook transport planned for phase 04: a per-run `hook.cmd` referenced
by its 8.3 short path that POSTs the payload with curl.exe and always exits 0.

Each candidate runs agy headless (`-p`): a denied MCP call shows up in `denied_actions`.

Usage: uv run python scenarios/agy_mcp_preapproval.py
"""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agy_mcp import MODEL, PROMPT, install_plugin  # noqa: E402
from common import config_guard, evidence, run_cli, sandbox  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402

RULES = {"permissions": {"allow": ["mcp(agentic-os/*)"]}}
CANDIDATES = {
    "sin regla (control)": None,
    ".agents/settings.json": ".agents/settings.json",
    ".agents/config.json": ".agents/config.json",
    ".gemini/settings.json": ".gemini/settings.json",
    "plugin settings.json": ".agents/plugins/agentic-os/settings.json",
    "plugin.json con permissions": "PLUGIN_JSON",
}


class HookSink(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            payload = json.loads(body or b"null")
        except ValueError:
            payload = {"_raw": body[:200].decode(errors="replace")}
        HookSink.received.append({"path": self.path, "payload": payload})
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


def short_path(path: Path) -> str:
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, 1024)
    return buffer.value or str(path)


def write_hook_cmd(folder: Path, port: int) -> str:
    script = folder / "hook.cmd"
    script.write_text(
        '@curl.exe -s -m 3 -o NUL -X POST -H "Content-Type: application/json" '
        f"--data-binary @- http://127.0.0.1:{port}/hook/%1\r\n@exit /b 0\r\n",
        "ascii",
    )
    return short_path(script)


def main() -> None:
    log = evidence("p04-agy-preapproval-calls.jsonl")
    log.unlink(missing_ok=True)
    server = SpikeMcp(set(), log)
    server.start()
    sink = HTTPServer(("127.0.0.1", 0), HookSink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    rec = Recorder(
        "agy · preaprobar herramientas MCP sin tocar la configuración global (fase 04, tarea 1)",
        evidence("p04-agy-preapproval.md"),
    )
    guard = config_guard("agy preapproval")
    changes = guard.__enter__()
    try:
        for label, target in CANDIDATES.items():
            token = f"p{uuid.uuid4().hex[:8]}"
            server.tokens.add(token)
            cwd = sandbox("agy-preapproval")
            plugin = install_plugin(cwd, server.path_url(token))
            hook = write_hook_cmd(cwd.parent, sink.server_port)
            (plugin / "hooks.json").write_text(
                json.dumps(
                    {"agentic-os": {"Stop": [{"type": "command", "command": f"{hook} Stop"}]}}
                ),
                "utf-8",
            )
            if target == "PLUGIN_JSON":
                (plugin / "plugin.json").write_text(
                    json.dumps({"name": "agentic-os", **RULES}), "utf-8"
                )
            elif target:
                file = cwd / target
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(json.dumps(RULES), "utf-8")
            hooks_before = len(HookSink.received)
            result = run_cli(
                ["agy", "--model", MODEL, "--output-format", "json", "-p", PROMPT], cwd
            )
            out = result.json or {}
            calls = [c["tool"] for c in server.calls() if c["run"] == token]
            denied = out.get("denied_actions")
            rec.step(
                f"{label}: llamadas {calls} · denegadas {denied}",
                calls == ["report_status", "complete_task"] and not denied,
                screen=False,
            )
            rec.note(f"hook.cmd ({hook}): {len(HookSink.received) - hooks_before} eventos Stop")
    finally:
        guard.__exit__(None, None, None)
        rec.step("Configuración global sin cambios", not changes, screen=False)
        for change in changes:
            rec.note(change)
        server.stop()
        sink.shutdown()
        rec.save()


if __name__ == "__main__":
    main()
