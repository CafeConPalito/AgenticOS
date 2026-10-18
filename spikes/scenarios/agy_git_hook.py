"""Phase 12, spike S1 (continued): can a PreToolUse hook of the workspace plugin approve git?

agy documents `{"decision": "allow"}` as the output of a PreToolUse hook. The hook here lets only
`git ...` command lines through and leaves anything else to agy's normal permission flow.

Cases (headless `-p`, where an unapproved command is denied):
  1. git commit      -> expected ALLOWED by the hook
  2. a non-git write -> expected DENIED (the hook must not approve it)
  3. git -C . / chained `cd . && git ...` -> how the hook sees the command line
  4. --add-dir with a second repo (no hook): can agy reach it?

    uv run python scenarios/git_hook_agy.py
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import SANDBOX_ROOT  # noqa: E402
from pty_run import clean_env  # noqa: E402
from scenarios.git_permissions import committed, repo, write_json  # noqa: E402

DECIDE = r"""
import json, sys
raw = sys.stdin.read()
try:
    call = json.loads(raw).get("toolCall", {})
except ValueError:
    call = {}
line = str(call.get("args", {}).get("CommandLine", "")).strip()
with open(sys.argv[1], "a", encoding="utf-8") as log:
    log.write(json.dumps({"name": call.get("name"), "line": line}) + "\n")
words = line.split()
if call.get("name") == "run_command" and words[:1] == ["git"]:
    print(json.dumps({"decision": "allow", "reason": "git is authorized by Agentic OS"}))
else:
    print(json.dumps({"decision": "ask"}))
"""


def short(path: Path) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < n < len(buffer) else str(path)


def plugin(path: Path, log: Path) -> None:
    folder = path / ".agents" / "plugins" / "agentic-os"
    decide = folder / "decide.py"
    folder.mkdir(parents=True)
    decide.write_text(DECIDE, "utf-8")
    write_json(folder / "plugin.json", {"name": "agentic-os"})
    command = f"{short(Path(sys.executable))} {short(decide)} {short(log.parent)}\\{log.name}"
    write_json(
        folder / "hooks.json",
        {
            "agentic-os": {
                "PreToolUse": [
                    {"matcher": "run_command", "hooks": [{"type": "command", "command": command}]}
                ]
            }
        },
    )
    # keep the plugin out of git, like the real adapter
    info = path / ".git" / "info" / "exclude"
    info.write_text(".agents/plugins/agentic-os/\n", "utf-8")


def run(argv: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=240,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout + result.stderr).strip().replace("\n", " ")[:170]


def case(name: str, prompt: str, check) -> str:
    path = repo(name)
    log = path.parent / f"{path.name}-hook.log"
    plugin(path, log)
    code, output = run(["agy", "--print", prompt, "--output-format", "text"], path)
    seen = log.read_text("utf-8").strip().splitlines() if log.exists() else []
    verdict = "ALLOWED" if check(path) else "DENIED "
    lines = f"{verdict} {name} · rc={code} · out={output!r}\n         hook saw: {seen}"
    print(lines, flush=True)
    return lines


def main() -> None:
    results = [
        case(
            "hook-git-commit",
            "Run exactly this shell command and nothing else: git commit --allow-empty -m probe-commit . Then answer DONE.",
            committed,
        ),
        case(
            "hook-non-git-write",
            "Run exactly this shell command and nothing else: echo hi > not-git.txt . Then answer DONE.",
            lambda p: (p / "not-git.txt").exists(),
        ),
        case(
            "hook-git-dash-C",
            "Run exactly this shell command and nothing else: git -C . commit --allow-empty -m probe-commit . Then answer DONE.",
            committed,
        ),
        case(
            "hook-git-chained",
            "Run exactly this shell command and nothing else: cd . && git commit --allow-empty -m probe-commit . Then answer DONE.",
            committed,
        ),
    ]
    target = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phases"
        / "12-control-git"
        / "evidencias"
        / "s1-agy-git-hook.md"
    )
    target.write_text(
        "# agy · hook PreToolUse que aprueba git (fase 12)\n\n```\n"
        + "\n".join(results)
        + "\n```\n",
        "utf-8",
    )
    print("evidence:", target)


if __name__ == "__main__":
    main()
    _ = (json, time, SANDBOX_ROOT)
