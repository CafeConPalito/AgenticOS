"""Phase 08 · R1: resuming a CLI session with a new per-run configuration.

For each CLI: a first session is told a keyword and reports to the MCP server with token A;
the session is then resumed (`claude --resume <id>` / `agy --conversation <id>`) with token B
and asked for the keyword. It must remember it and report with token B. The transcript and
usage before and after are recorded, and so is what each CLI shows for an unknown session ID.

Usage: uv run python scenarios/resume.py [claude|agy ...]
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import REPO, config_guard, run_cli, sandbox  # noqa: E402
from pty_run import PtyRun, accept_trust  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402
from usage_probe import HOME, agy_usage, claude_transcript, claude_usage  # noqa: E402

KEYWORD = "GIRASOL"
FIRST = (
    f"Recuerda esta palabra clave: {KEYWORD}. Usa la herramienta report_status del servidor "
    "agentic-os con el mensaje 'primera'. Después responde solo OK."
)
SECOND = (
    "¿Cuál era la palabra clave que te pedí recordar? Usa la herramienta report_status del "
    "servidor agentic-os con esa palabra como mensaje. Después responde solo la palabra."
)
CLAUDE_MODEL = "haiku"
AGY_MODEL = "gemini-3.8-flash-low"
BOGUS = "00000000-0000-4000-8000-000000000000"
EVIDENCE = REPO / "docs" / "phases" / "08-empaquetado" / "evidencias"


def evidence(name: str) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    return EVIDENCE / name


def usage_line(usage) -> str:
    data = usage.as_dict()
    data.pop("models", None)
    return " ".join(f"{k}={v}" for k, v in data.items())


def file_state(path: Path) -> str:
    if not path.exists():
        return f"{path} (no existe)"
    lines = path.read_text("utf-8", errors="replace").count("\n")
    return f"{path} · {path.stat().st_size} bytes · {lines} líneas"


def calls_for(server: SpikeMcp, token: str) -> list[dict]:
    return [c for c in server.calls() if c["run"] == token]


# ------------------------------------------------------------------ Claude Code
def claude_mcp(path: Path, url: str, token: str) -> Path:
    config = {
        "mcpServers": {
            "agentic-os": {
                "type": "http",
                "url": url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    }
    path.write_text(json.dumps(config), "utf-8")
    return path


def claude_hooks(path: Path, marker: Path) -> Path:
    command = f'cmd /c echo stop>> "{marker}"'
    hooks = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
    path.write_text(json.dumps(hooks), "utf-8")
    return path


def claude_argv(cwd: Path, server: SpikeMcp, token: str, label: str) -> list[str]:
    server.tokens.add(token)
    mcp = claude_mcp(cwd.parent / f"{cwd.name}-mcp-{label}.json", server.url, token)
    marker = cwd.parent / f"{cwd.name}-stop-{label}.txt"
    settings = claude_hooks(cwd.parent / f"{cwd.name}-settings-{label}.json", marker)
    return [
        "claude",
        "--model",
        CLAUDE_MODEL,
        "--mcp-config",
        str(mcp),
        "--strict-mcp-config",
        "--settings",
        str(settings),
        "--allowedTools",
        "mcp__agentic-os__*",
        "--output-format",
        "json",
    ]


def claude(server: SpikeMcp, rec: Recorder) -> None:
    rec.note("\n# Claude Code\n")
    cwd = sandbox("resume-claude")
    session = str(uuid.uuid4())
    token_a, token_b = f"ca-{uuid.uuid4().hex[:6]}", f"cb-{uuid.uuid4().hex[:6]}"
    transcript = claude_transcript(cwd, session)

    first = run_cli(
        [*claude_argv(cwd, server, token_a, "a"), "--session-id", session, "-p", FIRST], cwd
    )
    rec.step(
        "Sesión 1 (`--session-id`, token A)",
        first.returncode == 0 and bool(calls_for(server, token_a)),
        screen=False,
    )
    rec.note(f"Respuesta: {(first.json or {}).get('result')!r} · rc={first.returncode}")
    rec.note(f"Coste del CLI: {(first.json or {}).get('total_cost_usd')}")
    rec.note(f"Transcript: {file_state(transcript)}")
    if transcript.exists():
        rec.note(f"Consumo leído: {usage_line(claude_usage(transcript))}")

    second = run_cli(
        [*claude_argv(cwd, server, token_b, "b"), "--resume", session, "-p", SECOND], cwd
    )
    calls_b = calls_for(server, token_b)
    remembered = any(KEYWORD in json.dumps(c, ensure_ascii=False) for c in calls_b)
    rec.step(
        "Reanudada (`--resume`, token B): recuerda la palabra y llama con B",
        remembered,
        screen=False,
    )
    out = second.json or {}
    rec.note(
        f"Respuesta: {out.get('result')!r} · session_id={out.get('session_id')} · "
        f"rc={second.returncode} · stderr={second.stderr[:300]!r}"
    )
    rec.note(f"Coste del CLI (solo este proceso): {out.get('total_cost_usd')}")
    rec.note("Llamadas con token A: " + json.dumps(calls_for(server, token_a), ensure_ascii=False))
    rec.note("Llamadas con token B: " + json.dumps(calls_b, ensure_ascii=False))
    for label in ("a", "b"):
        marker = cwd.parent / f"{cwd.name}-stop-{label}.txt"
        text = marker.read_text("utf-8", errors="replace") if marker.exists() else ""
        rec.note(f"Hook Stop de la config {label.upper()}: {text.count('hook_event_name')} veces")
    rec.note(f"Transcript tras reanudar: {file_state(transcript)}")
    others = sorted(p.name for p in transcript.parent.glob("*.jsonl"))
    rec.note(f"Transcripts en la carpeta del proyecto: {others}")
    if transcript.exists():
        rec.note(f"Consumo leído tras reanudar: {usage_line(claude_usage(transcript))}")
    if out.get("session_id") and out.get("session_id") != session:
        other = claude_transcript(cwd, out["session_id"])
        rec.note(f"Transcript de la sesión nueva: {file_state(other)}")
        if other.exists():
            rec.note(f"Consumo de la sesión nueva: {usage_line(claude_usage(other))}")

    bogus = run_cli(["claude", "--resume", BOGUS, "-p", "hola"], cwd, timeout=60)
    rec.step("ID inexistente en modo headless", screen=False)
    rec.note(
        f"rc={bogus.returncode} · stdout={bogus.stdout[:300]!r} · stderr={bogus.stderr[:300]!r}"
    )
    run = PtyRun(["claude", "--resume", BOGUS], cwd, evidence("r1-claude-bogus.raw.log"))
    rec.run = run
    try:
        accept_trust(run, "claude", timeout=15)
        run.wait_idle(3, 30)
        rec.step("ID inexistente en la TUI")
        rec.note(f"¿Sigue vivo? {run.alive()}")
    finally:
        run.close()
        rec.run = None


def cost_states(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text("utf-8", errors="replace").splitlines():
        if '"cost-state"' in line:
            row = json.loads(line)
            rows.append({k: row.get(k) for k in ("totalCostUSD", "totalDuration", "startTime")})
    return rows


def claude_killed(server: SpikeMcp, rec: Recorder) -> None:
    """The real case: an interactive session killed after a turn (no cost-state written)."""
    rec.note("\n# Claude Code · sesión interactiva cortada a la fuerza\n")
    cwd = sandbox("resume-claude-killed")
    session = str(uuid.uuid4())
    token_a, token_b = f"ka-{uuid.uuid4().hex[:6]}", f"kb-{uuid.uuid4().hex[:6]}"
    transcript = claude_transcript(cwd, session)
    argv = [
        a for a in claude_argv(cwd, server, token_a, "a") if a not in ("--output-format", "json")
    ]
    run = PtyRun([*argv, "--session-id", session, FIRST], cwd, evidence("r1-claude-killed.raw.log"))
    rec.run = run
    try:
        accept_trust(run, "claude", timeout=20)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not calls_for(server, token_a):
            time.sleep(1)
        run.wait_idle(4, 60)
        rec.step("Turno terminado en la TUI", bool(calls_for(server, token_a)))
    finally:
        run.close()  # kills the process tree: no clean exit
        rec.run = None
    time.sleep(1)
    rec.note(f"Transcript tras matarla: {file_state(transcript)}")
    rec.note(f"cost-state: {cost_states(transcript) if transcript.exists() else '-'}")
    if transcript.exists():
        rec.note(f"Consumo leído (sin cost-state): {usage_line(claude_usage(transcript))}")
    second = run_cli(
        [*claude_argv(cwd, server, token_b, "b"), "--resume", session, "-p", SECOND], cwd
    )
    out = second.json or {}
    calls_b = calls_for(server, token_b)
    rec.step(
        "Reanudada tras el corte: recuerda y llama con B",
        any(KEYWORD in json.dumps(c, ensure_ascii=False) for c in calls_b),
        screen=False,
    )
    rec.note(
        f"Respuesta: {out.get('result')!r} · coste del CLI: {out.get('total_cost_usd')} · "
        f"rc={second.returncode}"
    )
    rec.note(f"cost-state tras reanudar: {cost_states(transcript) if transcript.exists() else '-'}")
    if transcript.exists():
        rec.note(f"Consumo leído tras reanudar: {usage_line(claude_usage(transcript))}")


# ------------------------------------------------------------------ Antigravity
def agy_plugin(workspace: Path, url: str) -> None:
    plugin = workspace / ".agents" / "plugins" / "agentic-os"
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": "agentic-os"}), "utf-8")
    config = {"mcpServers": {"agentic-os": {"url": url}}}
    (plugin / "mcp_config.json").write_text(json.dumps(config), "utf-8")


def newest_conversation(since: float) -> str | None:
    brain = HOME / ".gemini" / "antigravity-cli" / "brain"
    fresh = [p for p in brain.iterdir() if p.is_dir() and p.stat().st_mtime >= since]
    return max(fresh, key=lambda p: p.stat().st_mtime).name if fresh else None


def agy_transcript(conversation: str) -> Path:
    return (
        HOME
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / conversation
        / ".system_generated"
        / "logs"
        / "transcript_full.jsonl"
    )


def agy(server: SpikeMcp, rec: Recorder) -> None:
    rec.note("\n# Antigravity CLI\n")
    cwd = sandbox("resume-agy")
    token_a, token_b = f"aa-{uuid.uuid4().hex[:6]}", f"ab-{uuid.uuid4().hex[:6]}"
    base = [
        "agy",
        "--model",
        AGY_MODEL,
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    ]

    server.tokens.add(token_a)
    agy_plugin(cwd, server.path_url(token_a))
    started = time.time() - 1
    first = run_cli([*base, "-p", FIRST], cwd)
    conversation = newest_conversation(started)
    rec.step(
        "Sesión 1 (token A)",
        first.returncode == 0 and bool(calls_for(server, token_a)),
        screen=False,
    )
    rec.note(
        f"Respuesta: {(first.json or {}).get('response')!r} · rc={first.returncode} · "
        f"conversación={conversation} · claves JSON={sorted((first.json or {}).keys())}"
    )
    if not conversation:
        rec.note("No se encontró la conversación: se omite la reanudación.")
        return
    transcript = agy_transcript(conversation)
    rec.note(f"Transcript: {file_state(transcript)}")
    if transcript.exists():
        rec.note(f"Consumo leído: {usage_line(agy_usage(transcript))}")

    server.tokens.add(token_b)
    agy_plugin(cwd, server.path_url(token_b))
    started = time.time() - 1
    second = run_cli([*base, "--conversation", conversation, "-p", SECOND], cwd)
    calls_b = calls_for(server, token_b)
    remembered = any(KEYWORD in json.dumps(c, ensure_ascii=False) for c in calls_b)
    rec.step(
        "Reanudada (`--conversation`, token B): recuerda la palabra y llama con B",
        remembered,
        screen=False,
    )
    rec.note(
        f"Respuesta: {(second.json or {}).get('response')!r} · rc={second.returncode} · "
        f"stderr={second.stderr[:300]!r}"
    )
    rec.note(f"Conversación más reciente tras reanudar: {newest_conversation(started)}")
    rec.note("Llamadas con token A: " + json.dumps(calls_for(server, token_a), ensure_ascii=False))
    rec.note("Llamadas con token B: " + json.dumps(calls_b, ensure_ascii=False))
    rec.note(f"Transcript tras reanudar: {file_state(transcript)}")
    if transcript.exists():
        rec.note(f"Consumo leído tras reanudar: {usage_line(agy_usage(transcript))}")

    bogus = run_cli([*base, "--conversation", BOGUS, "-p", "hola"], cwd, timeout=90)
    rec.step("ID inexistente en modo headless", screen=False)
    rec.note(
        f"rc={bogus.returncode} · stdout={bogus.stdout[:300]!r} · stderr={bogus.stderr[:300]!r}"
    )
    run = PtyRun(["agy", "--conversation", BOGUS], cwd, evidence("r1-agy-bogus.raw.log"))
    rec.run = run
    try:
        accept_trust(run, "agy", timeout=15)
        run.wait_idle(3, 30)
        rec.step("ID inexistente en la TUI")
        rec.note(f"¿Sigue vivo? {run.alive()}")
        run.key("ctrl_c")
        time.sleep(0.5)
        run.key("ctrl_c")
        run.wait_exit(10)
    finally:
        run.close()
        rec.run = None


def main() -> None:
    which = sys.argv[1:] or ["claude", "agy"]
    log = evidence("r1-resume-calls.jsonl")
    log.unlink(missing_ok=True)
    server = SpikeMcp(set(), log)
    server.start()
    rec = Recorder(
        "Fase 08 · R1: reanudar sesiones con configuración nueva", evidence("r1-reanudar.md")
    )
    try:
        with config_guard("resume") as changes:
            if "claude" in which:
                claude(server, rec)
            if "claude" in which or "claude-killed" in which:
                claude_killed(server, rec)
            if "agy" in which:
                agy(server, rec)
        rec.note(f"\nConfiguración global: {changes or 'SIN CAMBIOS'}")
    finally:
        server.stop()
        rec.save()


if __name__ == "__main__":
    main()
