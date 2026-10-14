"""Phase 10 · S1/S2: capture the status line payload of a real CLI session (quota fields).

    uv run python quota_probe.py claude   # rate_limits.five_hour / seven_day
    uv run python quota_probe.py agy      # quota.<bucket>

The status line command appends every JSON payload it receives to <out>/payloads.jsonl.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from pty_run import PtyRun, accept_trust, clean_env

HERE = Path(__file__).parent
DUMP = HERE / "dump_stdin.py"
PYTHON = (HERE / ".venv" / "Scripts" / "python.exe").as_posix()


def claude(out: Path, project: Path) -> None:
    exe = shutil.which("claude") or "claude"
    command = f'"{PYTHON}" "{DUMP.as_posix()}" "{(out / "payloads.jsonl").as_posix()}"'
    settings = json.dumps({"statusLine": {"type": "command", "command": command}})
    run = PtyRun(
        [exe, "--setting-sources", "project,local", "--settings", settings],
        project,
        out / "pty.log",
        env=clean_env(),
    )
    try:
        accept_trust(run, "claude", timeout=30)
        time.sleep(3)
        run.type_line("Responde solo con la palabra: ok")
        run.wait_idle(quiet=6, timeout=90)
        time.sleep(2)
        (out / "screen.txt").write_text(run.snapshot(), "utf-8")
        run.type_line("/usage")
        time.sleep(4)
        (out / "usage-screen.txt").write_text(run.snapshot(), "utf-8")
        run.key("esc")
        run.type_line("/exit")
        run.wait_exit(15)
    finally:
        run.close()


AGY_SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def agy(out: Path, project: Path, variant: str) -> None:
    """Variants: `workspace` (<project>/.agents/settings.json), `plugin` (statusLine key in the
    workspace plugin's plugin.json) and `global` (the user's settings.json, restored after)."""
    exe = shutil.which("agy") or "agy"
    # agy runs the command through cmd.exe: backslashes, no quotes (the paths have no spaces).
    python, dump = PYTHON.replace("/", "\\"), str(DUMP)
    command = f"{python} {dump} {out / 'payloads.jsonl'}"
    block = {"statusLine": {"type": "command", "command": command}}
    backup = AGY_SETTINGS.read_text("utf-8") if AGY_SETTINGS.exists() else None
    if variant == "workspace":
        (project / ".agents").mkdir()
        (project / ".agents" / "settings.json").write_text(json.dumps(block), "utf-8")
    elif variant == "plugin":
        plugin = project / ".agents" / "plugins" / "probe"
        plugin.mkdir(parents=True)
        (plugin / "plugin.json").write_text(json.dumps({"name": "probe", **block}), "utf-8")
    elif variant == "global":
        data = json.loads(backup) if backup else {}
        AGY_SETTINGS.write_text(json.dumps({**data, **block}, indent=2), "utf-8")
    run = PtyRun([exe], project, out / "pty.log", env=clean_env())
    try:
        accept_trust(run, "agy", timeout=30)
        time.sleep(5)
        run.type_line("Responde solo con la palabra: ok")
        run.wait_idle(quiet=8, timeout=90)
        time.sleep(2)
        (out / "screen.txt").write_text(run.snapshot(), "utf-8")
        run.type_line("/usage")
        time.sleep(6)
        (out / "usage-screen.txt").write_text(run.snapshot(), "utf-8")
        run.key("esc")
        run.type_line("/exit")
        run.wait_exit(15)
    finally:
        run.close()
        if variant == "global" and backup is not None:
            AGY_SETTINGS.write_text(backup, "utf-8")


def main() -> None:
    cli = sys.argv[1] if len(sys.argv) > 1 else "claude"
    variant = sys.argv[2] if len(sys.argv) > 2 else ""
    out = HERE / "out" / f"quota-{cli}{'-' + variant if variant else ''}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "payloads.jsonl").unlink(missing_ok=True)
    project = Path(tempfile.mkdtemp(prefix="quota-probe-"))
    if cli == "claude":
        claude(out, project)
    else:
        agy(out, project, variant)
    print("payloads:", (out / "payloads.jsonl").exists(), "->", out)


if __name__ == "__main__":
    main()
