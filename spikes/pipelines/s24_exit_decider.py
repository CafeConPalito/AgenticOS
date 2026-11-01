"""Phase 24, spike S1: can the branch decider (cheapest model) tell whether a task ends at a
stage with an exit, and pick the branches at the same time when the stage also forks?

Twelve sample tasks: six at «Validación de requisitos» (no fork) and six at «Arquitectura»
(exit + fork Frontend/Backend/Datos). Half of them should end there. Real `claude -p` calls
with the decider's flags; prints the hits, the cost and the time.

    uv run python pipelines/s24_exit_decider.py [--model haiku]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

EXIT_REQ = "La tarea solo pide definir o revisar requisitos"
EXIT_ARCH = "La tarea solo pide definir o revisar la arquitectura"
BRANCHES = {
    "fe": ("Frontend", "La tarea toca la interfaz de usuario o el frontend"),
    "be": ("Backend", "La tarea toca la API, la base de datos o el backend"),
    "data": ("Datos", "La tarea pide análisis de datos, modelos, métricas o informes"),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "exit": {
            "type": "object",
            "properties": {"take": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["take", "reason"],
        },
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
        },
    },
    "required": ["exit", "branches"],
}


@dataclass
class Case:
    stage: str
    exit: str
    title: str
    description: str
    history: list[str]
    ends: bool
    branches: set[str] = field(default_factory=set)  # expected when it goes on (fork only)
    fork: bool = False


REQ_DONE = "- Toma de requisitos · Analista terminó: requisitos y criterios de aceptación escritos."
VAL_DONE = "- Validación de requisitos · Validador terminó: requisitos completos y coherentes."

CASES = [
    # ---- Validación de requisitos (no fork)
    Case("Validación de requisitos", EXIT_REQ, "Definir los requisitos del módulo de facturación",
         "Necesito que se escriban los requisitos del futuro módulo de facturación para "
         "presentarlos a dirección. De momento no hay que programar nada.", [REQ_DONE], True),
    Case("Validación de requisitos", EXIT_REQ, "Revisar los criterios de aceptación del login",
         "Repasa los criterios de aceptación del inicio de sesión que escribimos el mes pasado "
         "y corrige los que no se puedan probar.", [REQ_DONE], True),
    Case("Validación de requisitos", EXIT_REQ, "Historias de usuario para la app móvil",
         "Escribe las historias de usuario de la primera versión de la app móvil; el desarrollo "
         "lo haremos el trimestre que viene.", [REQ_DONE], True),
    Case("Validación de requisitos", EXIT_REQ, "Añadir exportación a PDF de las facturas",
         "Los clientes quieren descargar sus facturas en PDF desde su área privada.",
         [REQ_DONE], False),
    Case("Validación de requisitos", EXIT_REQ, "Corregir el cálculo del IVA en el carrito",
         "El carrito suma mal el IVA cuando hay productos con tipos distintos.",
         [REQ_DONE], False),
    Case("Validación de requisitos", EXIT_REQ, "Requisitos y desarrollo del buscador",
         "Define los requisitos del buscador de productos e impleméntalo con filtros por "
         "precio y categoría.", [REQ_DONE], False),
    # ---- Arquitectura (exit + fork)
    Case("Arquitectura", EXIT_ARCH, "Proponer la arquitectura del nuevo SaaS",
         "Queremos saber qué stack y qué servicios de Azure usaríamos para el nuevo SaaS de "
         "reservas. Solo el documento de arquitectura, sin código.", [REQ_DONE, VAL_DONE], True,
         fork=True),
    Case("Arquitectura", EXIT_ARCH, "Revisar si migramos de AWS a Google Cloud",
         "Evalúa la arquitectura actual y propone cómo sería en Google Cloud, con costes "
         "aproximados. Es un estudio, no una migración.", [REQ_DONE, VAL_DONE], True, fork=True),
    Case("Arquitectura", EXIT_ARCH, "Pantalla de perfil de usuario",
         "Añadir una pantalla donde el usuario pueda cambiar su foto y su nombre; el endpoint "
         "ya existe.", [REQ_DONE, VAL_DONE], False, {"fe"}, fork=True),
    Case("Arquitectura", EXIT_ARCH, "API de pedidos con su panel",
         "Crear el endpoint de pedidos con su tabla en la base de datos y la página del panel "
         "que los lista.", [REQ_DONE, VAL_DONE], False, {"fe", "be"}, fork=True),
    Case("Arquitectura", EXIT_ARCH, "Informe de abandono de clientes",
         "Analiza los datos de bajas del último año y entrena un modelo que prediga qué "
         "clientes se van a ir, con un informe.", [REQ_DONE, VAL_DONE], False, {"data"},
         fork=True),
    Case("Arquitectura", EXIT_ARCH, "Documentar la arquitectura y crear el esqueleto",
         "Define la arquitectura del proyecto y crea el esqueleto del backend en FastAPI con "
         "su base de datos.", [REQ_DONE, VAL_DONE], False, {"be"}, fork=True),
]  # fmt: skip


def prompt(case: Case) -> str:
    history = "\n".join(case.history)
    head = (
        f"Eres el enrutador de un pipeline de desarrollo. La etapa «{case.stage}» acaba de "
        "terminar.\n\n"
        "1. Decide primero si la tarea **termina aquí**: termina solo si se cumple esta "
        f"condición: «{case.exit}». Si la tarea pide además cualquier trabajo posterior "
        "(programar, desplegar…), no termina.\n"
    )
    if case.fork:
        branches = "\n".join(f"- {k} · {n}: {c}" for k, (n, c) in BRANCHES.items())
        head += (
            "2. Si no termina, decide por qué ramas debe pasar según sus condiciones: una, "
            "varias o todas, pero al menos una. Si termina, no tomes ninguna rama.\n\n"
            f"Ramas:\n{branches}\n\n"
        )
    else:
        head += "2. Esta etapa no tiene ramas: devuelve `branches` vacío.\n\n"
    return (
        head
        + f"Tarea: {case.title}\n{case.description}\n\nTrabajo ya hecho:\n{history}\n\n"
        + 'Explica cada decisión en una frase. Responde solo con JSON: {"exit": {"take": '
        'true|false, "reason": "..."}, "branches": [{"id": "...", "take": true|false, '
        '"reason": "..."}]}.'
    )


def run(case: Case, model: str) -> dict:
    argv = [
        "claude", "-p", prompt(case), "--model", model, "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA), "--tools", "", "--strict-mcp-config",
        "--no-session-persistence", "--max-budget-usd", "0.05",
    ]  # fmt: skip
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="s24-") as folder:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", cwd=folder, timeout=120
        )
    seconds = time.monotonic() - started
    data = json.loads(proc.stdout[proc.stdout.index("{") :])
    answer = data.get("structured_output") or {}
    ends = bool((answer.get("exit") or {}).get("take"))
    taken = {b["id"] for b in answer.get("branches") or [] if b.get("take")}
    ok = ends == case.ends and (ends or not case.fork or taken == case.branches)
    return {
        "title": case.title,
        "ok": ok,
        "ends": ends,
        "expected_ends": case.ends,
        "taken": sorted(taken),
        "expected": sorted(case.branches),
        "reason": (answer.get("exit") or {}).get("reason", ""),
        "cost": data.get("total_cost_usd") or 0.0,
        "seconds": round(seconds, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="haiku")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: run(c, args.model), CASES))
    for r in results:
        mark = "OK " if r["ok"] else "MAL"
        ends = f"termina={r['ends']!s:5} (esperado {r['expected_ends']!s:5})"
        lanes = f"ramas={r['taken']} (esperado {r['expected']})"
        print(f"{mark} {r['title'][:48]:48} {ends} {lanes} {r['cost']:.4f} $ {r['seconds']} s")
        if not r["ok"]:
            print(f"     motivo: {r['reason']}")
    hits = sum(r["ok"] for r in results)
    cost = sum(r["cost"] for r in results)
    print(f"\n{hits}/{len(results)} aciertos · {cost / len(results):.4f} $ de media por llamada")
    return 0 if hits >= 11 else 1


if __name__ == "__main__":
    sys.exit(main())
