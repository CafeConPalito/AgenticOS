"""Short-lived helper processes (git, the CLIs' --version, tasklist…) and opening folders.

The packaged backend runs without a console (phase 08). On Windows, every console program it
starts would then open a window of its own unless it is created with CREATE_NO_WINDOW.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run(
    argv: Sequence[str],
    timeout: float,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Runs a command to completion, capturing its output as text, with no window. Its stdin is
    empty unless `input` gives it text."""
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        input=input,
        stdin=None if input is not None else subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )


def open_in_file_manager(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_file_manager(path: str) -> None:
    """Opens the file manager with the file selected (its folder, where that is not possible)."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
