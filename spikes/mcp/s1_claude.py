"""Phase 18 · spike S1: external MCP servers in a Claude Code run.

Questions (plan, block 0):
  (a) mcp.json with a stdio server, an HTTP one and `npx` next to a dummy `agentic-os`, with
      --strict-mcp-config: do they connect?
  (b) are ${VAR} expanded in command, args, env, url and headers from the process environment?
  (c) does --disallowedTools mcp__srv__tool block in every permission mode? and a tool in no list?
  (d) a server that fails to start or starts late: does the session go on? how long does it wait?
  (e) do the server processes die when the session ends (clean exit and hard kill)?
  (f) do PreToolUse / PostToolUse with matcher `mcp__.*` give server, tool, input and result?
  (g) does the user's configuration stay the same?

Usage: uv run python mcp/s1_claude.py [scenario ...]   (from spikes/)
Evidence: docs/phases/18-conexiones-mcp/evidencias/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ConfigSnapshot, sandbox  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "18-conexiones-mcp" / "evidencias"
HERE = Path(__file__).resolve().parent
HOOK_LOGGER = REPO / "spikes" / "hook_logger.py"
STDIO = HERE / "servers" / "stdio_server.py"
HTTP = HERE / "servers" / "http_server.py"
PORT = 8765
KEY = "probe-secret-1234"
MODEL = "haiku"
KEEP = {"CLAUDE_CONFIG_DIR", "CLAUDE_CODE_GIT_BASH_PATH"}


def clean_env() -> dict[str, str]:
    env = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in KEEP:
            env[key] = value
        elif upper in {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"} or upper.startswith(
            ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK")
        ):
            continue
        else:
            env[key] = value
    return env


def py(path: Path) -> str:
    return sys.executable if path.suffix == ".py" else str(path)


def stdio_server(env: dict | None = None) -> dict:
    return {"command": sys.executable, "args": [str(STDIO)], "env": env or {}}


def http_server(headers: dict | None = None, url: str | None = None) -> dict:
    return {
        "type": "http",
        "url": url or f"http://127.0.0.1:{PORT}/mcp",
        "headers": headers if headers is not None else {"X-Probe-Key": KEY},
    }


def npx_server(folder: Path) -> dict:
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", str(folder)],
    }


def write_mcp(root: Path, name: str, servers: dict) -> Path:
    dummy = {"type": "http", "url": "http://127.0.0.1:9/r/mcp"}  # stands for agentic-os
    path = root / f"mcp-{name}.json"
    path.write_text(json.dumps({"mcpServers": {"agentic-os": dummy, **servers}}, indent=1), "utf-8")
    return path


def write_settings(root: Path, log: Path, matcher: str) -> Path:
    def hook(event: str) -> list:
        command = f'python "{HOOK_LOGGER.as_posix()}" claude {event} "{log.as_posix()}"'
        return [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]

    path = root / "settings.json"
    path.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": hook("PreToolUse"), "PostToolUse": hook("PostToolUse")}}
        ),
        "utf-8",
    )
    return path


def parse_stream(text: str) -> dict:
    """Condenses claude's stream-json: servers, tools called, results, denials."""
    init: dict = {}
    calls: list[dict] = []
    results: list[dict] = []
    final: dict = {}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            init = {
                "mcp_servers": event.get("mcp_servers"),
                "tools": [t for t in event.get("tools", []) if t.startswith("mcp__")],
            }
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    calls.append({"tool": block["name"], "input": block.get("input")})
        elif kind == "user":
            content = event.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result":
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                    results.append({"error": block.get("is_error"), "text": str(body)[:300]})
        elif kind == "result":
            final = {
                "answer": str(event.get("result"))[:600],
                "denials": [
                    {"tool": d.get("tool_name"), "input": d.get("tool_input")}
                    for d in event.get("permission_denials", [])
                ],
                "cost": event.get("total_cost_usd"),
            }
    return {"init": init, "calls": calls, "results": results, **final}


