"""Hook command for the spikes: appends the event payload (stdin JSON) to a JSONL file.

Usage (from a CLI hook): python hook_logger.py <cli> <event> <log.jsonl>
Always exits 0 so it never blocks the agent.
"""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    cli, event, log_path = sys.argv[1], sys.argv[2], sys.argv[3]
    # The CLIs send UTF-8; the console code page would garble accents.
    raw = sys.stdin.buffer.read().decode("utf-8", "replace") if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        payload = {"_raw": raw[:2000]}
    entry = {"at": time.strftime("%H:%M:%S"), "cli": cli, "event": event, "payload": payload}
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
