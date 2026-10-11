"""Phase 04, task 1: does agy run plugin hooks through a per-run `hook.cmd` (8.3 short path,
curl.exe, always exit 0)? Runs headless in autonomous mode, like the phase 01 hooks scenario.

Usage: uv run python scenarios/agy_hook_cmd.py [--ask]
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agy_mcp_preapproval import HookSink, write_hook_cmd  # noqa: E402

from agy_mcp import MODEL, PROMPT, install_plugin  # noqa: E402
from common import config_guard, evidence, run_cli, sandbox  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402

EVENTS = ("PreInvocation", "PostInvocation", "Stop")


def main() -> None:
    ask = "--ask" in sys.argv
    log = evidence("p04-agy-hook-cmd-calls.jsonl")
    log.unlink(missing_ok=True)
    token = f"k{uuid.uuid4().hex[:8]}"
    server = SpikeMcp({token}, log)
    server.start()
    sink = HTTPServer(("127.0.0.1", 0), HookSink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    rec = Recorder(
        f"agy · hooks por hook.cmd + curl ({'preguntar' if ask else 'autónomo'})",
        evidence(f"p04-agy-hook-cmd{'-ask' if ask else ''}.md"),
    )
    with config_guard("agy hook.cmd") as changes:
        try:
            cwd = sandbox("agy-hook-cmd")
            plugin = install_plugin(cwd, server.path_url(token))
            hook = write_hook_cmd(cwd, sink.server_port)
            hooks = {
                "agentic-os": {e: [{"type": "command", "command": f"{hook} {e}"}] for e in EVENTS}
            }
            (plugin / "hooks.json").write_text(json.dumps(hooks, indent=1), "utf-8")
            flags = [] if ask else ["--dangerously-skip-permissions"]
            result = run_cli(
                ["agy", "--model", MODEL, "--output-format", "json", *flags, "-p", PROMPT], cwd
            )
            received = [h["path"].rsplit("/", 1)[-1] for h in HookSink.received]
            rec.step(f"Hooks recibidos: {received}", "Stop" in received, screen=False)
            rec.step(
                f"Llamadas MCP: {[c['tool'] for c in server.calls()]}",
                bool(server.calls()) or ask,
                screen=False,
            )
            first = HookSink.received[0]["payload"] if HookSink.received else None
            rec.note("Primer payload: ```" + json.dumps(first, ensure_ascii=False)[:600] + "```")
            out = result.json or {}
            rec.note(f"rc {result.returncode} · denegadas {out.get('denied_actions')}")
        finally:
            server.stop()
            sink.shutdown()
    rec.step("Configuración global sin cambios", not changes, screen=False)
    rec.save()


if __name__ == "__main__":
    main()
