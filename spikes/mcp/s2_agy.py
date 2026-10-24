"""Phase 18 · spike S2: external MCP servers in an `agy` run (workspace plugin, ADR 0004).

Questions (plan, block 0):
  (a) does the plugin's mcp_config.json take stdio (command/args/env), HTTP with headers and npx?
  (b) are ${VAR} expanded (command, args, env, url, headers)? does a stdio server inherit the
      process environment?
  (c) can tools be filtered per server (`disabledTools` / `enabledTools`, seen in the binary)?
  (d) do the hooks see the MCP calls, with which name (prefix)?
  (e) a server that crashes or whose command does not exist: does the run go on?
  (f) processes after the run; the user's configuration stays the same.

Usage: uv run python mcp/s2_agy.py [a b c d e]   (from spikes/). Headless `agy -p`.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1_claude import HTTP, KEY, PORT, STDIO  # noqa: E402

from common import ConfigSnapshot, sandbox  # noqa: E402
from pty_run import clean_env  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "18-conexiones-mcp" / "evidencias"
HOOK_LOGGER = REPO / "spikes" / "hook_logger.py"

SHORT_PROMPT = (
    "Call read_note with topic 'a' (server probe), then ping with text 'b' (server web), then "
    "write_note with topic 'a' and text 'b' (server probe). Answer ONLY with the raw text each "
    "returned, one per line, or NOT AVAILABLE <tool name> for one you cannot call."
)
TOOLS_PROMPT = (
    "Call the tools below and then answer ONLY with one line per call: <exact tool name you "
    "used> => <raw text it returned>. Calls: read_note with topic 'a' (server probe); ping with "
    "text 'b' (server web); write_note with topic 'a' and text 'b' (server probe); show_env "
    "with name AOS_SECRET (server probe). If a tool is not available write: "
    "NOT AVAILABLE <tool name>."
)


def write_plugin(root: Path, log: Path, servers: dict) -> None:
    plugin = root / ".agents" / "plugins" / "agentic-os"
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": "agentic-os"}), "utf-8")
    (plugin / "mcp_config.json").write_text(json.dumps({"mcpServers": servers}, indent=1), "utf-8")

    def hook(event: str) -> dict:
        return {"type": "command", "command": f"python {HOOK_LOGGER} agy {event} {log}"}

    hooks = {
        "agentic-os": {
            "PreToolUse": [{"matcher": ".*", "hooks": [hook("PreToolUse")]}],
            "PostToolUse": [{"matcher": ".*", "hooks": [hook("PostToolUse")]}],
        }
    }
    (plugin / "hooks.json").write_text(json.dumps(hooks), "utf-8")


def stdio(env: dict | None = None, **extra) -> dict:
    return {"command": sys.executable, "args": [str(STDIO)], "env": env or {}, **extra}


def http(headers: dict | None = None, url: str | None = None, **extra) -> dict:
    return {
        "url": url or f"http://127.0.0.1:{PORT}/mcp",
        "headers": headers if headers is not None else {"X-Probe-Key": KEY},
        **extra,
    }


def probe_pids() -> set[int]:
    return {
        p.pid
        for p in psutil.process_iter(["cmdline"])
        if any("stdio_server.py" in part for part in (p.info["cmdline"] or []))
    }


def run(root: Path, prompt: str, env_extra: dict | None = None, timeout: int = 420) -> dict:
    argv = ["agy", "-p", prompt, "--output-format", "json", "--dangerously-skip-permissions"]
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
    answer = result.stdout.strip()
    try:
        data = json.loads(answer)
        answer = data.get("result", data.get("response", answer))
    except json.JSONDecodeError:
        pass
    return {
        "exit": result.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "answer": str(answer)[:1800],
        "stderr": result.stderr.strip()[:500],
    }


def hooks_since(log: Path, mark: int) -> list[dict]:
    if not log.exists():
        return []
    out = []
    with log.open(encoding="utf-8") as fh:
        fh.seek(mark)
        for line in fh:
            entry = json.loads(line)
            payload = entry.get("payload") or {}
            out.append(
                {"event": entry["event"], "payload": json.dumps(payload, ensure_ascii=False)[:3500]}
            )
    return out


def scenarios(root: Path) -> dict[str, tuple[dict, str, dict]]:
    npx = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", str(root)]}
    vars_env = {
        "AOS_PY": sys.executable,
        "AOS_STDIO": str(STDIO),
        "AOS_ARG": "extra-arg",
        "AOS_SECRET": "S3CRET-VALUE-8841",
        "AOS_KEY": KEY,
        "AOS_URL": f"http://127.0.0.1:{PORT}/mcp",
    }
    return {
        "d_names": ({"probe": stdio(), "web": http()}, SHORT_PROMPT, {}),
        "a_basic": (
            {"probe": stdio({"PROBE_LITERAL": "plain"}), "web": http(), "fs": npx},
            TOOLS_PROMPT + " Also call list_allowed_directories (server fs).",
            {"AOS_SECRET": "INHERITED-5531"},
        ),
        "b_vars": (
            {
                "probe": {
                    "command": "${AOS_PY}",
                    "args": ["${AOS_STDIO}", "${AOS_ARG}"],
                    "env": {"PROBE_SECRET": "${AOS_SECRET}"},
                },
                "web": http(headers={"X-Probe-Key": "${AOS_KEY}"}, url="${AOS_URL}"),
            },
            TOOLS_PROMPT + " Also call show_env with name PROBE_SECRET (server probe).",
            vars_env,
        ),
        "c_filter_disabled": (
            {"probe": stdio(disabledTools=["write_note"]), "web": http()},
            SHORT_PROMPT,
            {},
        ),
        "c_filter_enabled": (
            {"probe": stdio(enabledTools=["read_note"]), "web": http()},
            SHORT_PROMPT,
            {},
        ),
        "e_failing": (
            {
                "bad": stdio({"PROBE_MODE": "crash"}),
                "missing": {"command": "this-command-does-not-exist", "args": []},
                "probe": stdio(),
            },
            "Call read_note with topic 'a' (server probe) and answer ONLY with the exact tool "
            "name used and the raw text. If it is not available write NOT AVAILABLE.",
            {},
        ),
    }


def main() -> None:
    wanted = set(sys.argv[1:])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    root = sandbox("s2-agy-mcp")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    log = root / "hooks.jsonl"
    before_cfg = ConfigSnapshot.take()
    server = subprocess.Popen(
        [sys.executable, str(HTTP), str(PORT)], env={**os.environ, "PROBE_KEY": KEY}
    )
    time.sleep(3)
    report: dict = {"sandbox": str(root), "agy": subprocess.getoutput("agy --version")}
    before_pids = probe_pids()
    try:
        for name, (servers, prompt, env) in scenarios(root).items():
            if wanted and name[0] not in wanted:
                continue
            write_plugin(root, log, servers)
            mark = log.stat().st_size if log.exists() else 0
            outcome = run(root, prompt, env)
            outcome["hooks"] = hooks_since(log, mark)
            outcome["server_pids_alive_after"] = sorted(probe_pids() - before_pids)
            report[name] = outcome
            print(name, json.dumps(outcome, ensure_ascii=False, indent=1))
            for pid in outcome["server_pids_alive_after"]:
                try:
                    psutil.Process(pid).kill()
                except psutil.Error:
                    pass
    finally:
        server.kill()
    report["config_changes"] = before_cfg.diff(ConfigSnapshot.take())
    out = EVIDENCE / f"s2-agy-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("config changes:", report["config_changes"] or "none")
    print("evidence:", out)


if __name__ == "__main__":
    main()
