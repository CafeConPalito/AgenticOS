"""P5 for Claude Code: per-run MCP injection with --mcp-config + --strict-mcp-config.

Runs once headless and once in a PTY. The MCP server must receive both tool calls tagged with
the run token, and the user's global configuration must stay untouched.

Usage: uv run python scenarios/claude_mcp.py
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
TOOLS = "mcp__agentic-os__report_status mcp__agentic-os__complete_task"


def mcp_config(path: Path, url: str, token: str) -> Path:
    config = {
        "mcpServers": {
            "agentic-os": {
                "type": "http",
                "url": url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    }
    path.write_text(json.dumps(config, indent=2), "utf-8")
    return path


def base_argv(config: Path) -> list[str]:
    return [
        "claude",
        "--model",
        "haiku",
        "--setting-sources",
        "project,local",
        "--mcp-config",
        str(config),
        "--strict-mcp-config",
        "--allowedTools",
        TOOLS,
    ]


def main() -> None:
    log = evidence("p5-claude-mcp-calls.jsonl")
    log.unlink(missing_ok=True)
    headless_token, pty_token = f"h-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"
    server = SpikeMcp({headless_token, pty_token}, log)
    url = server.start()
    rec = Recorder("Claude Code · MCP por ejecución (P5)", evidence("p5-claude-mcp.md"))
    rec.note(f"Servidor MCP: {url} · tokens: {headless_token} (headless), {pty_token} (PTY)")
    try:
        with config_guard("claude-mcp") as changes:
            # -- headless ---------------------------------------------------------------
            cwd = sandbox("claude-mcp-headless")
            config = mcp_config(cwd.parent / f"{cwd.name}.mcp.json", url, headless_token)
            argv = [*base_argv(config), "--output-format", "json", "-p", PROMPT]
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
            out = json.loads(proc.stdout or "{}")
            calls = [c for c in server.calls() if c["run"] == headless_token]
            rec.step(
                "Headless: llamadas recibidas por el servidor",
                [c["tool"] for c in calls] == ["report_status", "complete_task"],
                screen=False,
            )
            rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
            rec.note(f"Respuesta: {out.get('result')!r} · coste: {out.get('total_cost_usd')}")

            # -- PTY (interactive) ------------------------------------------------------
            cwd = sandbox("claude-mcp-pty")
            config = mcp_config(cwd.parent / f"{cwd.name}.mcp.json", url, pty_token)
            # The prompt goes first: variadic flags such as --allowedTools <tools...> would
            # otherwise swallow a trailing positional prompt.
            argv = base_argv(config)
            argv.insert(1, PROMPT)
            run = PtyRun(argv, cwd, evidence("p5-claude-mcp-pty.raw.log"))
            rec.run = run
            try:
                if run.wait_screen(r"trust this folder", timeout=30):
                    for _ in range(10):
                        time.sleep(0.5)
                        run.key("down")
                        if run.wait_screen(r"❯ Yes, I trust", timeout=1.5):
                            break
                    run.key("enter")
                done = run.wait_screen(r"●\s*FIN", timeout=120)
                run.wait_idle(3, 30)
                calls = [c for c in server.calls() if c["run"] == pty_token]
                rec.step(
                    "PTY: llamadas recibidas por el servidor",
                    done and [c["tool"] for c in calls] == ["report_status", "complete_task"],
                )
                rec.note("```json\n" + json.dumps(calls, ensure_ascii=False, indent=1) + "\n```")
                run.key("esc")
                time.sleep(0.5)
                run.type_line("/exit")
                run.wait_exit(15)
            finally:
                run.close()
        rec.note(f"Configuración global: {changes or 'SIN CAMBIOS'}")
    finally:
        server.stop()
        rec.save()


if __name__ == "__main__":
    main()
