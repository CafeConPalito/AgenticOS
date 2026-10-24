"""Phase 17 · manual check with the real CLIs (CA6, CA8): a real backend, a real agent (Claude
Code with haiku, or agy), a skill with a script, and a task that fits it. It checks that the
agent loaded the skill and followed it, which way the run recorded, and that the person's CLI
configuration did not change (the CLIs' own trust entries for the temporary folder aside: the
app cleans those, phase 03).

Usage (from the repo root):  uv run --project backend python spikes/skills/real_cli.py claude|agy
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "tests"))

from agentic_os.config import Settings  # noqa: E402
from live_server import live_server  # noqa: E402
from test_scheduler_e2e import Api, wait_until  # noqa: E402

HOME = Path.home()
MARK = "PROBE-REAL-4321"
SIGN = "FIRMA-8642"
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"


def tree_hash(paths: list[Path]) -> dict[str, str]:
    out = {}
    for base in paths:
        files = [base] if base.is_file() else sorted(base.rglob("*")) if base.exists() else []
        for path in files:
            if path.is_file():
                out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


WATCHED = [
    HOME / ".claude" / "settings.json",
    HOME / ".claude" / "skills",
    HOME / ".claude" / "plugins" / "installed_plugins.json",
    HOME / ".gemini" / "config",
    HOME / ".gemini" / "antigravity-cli" / "settings.json",
]


def main() -> None:
    cli = sys.argv[1] if len(sys.argv) > 1 else "claude"
    root = Path(tempfile.mkdtemp(prefix="aos-skills-real-"))
    folder = root / "proyecto"
    folder.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    before = tree_hash(WATCHED)
    settings = Settings(_env_file=None, data_dir=root / "data", check_sessions_at_startup=False)
    report: dict = {"cli": cli, "root": str(root)}
    with live_server(settings) as server:
        api = Api(server)
        project = api.post("/api/projects", {"name": "Prueba skills", "path": str(folder)})["id"]
        agent_body = {
            "name": f"Dev {cli}",
            "cli": cli,
            # «Restringido» with the terminal allowed: no bypass-mode consent dialog (that one is
            # the person's, once, in their own CLI), and the skill's script can run.
            # agy has no such dialog: «Autónomo» (--dangerously-skip-permissions) lets it run
            # the script without asking.
            "permission_mode": "restricted" if cli == "claude" else "autonomous",
            "allowed_tools": ["read", "edit", "terminal"],
            **({"model": "haiku"} if cli == "claude" else {}),
        }
        agent = api.post("/api/agents", agent_body)["id"]
        api.post(
            "/api/skills",
            {
                "scope": "general",
                "name": "fichero-de-saludo",
                "description": "Cómo escribir el fichero de saludo saludo.txt de un proyecto: "
                "su texto exacto y la firma. Úsala siempre que haya que crear saludo.txt.",
                "body": f"# Fichero de saludo\n1. Crea `saludo.txt` en la carpeta del proyecto con "
                f"la línea exacta `{MARK}`.\n2. Ejecuta el script `scripts/firma.py` de esta skill "
                "con python y añade su salida como segunda línea de `saludo.txt`.\n",
                "files": {"scripts/firma.py": {"text": f"print('{SIGN}')\n"}},
            },
        )
        api.post(
            "/api/skills",
            {
                "scope": "general",
                "name": "propuesta-comercial",
                "description": "Redactar propuestas comerciales y presupuestos para clientes.",
            },
        )
        task = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "Crea el fichero de saludo saludo.txt",
                "description": "Hazlo como indique la skill que corresponda y termina la tarea.",
            },
        )
        started = time.monotonic()
        finished = wait_until(
            lambda: api.get(f"/api/tasks/{task['id']}")["status"] in ("done", "failed", "waiting"),
            timeout=600,
        )
        current = api.get(f"/api/tasks/{task['id']}")
        report["task_status"] = current["status"]
        report["seconds"] = round(time.monotonic() - started)
        run_id = current.get("last_run_id")
        if run_id:
            report["run_skills"] = api.get(f"/api/runs/{run_id}/skills")
            report["events"] = [
                (e["kind"], e["name"], e["detail"][:80])
                for e in api.get(f"/api/runs/{run_id}/events")
                if e["kind"] in ("mcp", "system") and "skill" in (e["name"] + e["detail"]).lower()
            ]
            run = api.get(f"/api/runs/{run_id}")
            report["cost_usd"] = run.get("cost_usd")
        target = folder / "saludo.txt"
        report["saludo"] = target.read_text("utf-8") if target.exists() else None
        report["finished"] = finished
    after = tree_hash(WATCHED)
    report["config_changes"] = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"real-cli-{cli}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("evidence:", out)


if __name__ == "__main__":
    main()