def run(
    root: Path,
    mcp: Path,
    prompt: str,
    permission: str,
    extra: list[str] | None = None,
    env_extra: dict | None = None,
    timeout: int = 240,
) -> dict:
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        MODEL,
        "--output-format",
        "stream-json",
        "--verbose",
        "--setting-sources",
        "project,local",
        "--mcp-config",
        str(mcp),
        "--strict-mcp-config",
        "--permission-mode",
        permission,
        *(extra or []),
    ]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=root,
        env={**clean_env(), **(env_extra or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        shell=os.name == "nt",
    )
    out = parse_stream(result.stdout)
    out |= {
        "exit": result.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "stderr": result.stderr.strip()[:500],
    }
    return out


def read_hooks(log: Path, mark: int) -> list[dict]:
    if not log.exists():
        return []
    entries = []
    with log.open(encoding="utf-8") as fh:
        fh.seek(mark)
        for line in fh:
            entry = json.loads(line)
            payload = entry.get("payload") or {}
            entries.append(
                {
                    "event": entry["event"],
                    "tool": payload.get("tool_name"),
                    "input": payload.get("tool_input"),
                    "response": str(payload.get("tool_response"))[:200]
                    if "tool_response" in payload
                    else None,
                }
            )
    return entries


PROMPT_ALL = (
    "Call these tools, one after another, and then answer ONLY with the raw text each returned, "
    "one per line: (1) read_note of the server probe with topic 'a'; (2) ping of the server "
    "web with text 'b'; (3) list_allowed_directories of the server fs. If a tool is not "
    "available, write NOT AVAILABLE: <tool name>."
)


def scenario_a(root: Path, **_):
    mcp = write_mcp(
        root, "a", {"probe": stdio_server(), "web": http_server(), "fs": npx_server(root)}
    )
    return {"a": (mcp, PROMPT_ALL, "bypassPermissions", [], {})}


def scenario_b(root: Path, **_):
    servers = {
        "probe": {
            "command": "${AOS_PY}",
            "args": ["${AOS_STDIO}", "${AOS_ARG}"],
            "env": {"PROBE_SECRET": "${AOS_SECRET}", "PROBE_LITERAL": "plain"},
        },
        "web": http_server(headers={"X-Probe-Key": "${AOS_KEY}"}, url="${AOS_URL}"),
    }
    mcp = write_mcp(root, "b", servers)
    prompt = (
        "Call show_env of the server probe three times, with names PROBE_SECRET, PROBE_LITERAL "
        "and AOS_SECRET, and ping of the server web with text 'b'. Answer ONLY with the raw "
        "text each returned, one per line. If a tool is not available write NOT AVAILABLE."
    )
    env = {
        "AOS_PY": sys.executable,
        "AOS_STDIO": str(STDIO),
        "AOS_ARG": "extra-arg",
        "AOS_SECRET": "S3CRET-VALUE-8841",
        "AOS_KEY": KEY,
        "AOS_URL": f"http://127.0.0.1:{PORT}/mcp",
    }
    return {"b": (mcp, prompt, "bypassPermissions", [], env)}


def scenario_c(root: Path, **_):
    mcp = write_mcp(root, "c", {"probe": stdio_server()})
    prompt = (
        "Call write_note of the server probe (topic 'a', text 'b') and then read_note of the "
        "server probe (topic 'a'). Answer ONLY with the raw text each returned, one per line, "
        "or with DENIED: <tool> for the one you could not call."
    )
    out = {}
    for mode in ("default", "acceptEdits", "bypassPermissions"):
        out[f"c_disallow_{mode}"] = (
            mcp,
            prompt,
            mode,
            [
                "--allowedTools",
                "mcp__probe__read_note",
                "--disallowedTools",
                "mcp__probe__write_note",
            ],
            {},
        )
    # a tool that is in no list: write_note is neither allowed nor denied
    out["c_unlisted_default"] = (
        mcp,
        prompt,
        "default",
        ["--allowedTools", "mcp__probe__read_note"],
        {},
    )
    out["c_unlisted_accept"] = (
        mcp,
        prompt,
        "acceptEdits",
        ["--allowedTools", "mcp__probe__read_note"],
        {},
    )
    return out


def scenario_d(root: Path, **_):
    prompt = (
        "Call read_note of the server probe with topic 'a'. If the server probe or the tool is "
        "not available, answer NOT AVAILABLE. Otherwise answer ONLY with the raw text returned."
    )
    crash = write_mcp(
        root,
        "d-crash",
        {"bad": stdio_server({"PROBE_MODE": "crash"}), "probe": stdio_server()},
    )
    missing = write_mcp(
        root,
        "d-missing",
        {"bad": {"command": "this-command-does-not-exist", "args": []}, "probe": stdio_server()},
    )
    slow = write_mcp(
        root,
        "d-slow",
        {"probe": stdio_server({"PROBE_MODE": "slow", "PROBE_DELAY": "25"})},
    )
    return {
        "d_crash": (crash, prompt, "bypassPermissions", [], {}),
        "d_missing_command": (missing, prompt, "bypassPermissions", [], {}),
        "d_slow_start": (slow, prompt, "bypassPermissions", [], {}),
    }


def scenario_f(root: Path, log: Path, **_):
    mcp = write_mcp(root, "f", {"probe": stdio_server(), "web": http_server()})
    settings = write_settings(root, log, "mcp__.*")
    prompt = (
        "Call read_note of the server probe (topic 'a'), then ping of the server web (text "
        "'b'), then a tool that does not exist: call write_note of the server probe with a "
        "missing argument 'topic' omitted. Answer ONLY 'done'."
    )
    return {"f_hooks": (mcp, prompt, "bypassPermissions", ["--settings", str(settings)], {})}


SCENARIOS = {
    "a": scenario_a,
    "b": scenario_b,
    "c": scenario_c,
    "d": scenario_d,
    "f": scenario_f,
}


def probe_python_processes() -> set[int]:
    return {
        p.pid
        for p in psutil.process_iter(["cmdline"])
        if any("stdio_server.py" in part for part in (p.info["cmdline"] or []))
    }


def scenario_e(root: Path) -> dict:
    """(e) server processes after a clean `-p` exit and after a hard kill of the claude process."""
    mcp = write_mcp(root, "e", {"probe": stdio_server()})
    before = probe_python_processes()
    clean = run(
        root,
        mcp,
        "Call pid of the server probe and answer ONLY with the raw text.",
        "bypassPermissions",
    )
    time.sleep(3)
    leaked_clean = sorted(probe_python_processes() - before)

    argv = [
        "claude",
        "-p",
        "Call pid of the server probe, then call read_note of probe 20 times "
        "one after another with different topics, then answer 'done'.",
        "--model",
        MODEL,
        "--output-format",
        "stream-json",
        "--verbose",
        "--setting-sources",
        "project,local",
        "--mcp-config",
        str(mcp),
        "--strict-mcp-config",
        "--permission-mode",
        "bypassPermissions",
    ]
    proc = subprocess.Popen(
        argv,
        cwd=root,
        env=clean_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        shell=os.name == "nt",
    )
    seen_pid = None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        if "PID=" in line:
            seen_pid = line.split("PID=")[1].split('"')[0].split("\\")[0]
            break
    alive_before_kill = bool(seen_pid) and psutil.pid_exists(int(seen_pid))
    try:
        parent = psutil.Process(proc.pid)
        parent.kill()  # only the claude launcher (hard kill, no tree)
    except psutil.Error:
        pass
    proc.wait(timeout=30)
    time.sleep(3)
    survivors = sorted(probe_python_processes() - before)
    for pid in survivors:
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass
    return {
        "clean_exit": {"result": clean.get("answer"), "leaked_pids": leaked_clean},
        "hard_kill": {
            "server_pid_seen": seen_pid,
            "alive_before_kill": alive_before_kill,
            "survivors_after_kill_of_launcher": survivors,
        },
    }


def main() -> None:
    wanted = set(sys.argv[1:])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    root = sandbox("s1-claude-mcp")
    log = root / "hooks.jsonl"
    before = ConfigSnapshot.take()
    server = subprocess.Popen(
        [sys.executable, str(HTTP), str(PORT)], env={**os.environ, "PROBE_KEY": KEY}
    )
    time.sleep(3)
    report: dict = {"sandbox": str(root), "claude": subprocess.getoutput("claude --version")}
    try:
        for letter, build in SCENARIOS.items():
            if wanted and letter not in wanted:
                continue
            for name, (mcp, prompt, permission, extra, env) in build(root, log=log).items():
                mark = log.stat().st_size if log.exists() else 0
                outcome = run(root, mcp, prompt, permission, extra, env)
                if letter == "f":
                    outcome["hooks"] = read_hooks(log, mark)
                report[name] = outcome
                print(name, json.dumps(outcome, ensure_ascii=False, indent=1))
        if not wanted or "e" in wanted:
            report["e_processes"] = scenario_e(root)
            print("e", json.dumps(report["e_processes"], indent=1))
    finally:
        server.kill()
    report["config_changes"] = before.diff(ConfigSnapshot.take())
    out = EVIDENCE / f"s1-claude-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("config changes:", report["config_changes"] or "none")
    print("evidence:", out)


if __name__ == "__main__":
    main()
