"""Removes the traces the spikes left in the user's global CLI configuration.

Only entries pointing into the spike sandbox root (AgenticOS-spike) are removed:
- agy:    ~/.gemini/antigravity-cli/settings.json → trustedWorkspaces
- Claude: ~/.claude.json → projects (trust and per-project state for sandbox folders)
Backups are written next to the sandbox root before any change.

Usage: uv run python cleanup.py [--dry-run]
"""

from __future__ import annotations

import json
import shutil
import sys
import time

from common import HOME, SANDBOX_ROOT

MARKER = "AgenticOS-spike"
AGY_SETTINGS = HOME / ".gemini" / "antigravity-cli" / "settings.json"
CLAUDE_JSON = HOME / ".claude.json"


def backup(path) -> None:
    target = SANDBOX_ROOT.parent / "backup" / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    print(f"backup: {target}")


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
        AGY_SETTINGS.write_text(json.dumps(data, indent=2), "utf-8")
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
        CLAUDE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return len(doomed)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    print(f"agy trustedWorkspaces removed: {clean_agy(dry_run)}{' (dry run)' if dry_run else ''}")
    print(f"claude projects removed: {clean_claude(dry_run)}{' (dry run)' if dry_run else ''}")


if __name__ == "__main__":
    main()
