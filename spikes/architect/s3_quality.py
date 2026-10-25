"""Phase 19 · spike S3: quality and cost of the Architect over ten scripted conversations.

The CLI mechanics were settled in S1/S2 (one interactive process per conversation). Here each
turn is a `claude -p --session-id/--resume` call with the same instructions, MCP and model,
which behaves the same and is far quicker to script. The user's side is scripted: an opening
message and fixed answers, then «complete it with what you have».

Per conversation it measures: questions in the first reply, whether the sheet was filled from
the first turn, references the model invented (rejected by the server), final issues, pipeline
valid at the first `set_pipeline`, turns, seconds and cost.

Usage: uv run python architect/s3_quality.py [model] [scenario ...]   (from spikes/)
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from modes import instructions  # noqa: E402

from common import sandbox  # noqa: E402
from pty_run import clean_env  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "19-meta-agentes" / "evidencias"
HERE = Path(__file__).resolve().parent
SERVER = HERE / "servers" / "architect_full.py"
BASE = (HERE / "instructions.md").read_text("utf-8")
CLOSE = "Con eso es suficiente: completa lo que falte con tu mejor criterio y dime si está listo."

SCENARIOS = {
    "redactor": (
        "agent",
        "",
        "Quiero un agente que me escriba los posts del blog de la empresa.",
        [
            "Somos una tienda online de material de montaña. El público son aficionados, no expertos. "
            "Tono cercano. Que use nuestra guía de marca y que cuide el SEO.",
        ],
    ),
    "comercial": (
        "agent",
        "",
        "Necesito un comercial que prepare propuestas para clientes B2B.",
        [
            "Vendemos el catálogo a tiendas físicas. Las propuestas llevan precios de las tarifas 2026. "
            "Nunca debe enviar nada a nadie: solo dejar el borrador.",
        ],
    ),
    "qa_estricto": (
        "agent",
        "",
        "Crea un QA muy estricto para la tienda online que pruebe en el "
        "navegador cada criterio de aceptación y revise accesibilidad.",
        [],
    ),
    "traductor_vago": (
        "agent",
        "",
        "Quiero un traductor.",
        [
            "Del español al inglés, para las fichas de producto y los posts. Inglés americano.",
            "Que no cambie nombres de producto ni precios.",
        ],
    ),
    "notion": (
        "agent",
        "",
        "Quiero un agente que lea las notas de reuniones que tenemos en Notion "
        "y me haga un resumen semanal con las tareas pendientes.",
        [
            "Las notas están en un espacio de Notion del equipo. El resumen lo quiero en Markdown.",
        ],
    ),
    "modelo_inexistente": (
        "agent",
        "",
        "Hazme un agente de documentación técnica de la API de la "
        "tienda que use el modelo gpt-5 de OpenAI.",
        [
            "Vale, lo que tú veas mejor.",
        ],
    ),
    "mejorar_qa": (
        "improve_agent",
        "QA",
        "Quiero que el QA sea más estricto con los tests: que "
        "rechace si falta un test de un caso límite, y que pueda leer las issues de GitHub.",
        [],
    ),
    "equipo_contenidos": (
        "team",
        "",
        "Monta un equipo de contenidos para el proyecto Blog "
        "corporativo: alguien que investigue el tema, alguien que redacte el post "
        "y alguien que lo revise antes de publicarlo.",
        [
            "La revisión final la quiero hacer yo también, después del revisor. Si el revisor ve "
            "problemas, que vuelva al redactor.",
        ],
    ),
    "equipo_dev": (
        "team",
        "",
        "Para la Tienda online quiero un flujo donde, después de los "
        "requisitos, las tareas de API vayan a un dev de backend, las de interfaz a un "
        "dev de frontend, y las que tocan las dos cosas pasen por ambos antes de QA. "
        "Reutiliza los agentes que ya tengo.",
        [],
    ),
    "mejorar_pipeline": (
        "improve_pipeline",
        "Tienda online",
        "Añade una revisión de seguridad "
        "antes de QA en la Tienda online, con un agente nuevo especializado.",
        [],
    ),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int, token: str, state: Path, mode: str, target: str) -> subprocess.Popen:
    env = {**clean_env(), "ARCH_TOKEN": token, "ARCH_STATE": str(state), "ARCH_MODE": mode,
           "ARCH_TARGET": target}  # fmt: skip
    out = open(state.parent / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen([sys.executable, str(SERVER), str(port)], env=env, stdout=out,
                            stderr=subprocess.STDOUT)  # fmt: skip
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("server did not start")


def call(
    root: Path, files: tuple[Path, Path], session: str, first: bool, text: str, model: str
) -> dict:
    mcp, prompt_file = files
    argv = [
        "claude", "-p", text,
        "--session-id" if first else "--resume", session,
        "--setting-sources", "project,local",
        "--mcp-config", str(mcp), "--strict-mcp-config",
        "--append-system-prompt-file", str(prompt_file),
        "--tools", "", "--allowedTools", "mcp__architect__*",
        "--model", model, "--output-format", "json",
    ]  # fmt: skip
    t0 = time.monotonic()
    proc = subprocess.run(argv, cwd=root, env=clean_env(), capture_output=True, text=True,
                          encoding="utf-8", timeout=600)  # fmt: skip
    seconds = round(time.monotonic() - t0, 1)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": (proc.stderr or proc.stdout)[:500], "seconds": seconds}
    return {
        "reply": data.get("result", ""),
        "cost": data.get("total_cost_usd") or 0.0,
        "seconds": seconds,
        "turns_inside": data.get("num_turns"),
        "is_error": data.get("is_error"),
    }


def run_scenario(name: str, model: str) -> dict:
    mode, target, opening, answers = SCENARIOS[name]
    root = sandbox(f"s3-{name}")
    state = root / "state.json"
    port, token = free_port(), uuid.uuid4().hex
    server = start_server(port, token, state, mode, target)
    mcp = root / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"architect": {
        "type": "http", "url": f"http://127.0.0.1:{port}/mcp",
        "headers": {"Authorization": f"Bearer {token}"}}}}), "utf-8")  # fmt: skip
    prompt_file = root / "architect.md"
    prompt_file.write_text(instructions(BASE, mode, target), "utf-8")
    session = str(uuid.uuid4())
    turns = []
    sheet_calls_after: list[int] = []
    try:
        for i, text in enumerate([opening, *answers, CLOSE]):
            turns.append(
                {"user": text, **call(root, (mcp, prompt_file), session, i == 0, text, model)}
            )
            st = json.loads(state.read_text("utf-8"))
            sheet_calls_after.append(sum(1 for c in st["calls"] if c["tool"] in
                                         ("update_sheet", "set_pipeline", "update_team")))  # fmt: skip
    finally:
        server.terminate()
    st = json.loads(state.read_text("utf-8"))
    issues = {ref: [f"Falta {k}" for k in ("name", "role", "cli", "instructions") if not s.get(k)]
              for ref, s in st["agents"].items()}  # fmt: skip
    first_reply = turns[0].get("reply", "")
    return {
        "name": name,
        "mode": mode,
        "turns": len(turns),
        "questions_first_reply": first_reply.count("?"),
        "filled_in_first_turn": sheet_calls_after[0] > 0,
        "rejected_references": st["rejected"],
        "final_agent_issues": issues,
        "pipeline_attempts": st.get("pipeline_attempts", []),
        "pipeline_valid_first": (not st["pipeline_attempts"][0])
        if st.get("pipeline_attempts")
        else None,
        "pipeline_valid_final": (not st["pipeline_attempts"][-1])
        if st.get("pipeline_attempts")
        else None,
        "suggested_connections": st["suggested_connections"],
        "unlock_requests": st["unlock_requests"],
        "tools_used": sorted({c["tool"] for c in st["calls"]} - {"start", "update_sheet:after"}),
        "cost_usd": round(sum(t.get("cost", 0) for t in turns), 4),
        "seconds": round(sum(t.get("seconds", 0) for t in turns), 1),
        "errors": [t["error"] for t in turns if t.get("error")],
        "final": {
            "agents": st["agents"],
            "existing": st["existing"],
            "team": st["team"],
            "pipeline": st["pipeline"],
        },  # fmt: skip
        "conversation": [{"user": t["user"], "reply": t.get("reply", "")} for t in turns],
    }


def main() -> None:
    args = sys.argv[1:]
    model = args.pop(0) if args and args[0] in ("haiku", "sonnet", "opus") else "sonnet"
    wanted = args or list(SCENARIOS)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda n: run_scenario(n, model), wanted))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s3-quality-{model}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps({"model": model, "results": results}, ensure_ascii=False, indent=1), "utf-8"
    )
    for r in results:
        print(json.dumps({k: r[k] for k in ("name", "turns", "questions_first_reply",
              "filled_in_first_turn", "pipeline_valid_first", "pipeline_valid_final", "cost_usd",
              "seconds")} | {"rejected": len(r["rejected_references"]),
              "issues": sum(len(v) for v in r["final_agent_issues"].values()),
              "suggested": [s["ref"] for s in r["suggested_connections"]], "errors": len(r["errors"])},
              ensure_ascii=False))  # fmt: skip
    print("evidence:", out)


if __name__ == "__main__":
    main()
