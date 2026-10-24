"""Phase 18 · spike S1 (PTY part): Claude Code interactive, the way the app launches it.

  - does the first turn see the tools of a server that starts slowly (the prompt is positional)?
  - after `/exit` (the app's orderly stop), are the servers' processes gone?
  - after terminating the PTY process (the app's fallback), are they?

Usage: uv run python mcp/s1_pty.py [fast|slow|kill]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1_claude import EVIDENCE, stdio_server, write_mcp  # noqa: E402

from common import sandbox  # noqa: E402
from pty_run import PtyRun, accept_trust, clean_env  # noqa: E402

PROMPT = (
    "Call read_note of the server probe with topic 'a' and answer with the raw text it returns. "
    "If you do not have that tool, answer exactly NO-TOOL."
)


def probe_pids() -> set[int]:
    return {
        p.pid
        for p in psutil.process_iter(["cmdline"])
        if any("stdio_server.py" in part for part in (p.info["cmdline"] or []))
    }


def scenario(name: str, delay: int, how_to_end: str) -> dict:
    root = sandbox(f"s1-pty-{name}")
    env = {"PROBE_MODE": "slow", "PROBE_DELAY": str(delay)} if delay else {}
    mcp = write_mcp(root, name, {"probe": stdio_server(env)})
    before = probe_pids()
    argv = [
        "claude",
        PROMPT,
        "--setting-sources",
        "project,local",
        "--mcp-config",
        str(mcp),
        "--strict-mcp-config",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "mcp__probe__*",
        "--model",
        "haiku",
    ]
    run = PtyRun(argv, root, root / "pty.log", env=clean_env())
    trusted = accept_trust(run, "claude")
    started = time.monotonic()
    seen = "none"
    while time.monotonic() - started < 90:
        screen = run.snapshot()
        if "PROBE-READ-4417" in screen.replace("\n", ""):
            seen = "tool-ran"
            break
        if screen.replace("\n", "").count("NO-TOOL") >= 2:  # the prompt echo has one
            seen = "no-tool"
            break
        time.sleep(1)
    waited = round(time.monotonic() - started, 1)
    alive_servers = sorted(probe_pids() - before)
    run.wait_idle(quiet=4, timeout=60)
    if how_to_end == "exit":
        run.key("esc")
        time.sleep(0.5)
        run.type_line("/exit")
        run.key("enter")
        exited = run.wait_exit(timeout=20)
    else:
        run.proc.terminate(force=True)  # what RunSession.kill() does
        exited = True
    time.sleep(4)
    leaked = sorted(probe_pids() - before)
    for pid in leaked:
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass
    tail = run.snapshot()[-600:]
    run.close()
    return {
        "name": name,
        "delay": delay,
        "trusted": trusted,
        "first_turn": seen,
        "seconds_to_answer": waited,
        "server_pids_while_running": alive_servers,
        "ended_by": how_to_end,
        "exited": exited,
        "leaked_after_end": leaked,
        "screen_tail": tail,
    }


def main() -> None:
    wanted = set(sys.argv[1:]) or {"fast", "slow", "kill"}
    results = []
    if "fast" in wanted:
        results.append(scenario("fast-exit", 0, "exit"))
    if "slow" in wanted:
        results.append(scenario("slow-exit", 12, "exit"))
    if "kill" in wanted:
        results.append(scenario("fast-kill", 0, "kill"))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "screen_tail"}, indent=1))
    out = EVIDENCE / f"s1-pty-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
