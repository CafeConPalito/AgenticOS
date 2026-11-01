"""Where the agent CLIs are (phase 23, ADR 0029).

A CLI installed while the app runs lands in a folder the backend's `PATH` does not have yet: the
installers add it to the user's `PATH` in the registry, which only new processes read. So, after
the process's own `PATH`, the user's and the machine's are read from the registry (with their
`%VARIABLES%` expanded), and then the folders the official installers use.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

# Where the official installers put each CLI on Windows (read on 2026-10-31).
KNOWN_DIRS = (
    Path("~") / ".local" / "bin",  # Claude Code: `claude install`
    Path("%LOCALAPPDATA%") / "agy" / "bin",  # Antigravity CLI: install.ps1
)


def _registry_paths() -> list[str]:  # pragma: no cover - Windows registry
    """The user's and the machine's `PATH`, as stored now (not as this process started)."""
    if sys.platform != "win32":
        return []
    import winreg

    keys = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    folders: list[str] = []
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        folders += [part for part in str(value).split(os.pathsep) if part.strip()]
    return folders


# Swapped in tests.
registry_paths: Callable[[], list[str]] = _registry_paths


def search_path() -> str:
    """The folders to look in after the process's `PATH`, expanded, each once."""
    seen: dict[str, None] = {}
    for folder in [*registry_paths(), *(str(d) for d in KNOWN_DIRS)]:
        expanded = os.path.expanduser(os.path.expandvars(folder.strip()))
        seen.setdefault(os.path.normcase(expanded), None)
    return os.pathsep.join(seen)


def which(name: str) -> str | None:
    """`shutil.which`, then the user's `PATH` and the installers' folders."""
    found = shutil.which(name)
    if found:
        return found
    extra = search_path()
    return shutil.which(name, path=extra) if extra else None
