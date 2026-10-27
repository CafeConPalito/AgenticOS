"""Phase 19 · spike S2: `agy` interactive as the Architect (one CLI per conversation).

Same questions as S1, with the workspace plugin of ADR 0004 in a folder of its own:
  (a) a multi-line message (bracketed paste) arrives as one turn;
  (b) the Stop hook ends each turn and the reply can be read from agy's transcript;
  (c) its own tools are blocked: a PreToolUse hook that denies everything except the
      Architect's MCP server (agy has no `--tools ""`);
  (d) exit and resume with `--conversation <id>` and a new token;
  (e) latency per turn and memory of the idle process tree.

Usage: uv run python architect/s2_agy.py [model]   (from spikes/)
Evidence: docs/phases/19-meta-agentes/evidencias/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1_claude import (  # noqa: E402
    EVIDENCE,
    INSTRUCTIONS,
    PERMISSION_MARKERS,
    TURN1,
    TURN2,
    TURN3,
    TURN4,
    paste,
    start_server,
    tree_rss_mb,
)

from common import ConfigSnapshot, sandbox  # noqa: E402
from pty_run import PtyRun, accept_trust, clean_env  # noqa: E402

HERE = Path(__file__).resolve().parent
GUARD = HERE / "agy_guard.py"
PLUGIN = Path(".agents") / "plugins" / "architect"


def write_plugin(root: Path, port: int, token: str, log: Path) -> None:
    folder = root / PLUGIN
    (folder / "rules").mkdir(parents=True, exist_ok=True)
    (folder / "plugin.json").write_text(json.dumps({"name": "architect"}), "utf-8")
    server = {
        "url": f"http://127.0.0.1:{port}/mcp",
        "headers": {"Authorization": f"Bearer {token}"},
    }
    (folder / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"architect": server}}), "utf-8"
    )

    def command(event: str) -> dict:  # agy runs it with cmd /c: no quotes, no spaces
        return {"type": "command", "command": f"{sys.executable} {GUARD} {event} {log}"}

    hooks = {
        "architect": {
            "PreToolUse": [{"matcher": "*", "hooks": [command("PreToolUse")]}],
            "PostToolUse": [{"matcher": "*", "hooks": [command("PostToolUse")]}],
            "PreInvocation": [command("PreInvocation")],
            "Stop": [command("Stop")],
        }
    }
    (folder / "hooks.json").write_text(json.dumps(hooks), "utf-8")
    (folder / "rules" / "AGENTS.md").write_text(INSTRUCTIONS, "utf-8")


def entries(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text("utf-8").splitlines() if x.strip()]


def count(log: Path, event: str) -> int:
    return sum(1 for e in entries(log) if e["event"] == event)


def last_field(log: Path, key: str) -> str | None:
    for e in reversed(entries(log)):
        value = (e.get("payload") or {}).get(key)
        if value:
            return value
    return None


def lines(path: str | None) -> list[str]:
    if not path or not Path(path).exists():
        return []
    return Path(path).read_text("utf-8", errors="replace").splitlines()


def wait_stop(run: PtyRun, log: Path, stops_before: int, timeout: float = 240) -> dict:
    started = time.monotonic()
    samples: list[tuple[float, int]] = []
    dialog = False
    while time.monotonic() - started < timeout:
        samples.append(
            (round(time.monotonic() - started, 2), len(lines(last_field(log, "transcriptPath"))))
        )
        screen = run.snapshot()
        if any(m in screen for m in PERMISSION_MARKERS) and "Allow" in screen:
            dialog = True
        if count(log, "Stop") > stops_before:
            break
        time.sleep(0.25)
    changes = [t for (t, n), (_, m) in zip(samples[1:], samples[:-1], strict=False) if n != m]
    return {
        "seconds_to_stop": round(time.monotonic() - started, 1),
        "transcript_changes_at": changes[:20],
        "permission_dialog_seen": dialog,
    }


def turn(run: PtyRun, log: Path, text: str, how: str) -> dict:
    stops = count(log, "Stop")
    mark_entries = len(entries(log))
    mark_lines = len(lines(last_field(log, "transcriptPath")))
    if how == "paste":
        paste(run, text)
    else:
        run.type_line(text)
    info = wait_stop(run, log, stops)
    run.wait_idle(quiet=2, timeout=20)
    new = entries(log)[mark_entries:]
    inputs = [
        (e.get("payload") or {}).get("lastUserInput")
        for e in new
        if e["event"] in ("PreInvocation", "Stop")
    ]
    inputs = [i for i in inputs if i]
    info.update(
        {
            "how": how,
            "stops": sum(1 for e in new if e["event"] == "Stop"),
            "last_user_input": inputs[-1] if inputs else None,
            "prompt_received_whole": bool(inputs)
            and all(x.strip() in inputs[-1] for x in text.splitlines()),
            "tools": [
                {
                    "name": ((e.get("payload") or {}).get("toolCall") or {}).get("name"),
                    "server": (
                        ((e.get("payload") or {}).get("toolCall") or {}).get("args") or {}
                    ).get("ServerName"),
                    "decision": e["answer"].get("decision"),
                }
                for e in new
                if e["event"] == "PreToolUse"
            ],
            "transcript_new_lines": lines(last_field(log, "transcriptPath"))[mark_lines:],
            "screen_tail": run.snapshot()[-1200:],
        }
    )
    return info


CACHE = Path.home() / ".gemini" / "antigravity-cli" / "mcp" / "architect_architect"


def connect_mcp(run: PtyRun, since: float, timeout: float = 30) -> float | None:
    """What the app does (RunSession._deferred_prompt_step): `/mcp` makes agy connect the
    plugin's server; agy then caches the tool schemas. Esc closes the panel."""
    t0 = time.monotonic()
    run.type_line("/mcp")
    connected = None
    while time.monotonic() - t0 < timeout:
        if CACHE.is_dir() and any(f.stat().st_mtime >= since for f in CACHE.glob("*.json")):
            connected = round(time.monotonic() - t0, 1)
            break
        time.sleep(0.3)
    time.sleep(1)
    run.key("esc")
    time.sleep(1.5)
    return connected


