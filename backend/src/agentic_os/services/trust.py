"""Forgets the folder trust the CLIs saved for task worktrees (ADR 0004, ADR 0009).

Claude Code keeps it in `~/.claude.json → projects` (keys like "D:/web.wt/T-7") and agy in
`~/.gemini/antigravity-cli/settings.json → trustedWorkspaces` ("D:\\web.wt\\T-7"). Both files
are rewritten by the running CLIs (spike, cleanup.py): editing one while its CLI is open could
lose the CLI's own changes. So a removed worktree is only *queued* here, and the entries are
removed when that CLI is not running; until then they wait in `<data_dir>/trust-cleanup.json`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import structlog
from sqlalchemy import select

from agentic_os.models import Cli, CliAccount
from agentic_os.services import proc

log = structlog.get_logger()

IMAGES = {"claude": "claude.exe", "agy": "agy.exe"}


def claude_config() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home()) / ".claude.json"


def agy_settings() -> Path:
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def process_running(image: str) -> bool:
    try:
        out = proc.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"], 10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True  # unknown: do not touch the file
    return image.lower() in out.lower()


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".agentic-os-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


def _load(path: Path) -> dict | None:
    """The config as a dict, or None when it is missing or not valid JSON (then untouched)."""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def forget_claude(path: Path, folders: list[str]) -> list[str]:
    """Removes the folders from `projects`; returns the ones that are gone (removed or absent)."""
    data = _load(path)
    if data is None:
        return folders if not path.exists() else []
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return folders
    doomed = [key for key in projects if any(same_path(key, f) for f in folders)]
    if doomed:
        for key in doomed:
            del projects[key]
        _write_json(path, data)
    return folders


def forget_agy(path: Path, folders: list[str]) -> list[str]:
    data = _load(path)
    if data is None:
        return folders if not path.exists() else []
    trusted = data.get("trustedWorkspaces")
    if not isinstance(trusted, list):
        return folders
    kept = [
        p for p in trusted if not (isinstance(p, str) and any(same_path(p, f) for f in folders))
    ]
    if len(kept) != len(trusted):
        data["trustedWorkspaces"] = kept
        _write_json(path, data)
    return folders


def account_claude_config(config_dir: str | Path) -> Path:
    """Where Claude Code keeps the folder trust of an account with its own login folder."""
    return Path(config_dir) / ".claude.json"


def account_trust_files(sessions) -> dict[str, list[Path]]:
    """The trust files of the accounts that keep their login in a folder of their own."""
    with sessions() as db:
        folders = db.scalars(
            select(CliAccount.config_dir).where(
                CliAccount.cli == Cli.CLAUDE.value, CliAccount.config_dir.is_not(None)
            )
        ).all()
    return {"claude": [account_claude_config(folder) for folder in folders]}


class TrustCleaner:
    def __init__(
        self,
        pending_file: Path,
        configs: dict[str, Path] | None = None,
        is_running: Callable[[str], bool] = process_running,
        extra_configs: Callable[[], dict[str, list[Path]]] | None = None,
    ) -> None:
        self._pending_file = pending_file
        self._configs = configs or {"claude": claude_config(), "agy": agy_settings()}
        self._is_running = is_running
        # More files of a CLI that appear while the app runs: the accounts' own folders.
        self._extra_configs = extra_configs or (lambda: {})
        self._lock = threading.Lock()

    def _pending(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self._pending_file.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        return {cli: list(data.get(cli, [])) for cli in IMAGES}

    def _save(self, pending: dict[str, list[str]]) -> None:
        self._pending_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self._pending_file, pending)

    def forget(self, folder: str) -> None:
        """Queues a removed worktree and tries to clean it right away."""
        with self._lock:
            pending = self._pending()
            for cli in IMAGES:
                if not any(same_path(folder, f) for f in pending.get(cli, [])):
                    pending.setdefault(cli, []).append(folder)
            self._save(pending)
        self.flush()

    def flush(self) -> dict[str, int]:
        """Cleans what it can now; returns how many folders are still pending per CLI."""
        with self._lock:
            pending = self._pending()
            if not any(pending.values()):
                return {}
            forgetters = {"claude": forget_claude, "agy": forget_agy}
            extra = self._extra_configs()
            for cli, folders in pending.items():
                if not folders or self._is_running(IMAGES[cli]):
                    continue
                try:
                    done = forgetters[cli](self._configs[cli], folders)
                except OSError:
                    log.exception("could not clean the folder trust", cli=cli)
                    continue
                # The accounts' own files are best effort, each on its own: one locked file must
                # not undo what the main one already got.
                for path in extra.get(cli, []):
                    try:
                        forgetters[cli](path, folders)
                    except OSError:
                        log.exception("could not clean an account's folder trust", path=str(path))
                pending[cli] = [f for f in folders if f not in done]
            self._save(pending)
            return {cli: len(f) for cli, f in pending.items() if f}
