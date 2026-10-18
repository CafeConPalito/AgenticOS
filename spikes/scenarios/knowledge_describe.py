"""Phase 14 S7: describe an image with a CLI in headless mode (`claude -p`, `agy -p`).

The image is copied to an empty sandbox folder and the CLI reads it there with its own file
tool. Writes the evidence to docs/phases/14-conocimiento/evidencias/s7-cli-describe.md.
Never touches the CLIs' global configuration (config_guard reports it).

Usage: uv run python scenarios/knowledge_describe.py [claude|agy]
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "knowledge"))

from images_expected import EXPECTED  # noqa: E402

from common import REPO, config_guard, run_cli, sandbox  # noqa: E402

IMAGES = Path(__file__).resolve().parent.parent / "knowledge" / "corpus" / "images"
OUT = REPO / "docs" / "phases" / "14-conocimiento" / "evidencias"
PROMPT = (
    "Lee la imagen `{name}` de esta carpeta con tu herramienta de lectura y descríbela en español "
    "de forma breve y precisa (máximo 4 frases). Incluye todo el texto, los números y los datos "
    "que aparezcan. Responde solo con la descripción."
)


def claude_argv(name: str) -> list[str]:
    return [
        "claude", "-p", PROMPT.format(name=name), "--model", "haiku", "--output-format", "json",
        "--tools", "Read", "--allowedTools", "Read", "--strict-mcp-config",
        "--no-session-persistence", "--max-budget-usd", "0.10",
    ]  # fmt: skip


def agy_argv(name: str) -> list[str]:
    return [
        "agy", "-p", PROMPT.format(name=name), "--model", "gemini-3.8-flash-low",
        "--output-format", "json",
    ]  # fmt: skip


def text_of(cli: str, data: dict | None) -> tuple[str, str]:
    """(description, cost/usage summary) from the CLI's JSON."""
    if not data:
        return "", "sin JSON"
    if cli == "claude":
        usage = data.get("usage", {})
        return data.get("result", ""), (
            f"coste={data.get('total_cost_usd')} USD, in={usage.get('input_tokens')}, "
            f"out={usage.get('output_tokens')}, subtype={data.get('subtype')}"
        )
    result = data.get("result", data)
    usage = result.get("usage") if isinstance(result, dict) else None
    response = result.get("response", "") if isinstance(result, dict) else str(result)
    return response, f"usage={json.dumps(usage)[:160]}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    wanted = sys.argv[1:] or ["claude", "agy"]
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# S7 · Describir imágenes con un CLI en modo headless\n"]
    for cli in wanted:
        build = claude_argv if cli == "claude" else agy_argv
        lines.append(f"\n## {cli}\n")
        total_hits = total_kw = 0
        times: list[float] = []
        with config_guard(cli) as changes:
            for image, keywords in EXPECTED.items():
                folder = sandbox(f"describe-{cli}")
                name = "imagen.png"
                shutil.copy(IMAGES / image, folder / name)
                started = time.monotonic()
                try:
                    result = run_cli(build(name), folder, timeout=180)
                    description, usage = text_of(cli, result.json)
                    error = "" if result.ok else f"rc={result.returncode} {result.stderr[:200]}"
                except Exception as exc:  # noqa: BLE001
                    description, usage, error = "", "", repr(exc)
                seconds = time.monotonic() - started
                times.append(seconds)
                hits = [k for k in keywords if k in description.lower()]
                total_hits += len(hits)
                total_kw += len(keywords)
                failure = f"· ERROR {error}" if error else ""
                lines.append(
                    f"- **{image}**: {seconds:.1f} s · aciertos {len(hits)}/{len(keywords)} · "
                    f"{usage} {failure}\n  > {description.strip()[:500]}"
                )
                print(lines[-1], flush=True)
        mean = sum(times) / len(times)
        config = "sin cambios" if not changes else "CAMBIADA: " + "; ".join(changes)
        lines.append(
            f"\n**{cli}**: {mean:.1f} s por imagen de media · "
            f"palabras clave {total_hits}/{total_kw} · configuración global {config}"
        )
        print(lines[-1])
    (OUT / "s7-cli-describe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
