"""The data folder (phase 08, ADR 0012): what it holds, and moving it somewhere else.

Its location is kept in a pointer in the fixed home folder (`config.read_pointer`). Moving
happens in two steps, because the database and the logs are open while the backend runs:
1. `request_move` checks the target and writes `pending_move` in the pointer; the backend
   then restarts (exit code 75, the desktop shell launches it again);
2. at the next start, before anything is opened, `apply_pending_move` copies the folder,
   checks the copy, rewrites the paths stored in the database, points to the new folder and
   deletes the old one. If anything fails the data stays where it was and the error is kept
   in the pointer for Settings to show.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from agentic_os.config import POINTER_FILE, home_dir, read_pointer
from agentic_os.db.session import DB_FILENAME
from agentic_os.errors import ApiError

log = structlog.get_logger(__name__)

RESTART_EXIT_CODE = 75  # the desktop shell relaunches the backend at once (ADR 0012)
# What the home folder keeps even when the data lives elsewhere.
HOME_ONLY = {POINTER_FILE}


def write_pointer(data: dict, home: Path | None = None) -> None:
    home = home or home_dir()
    home.mkdir(parents=True, exist_ok=True)
    target = home / POINTER_FILE
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    os.replace(temporary, target)


def same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(child: Path, parent: Path) -> bool:
    child_key = os.path.normcase(os.path.abspath(child))
    parent_key = os.path.normcase(os.path.abspath(parent))
    return child_key.startswith(parent_key.rstrip("\\/") + os.sep)


# ---------------------------------------------------------------- size
@dataclass
class Usage:
    database: int = 0  # the database, its WAL and the backups
    sessions: int = 0  # the runs' terminal logs and files
    logs: int = 0  # the backend's own logs
    other: int = 0

    @property
    def total(self) -> int:
        return self.database + self.sessions + self.logs + self.other


def _tree_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += (Path(root) / name).stat().st_size
    return total


def disk_usage(data_dir: Path) -> Usage:
    usage = Usage()
    try:
        entries = list(data_dir.iterdir())
    except OSError:
        return usage
    for entry in entries:
        size = _tree_size(entry) if entry.is_dir() else _file_size(entry)
        if entry.name.startswith(Path(DB_FILENAME).stem) or entry.name == "backups":
            usage.database += size
        elif entry.name == "runs":
            usage.sessions += size
        elif entry.name == "logs":
            usage.logs += size
        else:
            usage.other += size
    return usage


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# ---------------------------------------------------------------- moving
def _empty_enough(target: Path, home: Path) -> bool:
    """An empty folder, or the home folder with only what always stays there."""
    try:
        names = {p.name for p in target.iterdir()}
    except OSError:
        return False
    if same(target, home):
        return names <= HOME_ONLY | {"logs"}
    return not names


def request_move(data_dir: Path, target: str, home: Path | None = None) -> Path:
    """Checks the target and records the move for the next start. The caller makes sure no
    run is active (409 `runs_active`)."""
    home = home or home_dir()
    if os.environ.get("AGENTIC_OS_DATA_DIR"):
        raise ApiError(409, "data_dir_fixed", "the data folder is set by AGENTIC_OS_DATA_DIR")
    path = Path(target).expanduser()
    if not path.is_absolute():
        raise ApiError(422, "path_not_absolute", "use a full path to the folder", "to")
    path = Path(os.path.abspath(path))
    if same(path, data_dir):
        raise ApiError(422, "same_data_dir", "the data is already in that folder", "to")
    if inside(path, data_dir) or inside(data_dir, path):
        raise ApiError(422, "data_dir_nested", "the folders are inside each other", "to")
    if path.exists():
        if not path.is_dir():
            raise ApiError(422, "not_a_folder", "the path is not a folder", "to")
        if not _empty_enough(path, home):
            raise ApiError(422, "folder_not_empty", "choose an empty folder", "to")
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".agentic-os-probe"
        probe.write_text("ok", "utf-8")
        probe.unlink()
    except OSError as error:
        raise ApiError(422, "folder_not_accessible", str(error), "to") from error
    needed = disk_usage(data_dir).total
    if shutil.disk_usage(path).free < needed * 1.1 + 50_000_000:
        raise ApiError(422, "not_enough_space", "there is not enough free space there", "to")
    pointer = read_pointer(home)
    pointer["pending_move"] = {"from": str(data_dir), "to": str(path)}
    pointer["last_error"] = None
    write_pointer(pointer, home)
    log.info("data_dir_move_requested", source=str(data_dir), target=str(path))
    return path


def apply_pending_move(home: Path | None = None) -> bool:
    """Called at startup before the settings are read. True if the data was moved."""
    home = home or home_dir()
    pointer = read_pointer(home)
    move = pointer.get("pending_move")
    if not isinstance(move, dict):
        return False
    source, target = Path(move["from"]), Path(move["to"])
    copied: list[Path] = []
    try:
        for entry in source.iterdir():
            if same(source, home) and entry.name in HOME_ONLY:
                continue
            destination = target / entry.name
            copied.append(destination)
            if entry.is_dir():
                shutil.copytree(entry, destination)
            else:
                shutil.copy2(entry, destination)
        database = target / DB_FILENAME
        if database.exists():
            _check_and_rewrite(database, source, target)
    except Exception as error:  # the data stays where it was
        for path in copied:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        pointer.update(pending_move=None, last_error=f"{type(error).__name__}: {error}")
        write_pointer(pointer, home)
        return False
    write_pointer(
        {"data_dir": None if same(target, home) else str(target), "pending_move": None}, home
    )
    _remove_old(source, home)
    return True


def _check_and_rewrite(database: Path, source: Path, target: Path) -> None:
    """The copy must open and pass SQLite's check; then the absolute paths that pointed into
    the old folder (the runs' terminal logs) point into the new one."""
    connection = sqlite3.connect(database)
    try:
        (result,) = connection.execute("PRAGMA quick_check").fetchone()
        if result != "ok":
            raise RuntimeError(f"the copied database is damaged: {result}")
        prefix = os.path.normcase(os.path.abspath(source))
        rows = connection.execute("SELECT id, log_path FROM runs WHERE log_path != ''").fetchall()
        for run_id, log_path in rows:
            key = os.path.normcase(os.path.abspath(log_path))
            if key.startswith(prefix + os.sep):
                moved = str(target) + os.path.abspath(log_path)[len(prefix) :]
                connection.execute("UPDATE runs SET log_path = ? WHERE id = ?", (moved, run_id))
        connection.commit()
    finally:
        connection.close()


def _remove_old(source: Path, home: Path) -> None:
    """Deletes the old copy; the home folder keeps its pointer. A file still locked (an
    antivirus scan) is retried briefly and otherwise left behind."""
    for attempt in range(3):
        leftovers = []
        for entry in list(source.iterdir()) if source.exists() else []:
            if same(source, home) and entry.name in HOME_ONLY:
                continue
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except OSError:
                leftovers.append(entry)
        if not leftovers:
            break
        time.sleep(0.5 * (attempt + 1))
    if not same(source, home):
        with contextlib.suppress(OSError):
            source.rmdir()
