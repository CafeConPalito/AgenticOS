"""Prepares the models that go inside the installer (run by scripts/build-backend.ps1).

    python -m agentic_os.services.localmodels.stage <folder>

Downloads every catalog entry flagged `bundled` into `<folder>/models/<id>/`, checked against the
pinned SHA-256, with the same code the app uses to download. PyInstaller then adds
`<folder>/models` to the executable as `bundled_models`, where `store.bundled_folder` finds it.
Running it again does nothing for what is already there. Exit code 1 if anything failed, so a
build never ships without them.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.localmodels import catalog
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.downloads import READY, DownloadManager

TIMEOUT = 30 * 60.0


def stage(root: Path, entries: Iterable[CatalogEntry] | None = None, log=print) -> bool:
    chosen = list(entries) if entries is not None else [e for e in catalog.CATALOG if e.bundled]
    manager = DownloadManager(Path(root), KnowledgeEvents())
    ok = True
    for entry in chosen:
        if manager.state(entry).state != READY:
            log(f"downloading {entry.id} ({entry.size / 1e6:.1f} MB)…")
            manager.start(entry)
            manager.join(entry, timeout=TIMEOUT)
        state = manager.state(entry)
        if state.state == READY:
            log(f"{entry.id}: ready")
        else:
            ok = False
            log(f"{entry.id}: FAILED ({state.state} {state.error_code} {state.error_message})")
    manager.stop()
    return ok


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m agentic_os.services.localmodels.stage <folder>", file=sys.stderr)
        return 2
    return 0 if stage(Path(argv[0])) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
