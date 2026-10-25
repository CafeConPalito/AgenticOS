"""Phase 19 · spike S4: size of the Architect's tool answers in a large installation.

With 200 skills, 300 documents and 50 connections: how many characters (and ~tokens) does
each list/search answer take? Is listing whole catalogs affordable, or must the tools search
and page? No LLM involved.

Usage: uv run python architect/s4_sizes.py   (from spikes/)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_install import installation  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "19-meta-agentes" / "evidencias"
CHARS_PER_TOKEN = 3.5  # Spanish JSON, measured roughly on the phase 14 corpus


def size(value: object) -> dict:
    text = json.dumps(value, ensure_ascii=False)
    return {"chars": len(text), "tokens": round(len(text) / CHARS_PER_TOKEN)}


def main() -> None:
    small, big = installation(0), installation(1)
    answers = {}
    for label, inst in (("small", small), ("large", big)):
        answers[label] = {
            "counts": {k: len(inst[k]) for k in ("skills", "docs", "connections", "agents")},
            "list_all_skills": size(inst["skills"]),
            "list_all_docs": size(inst["docs"]),
            "list_all_connections": size(inst["connections"]),
            "list_connections_without_tools": size(
                [{k: c[k] for k in ("name", "description")} for c in inst["connections"]]
            ),
            "search_top8_skills": size(inst["skills"][:8]),
            "search_top8_docs": size(inst["docs"][:8]),
            "list_clis": size({"clis": inst["clis"], "tools": inst["tools"]}),
            "list_projects": size(inst["projects"]),
        }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s4-sizes-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(answers, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(answers, indent=1))
    print("evidence:", out)


if __name__ == "__main__":
    main()