def exit_agy(run: PtyRun) -> bool:
    run.key("ctrl_c")
    time.sleep(1.5)
    run.key("ctrl_c")
    return run.wait_exit(timeout=20)


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else ""
    root = sandbox("s2-architect")
    log = root / "hooks.jsonl"
    calls = root / "mcp-calls.jsonl"
    before = ConfigSnapshot.take()
    result: dict = {"model": model or "(default)", "root": str(root)}
    extra = ["--model", model] if model else []

    server = start_server(8768, "arch-token-0001", calls)
    write_plugin(root, 8768, "arch-token-0001", log)
    t0 = time.monotonic()
    wall = time.time()
    run = PtyRun(["agy", "--dangerously-skip-permissions", *extra], root, root / "pty-1.log",
                 env=clean_env())  # fmt: skip
    result["trusted"] = accept_trust(run, "agy", timeout=45)
    result["ready"] = run.wait_screen(r"\? for shortcuts", timeout=30)
    result["mcp_connected_after_s"] = connect_mcp(run, wall)
    result["seconds_to_ready"] = round(time.monotonic() - t0, 1)
    result["turn1"] = turn(run, log, TURN1, "type")
    result["rss_idle_mb"] = tree_rss_mb(run.proc.pid)
    result["turn2_multiline"] = turn(run, log, TURN2, "paste")
    result["turn3_escape"] = turn(run, log, TURN3, "type")
    result["rss_after_3_turns_mb"] = tree_rss_mb(run.proc.pid)
    conversation = last_field(log, "conversationId")
    result["conversation_id"] = conversation
    result["transcript_path"] = last_field(log, "transcriptPath")
    result["exited_cleanly"] = exit_agy(run)
    run.close()
    server.terminate()

    server = start_server(8769, "arch-token-0002", calls)
    write_plugin(root, 8769, "arch-token-0002", log)
    t0 = time.monotonic()
    wall = time.time()
    run = PtyRun(
        ["agy", "--dangerously-skip-permissions", "--conversation", str(conversation), *extra],
        root,
        root / "pty-2.log",
        env=clean_env(),
    )
    run.wait_screen(r"\? for shortcuts", timeout=45)
    result["resume_mcp_connected_after_s"] = connect_mcp(run, wall)
    result["resume_seconds_to_ready"] = round(time.monotonic() - t0, 1)
    result["turn4_resumed"] = turn(run, log, TURN4, "type")
    result["conversation_id_after_resume"] = last_field(log, "conversationId")
    result["exited_cleanly_2"] = exit_agy(run)
    run.close()
    server.terminate()

    mcp_calls = (
        [json.loads(x) for x in calls.read_text("utf-8").splitlines() if x.strip()]
        if calls.exists()
        else []
    )
    result["mcp_calls"] = [
        {"token": c["token"], "tool": c["tool"], "args": c["args"]} for c in mcp_calls
    ]
    result["config_changes"] = before.diff(ConfigSnapshot.take())

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s2-agy-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
