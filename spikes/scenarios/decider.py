"""Phase 13 S1/S2: a headless call that picks the branches of a pipeline fork.

Runs 5 example tasks through `claude -p` (S1) and `agy -p` (S2) and writes the evidence to
docs/phases/13-pipelines-ramas/evidencias/. Never touches the CLIs' global configuration
(config_guard reports it).

Usage: uv run python scenarios/decider.py [claude|agy]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import REPO, config_guard, run_cli, sandbox  # noqa: E402

OUT = REPO / "docs" / "phases" / "13-pipelines-ramas" / "evidencias"

BRANCHES = [
    {
        "id": "b1",
        "name": "Backend",
        "condition": "La tarea toca la API, la base de datos o el backend",
    },
    {
        "id": "f1",
        "name": "Frontend",
        "condition": "La tarea toca la interfaz de usuario o el frontend",
    },
]

TASKS = [
    (
        "Añadir el endpoint GET /clientes",
        "Devuelve la lista paginada de clientes desde la base de datos.",
        {"b1"},
    ),
    (
        "Botón de modo oscuro",
        "Añade un interruptor en la barra superior que cambia el tema.",
        {"f1"},
    ),
    (
        "Filtro de pedidos por fecha",
        "Nuevo parámetro `desde` en la API de pedidos y un selector de fechas "
        "en la pantalla de pedidos.",
        {"b1", "f1"},
    ),
    (
        "Corregir una errata en el README",
        "Cambia 'instalacion' por 'instalación' en la documentación.",
        set(),
    ),
    (
        "Migrar la tabla usuarios",
        "Añade la columna `telefono` y muéstrala en la ficha del usuario.",
        {"b1", "f1"},
    ),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "branches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "take": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "take", "reason"],
            },
        }
    },
    "required": ["branches"],
}


def prompt(title: str, description: str) -> str:
    branches = "\n".join(f"- {b['id']} · {b['name']}: {b['condition']}" for b in BRANCHES)
    return (
        "Eres el enrutador de un pipeline de desarrollo. Decide por qué ramas debe pasar la "
        "tarea. Puedes elegir una, varias o todas según las condiciones; explica cada decisión "
        "en una frase.\n\n"
        f"Tarea: {title}\n{description}\n\nRamas:\n{branches}\n\n"
        'Responde solo con JSON: {"branches": [{"id": "...", "take": true|false, '
        '"reason": "..."}]} '
        "con todas las ramas."
    )


def claude_argv(text: str) -> list[str]:
    return [
        "claude", "-p", text, "--model", "haiku", "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA), "--tools", "", "--strict-mcp-config",
        "--no-session-persistence", "--max-budget-usd", "0.05",
    ]  # fmt: skip


def agy_argv(text: str) -> list[str]:
    return ["agy", "-p", text, "--model", "gemini-3.8-flash-low", "--output-format", "json"]


def extract(cli: str, result) -> tuple[dict | None, dict]:
    """(decision, facts) from the CLI's output."""
    facts: dict = {"rc": result.returncode}
    data = result.json or {}
    if cli == "claude":
        facts["cost_usd"] = data.get("total_cost_usd")
        facts["usage"] = {
            k: (data.get("usage") or {}).get(k) for k in ("input_tokens", "output_tokens")
        }
        facts["is_error"] = data.get("is_error")
        structured = data.get("structured_output")
        facts["has_structured_output"] = structured is not None
        if isinstance(structured, dict):
            return structured, facts
        text = data.get("result") or ""
    else:
        inner = data.get("result", data)
        facts["status"] = inner.get("status")
        facts["usage"] = inner.get("usage")
        facts["denied"] = inner.get("denied_actions")
        text = inner.get("response") or ""
    facts["text_len"] = len(text)
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        return json.loads(text[start:end]), facts
    except ValueError:
        return None, facts


def main() -> None:
    wanted = sys.argv[1:] or ["claude", "agy"]
    OUT.mkdir(parents=True, exist_ok=True)
    for cli in wanted:
        build = claude_argv if cli == "claude" else agy_argv
        lines = [f"# Decisor headless con {cli} ({'S1' if cli == 'claude' else 'S2'})\n"]
        cwd = sandbox(f"decider-{cli}")
        correct = 0
        with config_guard(f"decider-{cli}") as changes:
            for title, description, expected in TASKS:
                started = time.monotonic()
                result = run_cli(build(prompt(title, description)), cwd, timeout=120)
                elapsed = time.monotonic() - started
                decision, facts = extract(cli, result)
                chosen = (
                    {b["id"] for b in decision["branches"] if b.get("take")} if decision else None
                )
                ok = chosen == expected
                correct += ok
                lines += [
                    f"## {title}",
                    f"- esperado: {sorted(expected) or 'ninguna'} · elegido: "
                    f"{sorted(chosen) if chosen is not None else 'SIN DECISIÓN VÁLIDA'} · "
                    f"{'OK' if ok else 'DISTINTO'} · {elapsed:.1f}s",
                    f"- hechos: `{json.dumps(facts, ensure_ascii=False)}`",
                    f"- decisión: `{json.dumps(decision, ensure_ascii=False)[:500]}`",
                    f"- stderr: `{result.stderr[:200]}`" if result.stderr else "",
                    "",
                ]
                print(lines[-5], lines[-4])
        files = list(cwd.iterdir())
        lines += [
            f"**Aciertos**: {correct}/{len(TASKS)}",
            f"**Ficheros en la carpeta tras las llamadas**: {[f.name for f in files]}",
            f"**Configuración global**: {changes or 'SIN CAMBIOS'}",
        ]
        target = OUT / ("s1-claude-decider.md" if cli == "claude" else "s2-agy-decider.md")
        target.write_text("\n".join(lines), "utf-8")
        print(f"evidence: {target}")


if __name__ == "__main__":
    main()
