"""Where the downloaded models live and whether one is complete.

`<data>/models/<id>/…` for models and `<data>/engines/<id>/…` for engines. A model is ready when
its `manifest.json` (written last, when every file has been checked) exists and every file is
there with the size the catalog says. A download in progress leaves `<file>.part` files, which
the next attempt continues from.

A model flagged `bundled` also counts as installed when the packaged app carries it: the build
puts its files under `bundled_models/<id>/` inside the executable (PyInstaller's data folder), or
in the folder named by AGENTIC_OS_BUNDLED_MODELS (tests, development). Those files are read in
place and cannot be removed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from agentic_os.db.base import utcnow
from agentic_os.services.localmodels.catalog import CatalogEntry

MANIFEST = "manifest.json"
PART = ".part"


def bundled_root() -> Path | None:
    """The folder with the models that came inside the app, if this is a build that has them."""
    override = os.environ.get("AGENTIC_OS_BUNDLED_MODELS")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", "")) / "bundled_models"
        return root if root.is_dir() else None
    return None


def bundled_folder(entry: CatalogEntry) -> Path | None:
    """Where the app carries this model, when it does and the files are all there."""
    root = bundled_root()
    if not entry.bundled or root is None:
        return None
    folder = root / entry.id
    complete = all(
        (folder / f.name).is_file() and (folder / f.name).stat().st_size == f.size
        for f in entry.files
    )
    return folder if complete else None


def folder_of(data_dir: Path, entry: CatalogEntry) -> Path:
    """Where to read the entry's files: the bundled copy if there is one, else the data folder."""
    return bundled_folder(entry) or downloaded_folder(data_dir, entry)


def downloaded_folder(data_dir: Path, entry: CatalogEntry) -> Path:
    """Where its downloads go (never the bundled folder)."""
    return Path(data_dir) / entry.folder / entry.id


def file_path(data_dir: Path, entry: CatalogEntry, name: str) -> Path:
    return folder_of(data_dir, entry) / name


def executable(data_dir: Path, entry: CatalogEntry) -> Path | None:
    """The program of an engine, once unpacked."""
    relative = entry.usage.get("executable")
    return folder_of(data_dir, entry) / relative if relative else None


def is_bundled(entry: CatalogEntry) -> bool:
    return bundled_folder(entry) is not None


def is_installed(data_dir: Path, entry: CatalogEntry) -> bool:
    if is_bundled(entry):
        return True
    folder = downloaded_folder(data_dir, entry)
    if not (folder / MANIFEST).is_file():
        return False
    if entry.unpack:  # an engine: the archive is gone, its program is what matters
        program = executable(data_dir, entry)
        return program is not None and program.is_file()
    return all(
        (folder / f.name).is_file() and (folder / f.name).stat().st_size == f.size
        for f in entry.files
    )


def partial_bytes(data_dir: Path, entry: CatalogEntry) -> int:
    """What an interrupted download already has (complete files and `.part` pieces)."""
    folder = downloaded_folder(data_dir, entry)
    total = 0
    for f in entry.files:
        for path in (folder / f.name, folder / (f.name + PART)):
            if path.is_file():
                total += min(path.stat().st_size, f.size)
                break
    return total


def write_manifest(data_dir: Path, entry: CatalogEntry) -> None:
    manifest = {
        "id": entry.id,
        "kind": entry.kind,
        "installed_at": utcnow().isoformat(),
        "files": [{"name": f.name, "size": f.size, "sha256": f.sha256} for f in entry.files],
    }
    folder = downloaded_folder(data_dir, entry)
    temporary = folder / (MANIFEST + PART)
    temporary.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    temporary.replace(folder / MANIFEST)


def remove(data_dir: Path, entry: CatalogEntry) -> None:
    """Deletes what was downloaded. The bundled copy is part of the app: it stays."""
    shutil.rmtree(downloaded_folder(data_dir, entry), ignore_errors=True)


def tree_size(path: Path) -> int:
    total = 0
    if path.is_dir():
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    return total


def used_bytes(data_dir: Path) -> dict[str, int]:
    """Disk used by the downloaded models and engines (for Settings)."""
    return {
        "models": tree_size(Path(data_dir) / "models"),
        "engines": tree_size(Path(data_dir) / "engines"),
    }
