"""Phase 17 · spike S2: Antigravity CLI (`agy`) skills inside the workspace plugin (ADR 0004).

Questions:
  (a) does `skills/<name>/SKILL.md` inside `.agents/plugins/agentic-os/` load as a skill?
  (b) which skills does agy see besides ours (built-in, global ~/.gemini/config, workspace)?
  (c) which hook event tells us that a skill was activated, and with what payload?
  (d) does the skill's script run (with --dangerously-skip-permissions)?

Usage: uv run python skills/s2_agy.py        (from spikes/)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ConfigSnapshot, sandbox  # noqa: E402
from pty_run import clean_env  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"
HOOK_LOGGER = REPO / "spikes" / "hook_logger.py"
SKILL = "aos-probe-agy"
MARK = "PROBE-SKILL-LOADED-8842"
SCRIPT_MARK = "PROBE-SCRIPT-RAN-6630"

LIST_PROMPT = (
    "Without calling any tool, look at the skills you have available. Answer ONLY with a JSON "
    "array of their exact names, nothing else. If you have none, answer []."
)
USE_PROMPT = (
    f"Use your skill named {SKILL} and do exactly what it says. Then answer with the text it "
    "told you to answer."
)


def write_plugin(root: Path, log: Path) -> None:
    plugin = root / ".agents" / "plugins" / "agentic-os"
    skill = plugin / "skills" / SKILL
    (skill / "scripts").mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": "agentic-os"}), "utf-8")
    script = skill / "scripts" / "probe.py"
    script.write_text(f'print("{SCRIPT_MARK}")\n', "utf-8")
    (skill / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: Probe skill of the Agentic OS spike. Use it only "
        f"when explicitly asked for {SKILL}.\n---\n\n"
        f"Run the script `scripts/probe.py` of this skill with python (absolute path: "
        f"{script}) and then answer with the line `{MARK}` followed by the script's output.\n",
        "utf-8",
    )

    # agy runs hooks through cmd.exe: unquoted paths without spaces (evidence P9, phase 01).
    def hook(event: str) -> dict:
        return {"type": "command", "command": f"python {HOOK_LOGGER} agy {event} {log}"}

    hooks = {
        "agentic-os": {
            "PreToolUse": [{"matcher": ".*", "hooks": [hook("PreToolUse")]}],
            "PostToolUse": [{"matcher": ".*", "hooks": [hook("PostToolUse")]}],
            "PreInvocation": [hook("PreInvocation")],
            "Stop": [hook("Stop")],
        }
    }
    (plugin / "hooks.json").write_text(json.dumps(hooks), "utf-8")


def run(name: str, prompt: str, root: Path) -> dict:
    argv = ["agy", "-p", prompt, "--output-format", "json", "--dangerously-skip-permissions"]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=root,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        shell=os.name == "nt",
    )
    answer = result.stdout.strip()
    try:
        data = json.loads(answer)
        answer = data.get("result", data.get("response", answer))
    except json.JSONDecodeError:
        pass
    return {
        "scenario": name,
        "exit": result.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "answer": str(answer)[:2000],
        "stderr": result.stderr.strip()[:800],
    }


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    root = sandbox("s2-agy-skills")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)  # agy walks up to a repo root
    log = root / "hooks.jsonl"
    write_plugin(root, log)
    before = ConfigSnapshot.take()
    results = []
    for name, prompt in (("list", LIST_PROMPT), ("use", USE_PROMPT)):
        mark = log.stat().st_size if log.exists() else 0
        outcome = run(name, prompt, root)
        hooks = []
        if log.exists():
            with log.open(encoding="utf-8") as fh:
                fh.seek(mark)
                for line in fh:
                    entry = json.loads(line)
                    payload = entry.get("payload") or {}
                    if entry["event"] in ("PreToolUse", "PostToolUse"):
                        hooks.append(
                            {
                                "event": entry["event"],
                                "payload": json.dumps(payload, ensure_ascii=False)[:700],
                            }
                        )
                    else:
                        hooks.append({"event": entry["event"]})
        outcome["hooks"] = hooks
        results.append(outcome)
        print(json.dumps(outcome, ensure_ascii=False, indent=1))
    changes = before.diff(ConfigSnapshot.take())
    report = {"sandbox": str(root), "config_changes": changes, "results": results}
    out = EVIDENCE / f"s2-agy-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("config changes:", changes or "none")
    print("evidence:", out)


if __name__ == "__main__":
    main()
