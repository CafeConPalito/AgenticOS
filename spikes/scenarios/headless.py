"""P11: headless mode (`-p` + stream-json) for both CLIs. Saves raw events and a summary.

Usage: uv run python scenarios/headless.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, run_cli, sandbox  # noqa: E402

PROMPT = "Crea un archivo hola.txt que contenga la palabra hola y después responde LISTO"


def run_headless(name: str, argv: list[str], cwd: Path) -> list[dict]:
    started = time.monotonic()
    result = run_cli(argv, cwd)
    elapsed = time.monotonic() - started
    evidence(f"p11-{name}.stream.jsonl").write_text(result.stdout, "utf-8")
    print(f"== {name}: rc={result.returncode} {elapsed:.1f}s, {len(result.events)} events")
    if result.stderr:
        print("stderr:", result.stderr[:500])
    return result.events


def summarize(events: list[dict]) -> list[str]:
    lines = []
    for event in events:
        kind = event.get("type", "?")
        sub = event.get("subtype", "")
        keys = sorted(k for k in event if k not in {"type", "subtype"})
        lines.append(f"- `{kind}`{('/' + sub) if sub else ''}: {', '.join(keys)[:180]}")
    return lines


def main() -> None:
    report = ["# Modo headless (P11)\n", f"Prompt: «{PROMPT}»\n"]

    session_id = str(uuid.uuid4())
    cwd = sandbox("claude-headless")
    argv = [
        "claude",
        "-p",
        PROMPT,
        "--model",
        "haiku",
        "--output-format",
        "stream-json",
        "--verbose",
        "--strict-mcp-config",
        "--permission-mode",
        "acceptEdits",
        "--session-id",
        session_id,
        "--max-budget-usd",
        "0.25",
    ]
    with config_guard("claude-headless") as changes:
        events = run_headless("claude", argv, cwd)
    created = (cwd / "hola.txt").exists()
    report += [
        "## Claude Code\n",
        f"`{' '.join(argv)}`\n",
        f"- hola.txt creado: {created}",
        f"- Config global: {changes or 'SIN CAMBIOS'}\n",
        *summarize(events),
        "",
    ]
    result = next((e for e in events if e.get("type") == "result"), {})
    report.append(
        "Resultado: "
        + json.dumps(
            {k: result.get(k) for k in ("session_id", "total_cost_usd", "usage", "num_turns")},
            ensure_ascii=False,
        )[:900]
        + "\n"
    )

    cwd = sandbox("agy-headless")
    argv = [
        "agy",
        "-p",
        PROMPT,
        "--model",
        "gemini-3.8-flash-low",
        "--output-format",
        "stream-json",
    ]
    with config_guard("agy-headless") as changes:
        events = run_headless("agy", argv, cwd)
    created = (cwd / "hola.txt").exists()
    report += [
        "## Antigravity CLI\n",
        f"`{' '.join(argv)}`\n",
        f"- hola.txt creado: {created}",
        f"- Config global: {changes or 'SIN CAMBIOS'}\n",
        *summarize(events),
        "",
    ]
    last = events[-1] if events else {}
    report.append("Último evento: " + json.dumps(last, ensure_ascii=False)[:900] + "\n")

    evidence("p11-headless.md").write_text("\n".join(report), "utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
