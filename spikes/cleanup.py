"""Removes the traces the spikes left in the user's global CLI configuration.

Only entries pointing into the spike sandbox root (AgenticOS-spike) are removed:
- agy:    ~/.gemini/antigravity-cli/settings.json → trustedWorkspaces
- Claude: ~/.claude.json → projects (trust and per-project state for sandbox folders)

Both files are rewritten by the running CLIs, so:
- the target CLI must not be running (checked; the script refuses otherwise);
- each file is backed up and replaced atomically (write to a temp file, then os.replace).

Usage: uv run python cleanup.py [--dry-run] [--agy] [--claude]   (default: both)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import HOME, SANDBOX_ROOT

MARKER = "AgenticOS-spike"
AGY_SETTINGS = HOME / ".gemini" / "antigravity-cli" / "settings.json"
CLAUDE_JSON = HOME / ".claude.json"


def running(image: str) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    return image.lower() in out.lower()


def backup(path: Path) -> None:
    target = SANDBOX_ROOT.parent / "backup" / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    print(f"backup: {target}")


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".agentic-os-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


def clean_agy(dry_run: bool) -> int:
    if not AGY_SETTINGS.exists():
        return 0
    data = json.loads(AGY_SETTINGS.read_text("utf-8"))
    trusted = data.get("trustedWorkspaces") or []
    kept = [p for p in trusted if MARKER not in p]
    removed = len(trusted) - len(kept)
    if removed and not dry_run:
        backup(AGY_SETTINGS)
        data["trustedWorkspaces"] = kept
        atomic_write_json(AGY_SETTINGS, data)
    return removed


def clean_claude(dry_run: bool) -> int:
    if not CLAUDE_JSON.exists():
        return 0
    data = json.loads(CLAUDE_JSON.read_text("utf-8"))
    projects = data.get("projects") or {}
    doomed = [key for key in projects if MARKER in key]
    if doomed and not dry_run:
        backup(CLAUDE_JSON)
        for key in doomed:
            del projects[key]
        atomic_write_json(CLAUDE_JSON, data)
    return len(doomed)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    targets = {a for a in sys.argv[1:] if a in {"--agy", "--claude"}} or {"--agy", "--claude"}
    suffix = " (dry run)" if dry_run else ""
    if "--agy" in targets:
        if running("agy.exe") and not dry_run:
            print("agy is running: close it and retry")
        else:
            print(f"agy trustedWorkspaces removed: {clean_agy(dry_run)}{suffix}")
    if "--claude" in targets:
        if running("claude.exe") and not dry_run:
            print("Claude Code is running (it rewrites ~/.claude.json): close it and retry")
        else:
            print(f"claude projects removed: {clean_claude(dry_run)}{suffix}")


if __name__ == "__main__":
    main()
