"""Exploratory helper: launch a CLI in a PTY, print the screen every few seconds.

Usage: uv run python scenarios/explore.py <name> <seconds> -- <argv...>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import PtyRun  # noqa: E402


def main() -> None:
    name, seconds = sys.argv[1], float(sys.argv[2])
    argv = sys.argv[sys.argv.index("--") + 1 :]
    cwd = sandbox(name)
    with config_guard(name):
        run = PtyRun(argv, cwd, evidence(f"{name}.raw.log"))
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end and run.alive():
                time.sleep(min(5, max(0.1, end - time.monotonic())))
                print(f"===== t={run.elapsed():.1f}s alive={run.alive()} =====")
                print(run.snapshot())
        finally:
            run.close()


if __name__ == "__main__":
    main()
