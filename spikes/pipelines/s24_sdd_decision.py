"""Phase 24, spike S2: does the requirements analyst decide well whether a task goes with SDD?

Three sample repositories (spec-kit, specs per phase like this repo, none) and ten requests.
Rule under test: a trivially small change goes without SDD; otherwise SDD when the project
already uses it (in its own format) or when the work is large (the app's `specs/NNN-name/`);
anything else goes without SDD. Real `claude -p` calls with read-only tools in each repo.

    uv run python pipelines/s24_sdd_decision.py [--model sonnet]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

GUIDE = """## Decide si la tarea va con SDD (desarrollo guiado por especificaciones)
Antes de escribir los requisitos, decide el modo de trabajo, en este orden:
1. **Cambio trivial → sin SDD**, aunque el proyecto use SDD: una errata, renombrar algo, un
   ajuste de estilo, un cambio de una línea o de un solo fichero sin decisiones.
2. **El proyecto ya usa SDD → con SDD, en su formato**: sigue sus carpetas, su numeración y sus
   ficheros (mira las specs que ya hay y copia su estructura).
3. **Trabajo grande → con SDD, en el formato de la app** (`specs/NNN-nombre/` con `spec.md`,
   `plan.md` y `tasks.md`; NNN es el siguiente número libre): varias piezas o capas (interfaz,
   API, base de datos), un módulo nuevo, integraciones externas, o decisiones de diseño que hay
   que dejar escritas.
4. **Lo demás → sin SDD**: un cambio acotado de una sola pieza (un endpoint, un campo, una
   pantalla sencilla) en un proyecto sin SDD.
Con SDD, `spec_path` es la carpeta (relativa al proyecto) donde irá la spec de esta tarea.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["sdd", "direct"]},
        "reason": {"type": "string"},
        "spec_path": {"type": "string"},
    },
    "required": ["mode", "reason", "spec_path"],
}

REPOS: dict[str, dict[str, str]] = {
    "speckit": {
        ".specify/memory/constitution.md": "# Constitución\n- Tests primero.\n",
        ".specify/templates/spec-template.md": "# Spec: <nombre>\n",
        "specs/001-login/spec.md": "# Spec: inicio de sesión\n## Historias\n- ...\n",
        "specs/001-login/plan.md": "# Plan\n",
        "specs/001-login/tasks.md": "- [x] T001 formulario\n",
        "src/app.py": "def login(user, password):\n    raise ValueError('Usuaro incorrecto')\n",
        "README.md": "# Tienda\n",
    },
    "phases": {
        "docs/roadmap.md": "| 01 | Login | cerrada |\n| 02 | Catálogo | cerrada |\n",
        "docs/phases/01-login/spec.md": "# Fase 01: Login · Spec\n",
        "docs/phases/01-login/plan.md": "# Fase 01: Login · Plan\n",
        "docs/phases/02-catalogo/spec.md": "# Fase 02: Catálogo · Spec\n",
        "docs/phases/02-catalogo/plan.md": "# Fase 02: Catálogo · Plan\n",
        "src/profile.py": "class Profile:\n    name: str\n    email: str\n    usr_cnt = 0\n",
        "README.md": "# CRM\n",
    },
    "plain": {
        "README.md": "# Agenda\nUna API pequeña de contactos.\nInstalación: pip instal -e .\n",
        "src/api.py": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/users')\n"
        "def users():\n    return []\n",
        "src/ui/button.css": ".primary { background: #336699; }\n",
    },
}

DETECTED = {
    "speckit": "El proyecto usa spec-kit: `.specify/` y specs en `specs/NNN-nombre/`.",
    "phases": "El proyecto usa specs por fase: `docs/phases/NN-nombre/spec.md` y `plan.md`.",
    "plain": "El proyecto no usa SDD.",
}


@dataclass
class Case:
    repo: str
    request: str
    mode: str
    path: str = ""  # regex the spec_path must match when mode is sdd


CASES = [
    Case("plain", "Corrige la errata «pip instal» del README.", "direct"),
    Case("plain", "Cambia el color del botón principal a verde.", "direct"),
    Case("plain", "Añade autenticación con OAuth de Google, roles de usuario y un panel de "
         "administración para gestionarlos.", "sdd", r"^specs/0*1-[a-z0-9-]+/?$"),
    Case("plain", "Añade un endpoint para borrar un usuario por su id.", "direct"),
    Case("speckit", "Corrige la errata «Usuaro» del mensaje de error del login.", "direct"),
    Case("speckit", "Añade recuperación de contraseña por email con enlace que caduca.", "sdd",
         r"^specs/002-[a-z0-9-]+/?$"),
    Case("speckit", "Añade paginación al listado de productos.", "sdd",
         r"^specs/002-[a-z0-9-]+/?$"),
    Case("phases", "Renombra el atributo usr_cnt a user_count.", "direct"),
    Case("phases", "Nuevo módulo de informes de ventas con gráficos y exportación a Excel.",
         "sdd", r"^docs/phases/03-[a-z0-9-]+/?$"),
    Case("phases", "Añade el campo teléfono al perfil, con su validación.", "sdd",
         r"^docs/phases/03-[a-z0-9-]+/?$"),
]  # fmt: skip


def build(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def run(case: Case, model: str) -> dict:
    prompt = (
        "Eres el analista de requisitos del equipo. Te llega esta tarea en el proyecto de la "
        "carpeta actual (puedes leer los ficheros):\n\n"
        f"Tarea: {case.request}\n\nDetección automática: {DETECTED[case.repo]}\n\n{GUIDE}\n"
        "Ahora solo decide el modo; no escribas requisitos. Responde con JSON: "
        '{"mode": "sdd"|"direct", "reason": "...", "spec_path": "..." (vacío sin SDD)}.'
    )
    with tempfile.TemporaryDirectory(prefix="s24-sdd-") as folder:
        build(Path(folder), REPOS[case.repo])
        argv = [
            "claude", "-p", prompt, "--model", model, "--output-format", "json",
            "--json-schema", json.dumps(SCHEMA), "--tools", "Read,Glob,Grep",
            "--strict-mcp-config", "--no-session-persistence", "--max-budget-usd", "0.40",
        ]  # fmt: skip
        started = time.monotonic()
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", cwd=folder, timeout=300
        )
    data = json.loads(proc.stdout[proc.stdout.index("{") :])
    answer = data.get("structured_output") or {}
    mode = answer.get("mode", "?")
    path = str(answer.get("spec_path") or "").replace("\\", "/")
    ok = mode == case.mode and (mode != "sdd" or re.match(case.path, path) is not None)
    return {
        "case": f"{case.repo}: {case.request[:44]}",
        "ok": ok,
        "mode": mode,
        "expected": case.mode,
        "path": path,
        "reason": answer.get("reason", ""),
        "cost": data.get("total_cost_usd") or 0.0,
        "seconds": round(time.monotonic() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="sonnet")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: run(c, args.model), CASES))
    for r in results:
        print(
            f"{'OK ' if r['ok'] else 'MAL'} {r['case']:56} {r['mode']:6} (esperado "
            f"{r['expected']:6}) {r['path'] or '-'} · {r['cost']:.3f} $ {r['seconds']} s"
        )
        if not r["ok"]:
            print(f"     motivo: {r['reason']}")
    hits = sum(r["ok"] for r in results)
    cost = sum(r["cost"] for r in results)
    print(f"\n{hits}/{len(results)} aciertos · {cost / len(results):.3f} $ de media")
    return 0 if hits >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())
