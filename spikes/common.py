"""Shared helpers for the phase 01 spikes: sandboxes, evidence and global-config guards."""

from __future__ import annotations

import contextlib
import difflib
import json
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "docs" / "phases" / "01-spike-clis" / "evidencias"
SANDBOX_ROOT = Path(os.environ.get("LOCALAPPDATA", HOME)) / "AgenticOS-spike" / "sandbox"

# Global CLI configuration that a spike must never change behind the user's back.
CLAUDE_CONFIG = [HOME / ".claude.json", HOME / ".claude" / "settings.json"]
GEMINI_DIR = HOME / ".gemini"
# Runtime state under ~/.gemini that legitimately changes on every run.
GEMINI_VOLATILE_DIRS = {
    "cache",
    "log",
    "logs",
    "conversations",
    "brain",
    "crashes",
    "updater",
    "tmp",
}
GEMINI_VOLATILE_FILES = {
    "cli.log",
    "conversation_summaries.db",
    "last_check.timestamp",
    "jetski_state.pbtxt",
}


def sandbox(name: str) -> Path:
    """Fresh, empty working directory for one scenario (outside the repo and user folders)."""
    # Unique per run: a previous run may have left a process (e.g. an MCP server) inside it.
    path = SANDBOX_ROOT / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    path.mkdir(parents=True)
    (path / "README.txt").write_text("Agentic OS spike sandbox. Safe to delete.\n", "utf-8")
    return path


def evidence(name: str) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    return EVIDENCE / name


def _gemini_files() -> list[Path]:
    if not GEMINI_DIR.exists():
        return []
    files = []
    for path in GEMINI_DIR.rglob("*"):
        rel = path.relative_to(GEMINI_DIR).parts
        if any(part in GEMINI_VOLATILE_DIRS for part in rel) or path.name in GEMINI_VOLATILE_FILES:
            continue
        if path.is_file():
            files.append(path)
    return files


def _relevant_bytes(path: Path) -> bytes:
    """~/.claude.json holds run state too; keep only its configuration (MCP servers)."""
    if path.name != ".claude.json":
        return path.read_bytes()
    data = json.loads(path.read_text("utf-8"))
    relevant = {
        "mcpServers": data.get("mcpServers"),
        "projects": {
            key: value.get("mcpServers")
            for key, value in (data.get("projects") or {}).items()
            if value.get("mcpServers")
        },
    }
    return json.dumps(relevant, indent=1, sort_keys=True).encode()


def watched_config_files() -> list[Path]:
    return [p for p in CLAUDE_CONFIG if p.exists()] + _gemini_files()


@dataclass
class ConfigSnapshot:
    contents: dict[Path, bytes]

    @classmethod
    def take(cls) -> ConfigSnapshot:
        return cls({p: _relevant_bytes(p) for p in watched_config_files()})

    def diff(self, other: ConfigSnapshot) -> list[str]:
        changes: list[str] = []
        for path in sorted(set(self.contents) | set(other.contents)):
            before, after = self.contents.get(path), other.contents.get(path)
            if before == after:
                continue
            if before is None or after is None:
                changes.append(f"{'added' if before is None else 'removed'}: {path}")
                continue
            lines = difflib.unified_diff(
                before.decode("utf-8", "replace").splitlines(),
                after.decode("utf-8", "replace").splitlines(),
                lineterm="",
                n=0,
            )
            body = [ln for ln in lines if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
            changes.append("\n".join([f"changed: {path}", *body[:40]]))
        return changes


@contextlib.contextmanager
def config_guard(label: str) -> Iterator[list[str]]:
    """Reports whether the scenario changed real CLI configuration (MCP servers, settings…)."""
    before = ConfigSnapshot.take()
    changes: list[str] = []
    try:
        yield changes
    finally:
        changes.extend(before.diff(ConfigSnapshot.take()))
        status = "UNCHANGED" if not changes else "CHANGED"
        print(f"[config-guard] {label}: global CLI configuration {status}")
        for change in changes:
            for line in change.splitlines():
                print("  " + line)


def wait_for(predicate: Callable[[], bool], timeout: float, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
