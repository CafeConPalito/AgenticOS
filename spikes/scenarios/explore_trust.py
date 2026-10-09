"""Explores how to answer Claude Code's folder-trust dialog through the PTY."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import evidence, sandbox  # noqa: E402
from pty_run import PtyRun  # noqa: E402

KEYSEQ = sys.argv[1] if len(sys.argv) > 1 else "\x1b[B"


def main() -> None:
    cwd = sandbox("claude-trust")
    run = PtyRun(["claude", "--model", "haiku"], cwd, evidence("explore-trust.raw.log"))
    try:
        run.wait_screen("trust this folder", 30)
        time.sleep(1)
        print("-- before:", [ln for ln in run.snapshot().splitlines() if "❯" in ln])
        run.send(KEYSEQ.encode().decode("unicode_escape"))
        time.sleep(1.5)
        print("-- after key:", [ln for ln in run.snapshot().splitlines() if "❯" in ln])
    finally:
        run.close()


if __name__ == "__main__":
    main()
