"""P8: compare usage read from transcripts with what each CLI reports in its JSON result.

Usage: uv run python scenarios/usage.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import clean_env  # noqa: E402
from recorder import Recorder  # noqa: E402
from usage_probe import agy_transcript, agy_usage, claude_transcript, claude_usage  # noqa: E402

PROMPT = "Escribe un haiku sobre agentes que trabajan en equipo."
SUBAGENT_PROMPT = (
    "Lanza un subagente que cuente los archivos de esta carpeta y responde con el número."
)


def run_json(argv: list[str], cwd: Path) -> dict:
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return json.loads(proc.stdout)


def compare_claude(rec: Recorder, label: str, prompt: str, extra: list[str]) -> None:
    cwd = sandbox(f"claude-usage-{label}")
    sid = str(uuid.uuid4())
    argv = [
        "claude", "--model", "haiku", "--setting-sources", "project,local",
        "--strict-mcp-config", "--output-format", "json", "--session-id", sid, *extra,
        "-p", prompt,
    ]  # fmt: skip
    result = run_json(argv, cwd)
    parsed = claude_usage(claude_transcript(cwd, sid))
    reported = result.get("usage") or {}
    reported_models = result.get("modelUsage") or {}
    same_cost = (
        parsed.cost_usd is not None and abs(parsed.cost_usd - result["total_cost_usd"]) < 1e-9
    )
    model_totals = {
        "input": sum(m.get("inputTokens", 0) for m in reported_models.values()),
        "output": sum(m.get("outputTokens", 0) for m in reported_models.values()),
    }
    same_tokens = (parsed.input_tokens, parsed.output_tokens) == (
        model_totals["input"],
        model_totals["output"],
    )
    rec.step(f"Claude ({label}): transcript vs resultado", same_cost and same_tokens, screen=False)
    rec.note(
        "| | Transcript (`cost-state`) | Resultado JSON |\n|---|---|---|\n"
        f"| Coste USD | {parsed.cost_usd} | {result.get('total_cost_usd')} |\n"
        f"| Tokens entrada | {parsed.input_tokens} | {model_totals['input']} |\n"
        f"| Tokens salida | {parsed.output_tokens} | {model_totals['output']} |\n"
        f"| Caché lectura / creación | {parsed.cache_read_tokens} / {parsed.cache_creation_tokens}"
        f" | `usage` del último turno: {reported.get('cache_read_input_tokens')} / "
        f"{reported.get('cache_creation_input_tokens')} |\n"
        f"| Modelos | {list(parsed.models)} | {list(reported_models)} |\n"
    )


def compare_agy(rec: Recorder) -> None:
    cwd = sandbox("agy-usage")
    argv = ["agy", "--model", "gemini-3.8-flash-low", "--output-format", "json", "-p", PROMPT]
    result = run_json(argv, cwd)
    parsed = agy_usage(agy_transcript(result["conversation_id"]))
    reported = result.get("usage") or {}
    same = (parsed.input_tokens, parsed.output_tokens, parsed.cache_read_tokens) == (
        reported.get("input_tokens"),
        reported.get("output_tokens"),
        reported.get("cache_read_tokens"),
    )
    rec.step("agy: transcript vs resultado", same, screen=False)
    rec.note(
        "| | transcript_full.jsonl | Resultado JSON |\n|---|---|---|\n"
        f"| Tokens entrada | {parsed.input_tokens} | {reported.get('input_tokens')} |\n"
        f"| Tokens salida | {parsed.output_tokens} | {reported.get('output_tokens')} |\n"
        f"| Caché lectura | {parsed.cache_read_tokens} | {reported.get('cache_read_tokens')} |\n"
        f"| Razonamiento | {parsed.thinking_tokens} | {reported.get('thinking_tokens')} |\n"
        "| Coste | — (no registrado) | — |\n"
    )


def interactive_claude(rec: Recorder) -> None:
    """The PTY sessions from P1/P5 have no JSON result: show that the transcript still works."""
    root = Path.home() / ".claude" / "projects"
    files = sorted(root.glob("*claude-mcp-pty-*/*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        rec.note("No hay transcripts de sesiones interactivas para comparar.")
        return
    parsed = claude_usage(files[-1])
    rec.step("Claude (sesión interactiva PTY de P5): consumo desde el transcript",
             parsed.cost_usd is not None, screen=False)  # fmt: skip
    rec.note(f"`{files[-1].name}` → {json.dumps(parsed.as_dict(), ensure_ascii=False)[:500]}")


def main() -> None:
    rec = Recorder("Consumo por sesión (P8)", evidence("p8-usage.md"))
    try:
        with config_guard("usage") as changes:
            compare_claude(rec, "simple", PROMPT, [])
            compare_claude(
                rec, "subagente", SUBAGENT_PROMPT, ["--permission-mode", "bypassPermissions"]
            )
            compare_agy(rec)
            interactive_claude(rec)
        rec.note(f"Configuración global: {changes or 'SIN CAMBIOS'}")
    finally:
        rec.save()


if __name__ == "__main__":
    main()
