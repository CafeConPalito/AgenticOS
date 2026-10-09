"""Shared helpers for the phase 01 spikes: sandboxes, evidence and global-config guards."""

from __future__ import annotations

import contextlib
import difflib
import json
import os
import subprocess
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
    "presence",
    "annotations",
    "bin",
    "mcp",  # tool-schema cache of connected MCP servers
}
GEMINI_VOLATILE_SUFFIXES = (".db-wal", ".db-shm", ".lock", ".pb")
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
        if (
            any(part in GEMINI_VOLATILE_DIRS for part in rel)
            or path.name in GEMINI_VOLATILE_FILES
            or path.name.endswith(GEMINI_VOLATILE_SUFFIXES)
        ):
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
        """Files may be mid-write by a running CLI: retry, then record them as unreadable
        instead of raising (a raise inside config_guard's finally would hide the result)."""
        contents: dict[Path, bytes] = {}
        for path in watched_config_files():
            for attempt in range(5):
                try:
                    contents[path] = _relevant_bytes(path)
                    break
                except FileNotFoundError:
                    break  # deleted between listing and reading: treat as absent
                except (OSError, ValueError):  # ValueError covers JSONDecodeError
                    if attempt == 4:
                        contents[path] = b"<unreadable>"
                    time.sleep(0.2)
        return cls(contents)

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
        try:
            changes.extend(before.diff(ConfigSnapshot.take()))
        except Exception as error:  # noqa: BLE001 - never mask the scenario's own outcome
            changes.append(f"config-guard could not compare: {error!r}")
        status = "UNCHANGED" if not changes else "CHANGED"
        print(f"[config-guard] {label}: global CLI configuration {status}")
        for change in changes:
            for line in change.splitlines():
                print("  " + line)


@dataclass
class CliResult:
    returncode: int
    stdout: str
    stderr: str
    json: dict | None  # last stdout line parsed as JSON, if it was JSON
    events: list[dict]  # every stdout line that parsed as JSON (stream-json)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.json is not None


def run_cli(argv: list[str], cwd: Path, timeout: float = 300) -> CliResult:
    """Runs a CLI headless with a clean environment; never raises on non-JSON output."""
    from pty_run import clean_env  # local import: pty_run imports winpty

    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    events: list[dict] = []
    for line in proc.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    last = events[-1] if events else None
    return CliResult(proc.returncode, proc.stdout, proc.stderr.strip(), last, events)


def wait_for(predicate: Callable[[], bool], timeout: float, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
