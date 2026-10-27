"""Hook command for agy in spike S2: logs every event and, on PreToolUse, denies any tool that is
not an MCP call to the Architect's server.

Usage (from hooks.json): <python> agy_guard.py <event> <log.jsonl>
Always exits 0.
"""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    event, log_path = sys.argv[1], sys.argv[2]
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw[:2000]}
    answer: dict = {}
    if event == "PreToolUse":
        call = payload.get("toolCall") or {}
        server = str((call.get("args") or {}).get("ServerName", ""))
        if call.get("name") == "call_mcp_tool" and server.endswith("architect"):
            answer = {"decision": "allow"}
        else:
            answer = {
                "decision": "deny",
                "reason": "El Arquitecto solo puede usar las herramientas de su servidor MCP.",
            }
    entry = {"t": time.time(), "event": event, "payload": payload, "answer": answer}
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    sys.stdout.write(json.dumps(answer))


if __name__ == "__main__":
    main()
