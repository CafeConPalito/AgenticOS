"""P1–P3 for Claude Code: start with a prompt, type from outside, Esc, Ctrl+C, resize.

Usage: uv run python scenarios/claude_pty.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import PtyRun  # noqa: E402
from recorder import Recorder  # noqa: E402

PROMPT_LINE = r"❯\s*$|>\s*$|\? for shortcuts"


def accept_trust(run: PtyRun, rec: Recorder) -> None:
    if run.wait_screen(r"trust this folder", timeout=30):
        rec.step("Diálogo de confianza en la carpeta")
        # Keys sent before the menu is interactive are dropped: retry until selected.
        for _ in range(10):
            time.sleep(0.5)
            run.key("down")
            if run.wait_screen(r"❯ Yes, I trust", timeout=1.5):
                break
        run.key("enter")


def main() -> None:
    cwd = sandbox("claude-pty")
    # --strict-mcp-config without --mcp-config: none of the user's global MCP servers start.
    argv = [
        "claude",
        "--model",
        "haiku",
        "--strict-mcp-config",
        "Responde solo con la palabra UNO",
    ]
    with config_guard("claude-pty") as changes:
        run = PtyRun(argv, cwd, evidence("p1-claude-pty.raw.log"), cols=120, rows=40)
        rec = Recorder("Claude Code en ConPTY (P1–P3)", evidence("p1-claude-pty.md"), run)
        rec.note(f"argv: `{' '.join(argv)}` · cwd: sandbox · ventana 120×40")
        try:
            accept_trust(run, rec)

            ok = run.wait_screen(r"\bUNO\b", timeout=90) and run.wait_idle(3, 60)
            rec.step("a) Respuesta al prompt inicial", ok)

            run.type_line("Responde solo con la palabra DOS")
            ok = run.wait_screen(r"\bDOS\b.*\n(?s:.*)\bDOS\b|●\s*DOS", timeout=90)
            run.wait_idle(3, 60)
            rec.step("b) Segundo prompt escrito desde fuera", ok)

            run.type_line("Escribe los números del 1 al 300, uno por línea, sin ningún otro texto")
            run.wait_screen(r"\b1[0-9]\b", timeout=60)
            time.sleep(1.5)
            rec.step("c1) Turno largo en curso (antes de Esc)")
            run.key("esc")
            interrupted = run.wait_screen(r"interrupt", timeout=15)
            run.wait_idle(2, 20)
            rec.step("c2) Tras pulsar Esc", interrupted)

            run.type_line("Responde solo con la palabra TRES")
            ok = run.wait_screen(r"●\s*TRES|\bTRES\b\s*$", timeout=90)
            run.wait_idle(3, 60)
            rec.step("c3) La sesión sigue viva y responde tras la interrupción", ok)

            run.resize(90, 30)
            time.sleep(2)
            rec.step("e) Tras redimensionar a 90×30")

            run.key("ctrl_c")
            time.sleep(1.5)
            rec.step("d1) Tras un Ctrl+C (sin turno en curso)", run.alive())
            run.key("ctrl_c")
            exited = run.wait_exit(10)
            rec.step("d2) Tras un segundo Ctrl+C", exited)
            if not exited:
                # Clear any pending input/suggestion, then exit with the slash command.
                run.key("esc")
                time.sleep(0.5)
                run.type_line("/exit")
                exited = run.wait_exit(15)
                rec.step("d3) Tras escribir /exit", exited)
            rec.note(f"Proceso vivo al final: {run.alive()}")
        finally:
            run.close()
    rec.note("Configuración global: " + ("SIN CAMBIOS" if not changes else "\n".join(changes)))
    rec.save()


if __name__ == "__main__":
    main()
