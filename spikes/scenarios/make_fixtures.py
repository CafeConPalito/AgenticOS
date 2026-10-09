"""Builds anonymized test fixtures from real transcripts (only usage-related fields are kept).

Usage: uv run python scenarios/make_fixtures.py <claude-transcript.jsonl> <agy-transcript.jsonl>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> None:
    claude_src, agy_src = Path(sys.argv[1]), Path(sys.argv[2])
    FIXTURES.mkdir(parents=True, exist_ok=True)

    claude_rows = []
    for line in claude_src.read_text("utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "cost-state":
            keep = ("type", "totalCostUSD", "modelUsage")
            claude_rows.append({k: row[k] for k in keep if k in row})
        elif row.get("type") == "assistant" and (row.get("message") or {}).get("usage"):
            message = row["message"]
            claude_rows.append(
                {
                    "type": "assistant",
                    "message": {k: message.get(k) for k in ("id", "model", "usage")},
                }
            )
        elif row.get("type") == "user":
            claude_rows.append({"type": "user", "message": {"content": "<redacted>"}})
    (FIXTURES / "claude_transcript.jsonl").write_text(
        "\n".join(json.dumps(r) for r in claude_rows) + "\n", "utf-8"
    )

    agy_rows = []
    for line in agy_src.read_text("utf-8").splitlines():
        row = json.loads(line)
        keep = ("type", "status", "input_tokens", "output_tokens", "cache_read_tokens")
        agy_rows.append({k: row[k] for k in keep if k in row})
    (FIXTURES / "agy_transcript_full.jsonl").write_text(
        "\n".join(json.dumps(r) for r in agy_rows) + "\n", "utf-8"
    )
    print(f"claude rows: {len(claude_rows)} · agy rows: {len(agy_rows)}")


if __name__ == "__main__":
    main()
