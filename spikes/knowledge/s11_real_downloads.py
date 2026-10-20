"""Phase 14 block 3: downloads the small catalog entries from their real sources (modelscope.cn,
GitHub, Hugging Face), with a cancel and resume in the middle of the biggest, and checks them.

Run from the backend environment:  cd backend && uv run python ../spikes/knowledge/s11_real_downloads.py
"""

import sys
import tempfile
import time
from pathlib import Path

from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.localmodels import catalog, store
from agentic_os.services.localmodels.downloads import DownloadManager

sys.stdout.reconfigure(encoding="utf-8")
data = Path(tempfile.mkdtemp(prefix="agentic-models-"))
events = KnowledgeEvents()
manager = DownloadManager(data, events)
print("data dir:", data)


def wait(entry, label):
    t = time.perf_counter()
    manager.join(entry, timeout=900)
    state = manager.state(entry)
    print(
        f"{label}: {entry.id} -> {state.state} {state.done}/{state.total} "
        f"{state.error_code or ''} {state.error_message or ''} in {time.perf_counter() - t:.1f}s"
    )
    return state


for name in ("ocr-latin", "llama-cpp"):
    entry = catalog.entry(name)
    manager.start(entry)
    assert wait(entry, "download").state == "ready", name
    assert store.is_installed(data, entry)

program = store.executable(data, catalog.entry("llama-cpp"))
print("llama-server:", program, program.is_file())

# Resume on the biggest of the small ones: cancel after ~25 %, then continue.
entry = catalog.entry("e5-small")
manager.start(entry)
deadline = time.monotonic() + 120
while manager.state(entry).done < entry.size * 0.25 and time.monotonic() < deadline:
    time.sleep(0.2)
manager.cancel(entry)
state = wait(entry, "cancelled")
print("partial on disk:", store.partial_bytes(data, entry), "of", entry.size)
manager.start(entry)
final = wait(entry, "resumed")
assert final.state == "ready"
print(
    "installed:",
    {
        e.id: store.is_installed(data, e)
        for e in catalog.CATALOG
        if e.id in ("ocr-latin", "llama-cpp", "e5-small")
    },
)
print("disk:", store.used_bytes(data))
