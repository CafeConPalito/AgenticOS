"""Phase 12, spikes S1 (agy) and S2 (Claude Code): can git commands be pre-approved per run?

Each case runs the CLI headless (`-p`, where anything not allowed is denied instead of asked) in a
fresh sandbox repo and asks for a real `git commit`. The evidence is the repository itself
(was the commit made?), never what the model says.

    python scenarios/git_permissions.py agy
    python scenarios/git_permissions.py claude
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import SANDBOX_ROOT  # noqa: E402
from pty_run import clean_env  # noqa: E402

PROMPT = (
    "Run exactly this shell command and nothing else: git commit --allow-empty -m probe-commit . "
    "Then answer with the single word DONE."
)
PROMPT_CHAINED = (
    "Run exactly this shell command and nothing else: cd . && git commit --allow-empty -m "
    "probe-commit . Then answer with the single word DONE."
)
PROMPT_DASH_C = (
    "Run exactly this shell command and nothing else: git -C . commit --allow-empty -m "
    "probe-commit . Then answer with the single word DONE."
)


def repo(name: str) -> Path:
    path = SANDBOX_ROOT / f"git-{name}-{time.strftime('%H%M%S')}"
    path.mkdir(parents=True)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "T"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, env=env)
    (path / "a.txt").write_text("1\n", "utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "base"], check=True, env=env)
    return path


def committed(path: Path) -> bool:
    out = subprocess.run(
        ["git", "-C", str(path), "log", "--format=%s"], capture_output=True, text=True
    ).stdout
    return "probe-commit" in out.split()


def run(argv: list[str], cwd: Path, timeout: int = 240) -> tuple[int, str]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=clean_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"


def report(case: str, path: Path, code: int, output: str, lines: list[str]) -> None:
    ok = committed(path)
    line = f"{'ALLOWED' if ok else 'DENIED '} {case} · rc={code} · {output.replace(chr(10), ' ')[:160]}"
    print(line, flush=True)
    lines.append(line)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), "utf-8")


# ---------------------------------------------------------------------------------- agy
def agy_case(name: str, mode: list[str], setup, prompt: str = PROMPT) -> str:
    path = repo(name)
    if setup is not None:
        setup(path)
    code, output = run(["agy", "--print", prompt, "--output-format", "text", *mode], path)
    out: list[str] = []
    report(f"agy {name}", path, code, output, out)
    return out[0]


def agy() -> list[str]:
    results = []
    results.append(agy_case("control-default", [], None))
    for rule in ("command(git *)", "command(git:*)", "command(git commit*)", "command(git)"):
        slug = "".join(c if c.isalnum() else "_" for c in rule)

        def project_settings(path: Path, rule=rule) -> None:
            write_json(path / ".agents" / "settings.json", {"permissions": {"allow": [rule]}})

        results.append(agy_case(f"project-settings-{slug}", [], project_settings))
    return results


# -------------------------------------------------------------------------------- claude
def claude_case(name: str, args: list[str], prompt: str = PROMPT) -> str:
    path = repo(name)
    code, output = run(["claude", "-p", prompt, "--output-format", "text", *args], path)
    out: list[str] = []
    report(f"claude {name}", path, code, output, out)
    return out[0]


def claude() -> list[str]:
    results = []
    # print mode has no dialog: what is not allowed is denied.
    results.append(claude_case("control-default", ["--permission-mode", "default"]))
    allow = ["--allowedTools", "Bash(git:*)"]
    results.append(claude_case("allow-git-prefix", ["--permission-mode", "default", *allow]))
    results.append(
        claude_case(
            "allow-git-prefix-chained", ["--permission-mode", "default", *allow], PROMPT_CHAINED
        )
    )
    results.append(
        claude_case(
            "allow-git-prefix-dash-C", ["--permission-mode", "default", *allow], PROMPT_DASH_C
        )
    )
    results.append(
        claude_case(
            "allow-git-star-and-ps",
            ["--permission-mode", "default", "--allowedTools", "Bash(git *)", "PowerShell(git *)"],
        )
    )
    return results


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which not in ("agy", "claude"):
        raise SystemExit("usage: git_permissions.py agy|claude")
    lines = agy() if which == "agy" else claude()
    target = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phases"
        / "12-control-git"
        / "evidencias"
        / f"s{'1' if which == 'agy' else '2'}-{which}-git-permissions.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"# {which} · preaprobar comandos de git (fase 12)\n\n```\n" + "\n".join(lines) + "\n```\n",
        "utf-8",
    )
    shutil.rmtree(SANDBOX_ROOT, ignore_errors=True) if "--clean" in sys.argv else None
    print(f"evidence: {target}")
