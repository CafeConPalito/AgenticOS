"""Phase 18 · spike S2 (PTY part): `agy` interactive with external servers in its plugin.

  - how do we know that every external server has connected before typing the prompt?
    Candidate signal: agy writes each tool's schema to ~/.gemini/antigravity-cli/mcp/<server>/
    when it connects (read-only for us).
  - what happens if the prompt is typed at once, before they connect?
  - processes after the orderly exit and after a terminate.

Usage: uv run python mcp/s2_pty.py [wait|early|kill]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1_claude import EVIDENCE  # noqa: E402
from s2_agy import probe_pids, stdio, write_plugin  # noqa: E402

from common import sandbox  # noqa: E402
from pty_run import PtyRun, accept_trust, clean_env  # noqa: E402

CACHE = Path.home() / ".gemini" / "antigravity-cli" / "mcp"
PROMPT = (
    "Call the MCP tool read_note of the MCP server {server} with topic 'a' and answer with the "
    "raw text it returns."
)


def cache_ready(server: str, since: float) -> bool:
    folder = CACHE / f"agentic-os_{server}"
    return folder.is_dir() and any(f.stat().st_mtime >= since for f in folder.glob("*.json"))


def scenario(name: str, delay: int, mode: str) -> dict:
    root = sandbox(f"s2-pty-{name}")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    server = f"srv{int(time.time())}"
    write_plugin(
        root,
        root / "hooks.jsonl",
        {server: stdio({"PROBE_MODE": "slow", "PROBE_DELAY": str(delay)})},
    )
    before = probe_pids()
    started_wall = time.time()
    run = PtyRun(["agy", "--dangerously-skip-permissions"], root, root / "pty.log", env=clean_env())
    trusted = accept_trust(run, "agy", timeout=45)
    ready = run.wait_screen(r"\? for shortcuts", timeout=30)
    time.sleep(2)
    t0 = time.monotonic()
    connected_after = None
    if mode != "early":
        while time.monotonic() - t0 < 90:
            if cache_ready(server, started_wall):
                connected_after = round(time.monotonic() - t0, 1)
                break
            time.sleep(0.5)
    run.type_line(PROMPT.format(server=f"agentic-os_{server}"))
    run.key("enter")
    answer = "none"
    t1 = time.monotonic()
    while time.monotonic() - t1 < 120:
        screen = run.snapshot().replace("\n", "")
        if "PROBE-READ-4417" in screen:
            answer = "tool-ran"
            break
        time.sleep(1)
    waited = round(time.monotonic() - t1, 1)
    run.wait_idle(quiet=4, timeout=60)
    during = sorted(probe_pids() - before)
    if mode == "kill":
        run.proc.terminate(force=True)
    else:
        run.key("ctrl_c")
        time.sleep(1.5)
        run.key("ctrl_c")
        run.wait_exit(timeout=20)
    time.sleep(4)
    leaked = sorted(probe_pids() - before)
    for pid in leaked:
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass
    tail = re.sub(r"\s+", " ", run.snapshot())[-400:]
    run.close()
    return {
        "name": name,
        "delay": delay,
        "server": server,
        "mode": mode,
        "trusted": trusted,
        "ready_screen": ready,
        "cache_signal_after_s": connected_after,
        "first_turn": answer,
        "seconds_to_answer": waited,
        "server_pids_during": during,
        "leaked_after_end": leaked,
        "screen_tail": tail,
    }


def main() -> None:
    wanted = set(sys.argv[1:]) or {"wait", "early", "kill"}
    results = []
    if "wait" in wanted:
        results.append(scenario("wait", 12, "wait"))
    if "early" in wanted:
        results.append(scenario("early", 40, "early"))
    if "kill" in wanted:
        results.append(scenario("kill", 0, "kill"))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "screen_tail"}, indent=1))
    out = EVIDENCE / f"s2-pty-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
