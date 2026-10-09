"""P5 for Antigravity CLI: per-run MCP via a workspace plugin (.agents/plugins/agentic-os/).

The plugin lives inside the run's working directory, so it applies only to that run and the
user's global ~/.gemini configuration is never touched.

Usage: uv run python scenarios/agy_mcp.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import PtyRun, clean_env  # noqa: E402
from recorder import Recorder  # noqa: E402
from spike_mcp import SpikeMcp  # noqa: E402

PROMPT = (
    "Usa la herramienta report_status del servidor agentic-os con el mensaje 'empezando'. "
    "Después usa complete_task con el resumen 'listo'. Finalmente responde FIN."
)
MODEL = "gemini-3.8-flash-low"


def install_plugin(workspace: Path, url: str) -> Path:
    plugin = workspace / ".agents" / "plugins" / "agentic-os"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": "agentic-os"}), "utf-8")
    config = {"mcpServers": {"agentic-os": {"url": url}}}
    (plugin / "mcp_config.json").write_text(json.dumps(config, indent=2), "utf-8")
    return plugin


def headless(server: SpikeMcp, rec: Recorder, label: str, extra: list[str]) -> None:
    token = f"h{label}-{uuid.uuid4().hex[:6]}"
    server.tokens.add(token)
    cwd = sandbox(f"agy-mcp-headless{label}")
    install_plugin(cwd, server.path_url(token))
    argv = ["agy", "--model", MODEL, "--output-format", "json", *extra, "-p", PROMPT]
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
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {"_raw": proc.stdout[-400:]}
    calls = [c for c in server.calls() if c["run"] == token]
    rec.step(
        f"Headless {' '.join(extra) or '(sin flags)'}: llamadas recibidas",
        [c["tool"] for c in calls] == ["report_status", "complete_task"],
        screen=False,
    )
    rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
    rec.note(
        f"Respuesta: {out.get('response')!r} · denegadas: {out.get('denied_actions')} · "
        f"stderr: {proc.stderr.strip()[:300]!r}"
    )


def pty(server: SpikeMcp, rec: Recorder) -> None:
    token = f"p-{uuid.uuid4().hex[:6]}"
    server.tokens.add(token)
    cwd = sandbox("agy-mcp-pty")
    install_plugin(cwd, server.path_url(token))
    # No initial prompt: workspace plugins load only once the folder is trusted, so the
    # prompt is typed after the trust dialog and a short settle time.
    argv = ["agy", "--model", MODEL]
    run = PtyRun(argv, cwd, evidence("p5-agy-mcp-pty.raw.log"))
    rec.run = run
    try:
        if run.wait_screen(r"trust the contents", timeout=30):
            for _ in range(10):
                time.sleep(0.5)
                run.key("enter")
                time.sleep(1)
                if "trust the contents" not in run.snapshot():
                    break
        run.wait_screen(r"\? for shortcuts", timeout=30)
        time.sleep(5)
        run.type_line(PROMPT)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            screen = run.snapshot()
            if [c["tool"] for c in server.calls() if c["run"] == token] == [
                "report_status",
                "complete_task",
            ]:
                break
            # Permission prompts for the MCP tool: approve them (we are in a sandbox).
            if any(w in screen for w in ("Allow", "allow", "Permitir", "approve")):
                rec.step("Petición de permiso en la TUI")
                run.key("enter")
                time.sleep(2)
            time.sleep(1)
        run.wait_idle(3, 30)
        calls = [c for c in server.calls() if c["run"] == token]
        rec.step(
            "PTY: llamadas recibidas por el servidor",
            [c["tool"] for c in calls] == ["report_status", "complete_task"],
        )
        rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
        run.key("ctrl_c")
        time.sleep(0.5)
        run.key("ctrl_c")
        run.wait_exit(10)
    finally:
        run.close()


def main() -> None:
    log = evidence("p5-agy-mcp-calls.jsonl")
    log.unlink(missing_ok=True)
    server = SpikeMcp(set(), log)
    url = server.start()
    rec = Recorder(
        "Antigravity CLI · MCP por ejecución con plugin de workspace (P5)",
        evidence("p5-agy-mcp.md"),
    )
    rec.note(f"Servidor MCP: {url} (token en la ruta `/r/<token>/mcp`)")
    try:
        with config_guard("agy-mcp") as changes:
            headless(server, rec, "", [])
            headless(server, rec, "-skip", ["--dangerously-skip-permissions"])
            pty(server, rec)
        rec.note(f"Configuración global: {changes or 'SIN CAMBIOS'}")
    finally:
        server.stop()
        rec.save()


if __name__ == "__main__":
    main()
