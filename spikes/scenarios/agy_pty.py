"""P1–P3 for Antigravity CLI (agy): start with a prompt, type from outside, Esc, Ctrl+C, resize.

Usage: uv run python scenarios/agy_pty.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import PtyRun  # noqa: E402
from recorder import Recorder  # noqa: E402

MODEL = "gemini-3.8-flash-low"


def accept_trust(run: PtyRun, rec: Recorder) -> None:
    if run.wait_screen(r"trust the contents", timeout=30):
        rec.step("Diálogo de confianza en la carpeta")
        for _ in range(10):  # "Yes" is preselected; retry Enter until the dialog is gone
            time.sleep(0.5)
            run.key("enter")
            time.sleep(1)
            if "trust the contents" not in run.snapshot():
                break


def answered(run: PtyRun, word: str) -> bool:
    """The word appears at least twice: once in our prompt, once in the answer."""
    return run.snapshot().count(word) >= 2


def main() -> None:
    cwd = sandbox("agy-pty")
    argv = ["agy", "--model", MODEL, "-i", "Responde solo con la palabra UNO"]
    with config_guard("agy-pty") as changes:
        run = PtyRun(argv, cwd, evidence("p1-agy-pty.raw.log"), cols=120, rows=40)
        rec = Recorder("Antigravity CLI en ConPTY (P1–P3)", evidence("p1-agy-pty.md"), run)
        rec.note(f"argv: `{' '.join(argv)}` · cwd: sandbox · ventana 120×40")
        try:
            accept_trust(run, rec)

            ok = wait(lambda: answered(run, "UNO"), 90) and run.wait_idle(3, 60)
            rec.step("a) Respuesta al prompt inicial", ok)

            run.type_line("Responde solo con la palabra DOS")
            ok = wait(lambda: answered(run, "DOS"), 90)
            run.wait_idle(3, 60)
            rec.step("b) Segundo prompt escrito desde fuera", ok)

            run.type_line("Escribe los números del 1 al 300, uno por línea, sin ningún otro texto")
            run.wait_screen(r"\b2[0-9]\b", timeout=60)
            time.sleep(1.0)
            rec.step("c1) Turno largo en curso (antes de Esc)")
            run.key("esc")
            time.sleep(3)
            run.wait_idle(2, 20)
            rec.step("c2) Tras pulsar Esc")

            run.type_line("Responde solo con la palabra TRES")
            ok = wait(lambda: answered(run, "TRES"), 90)
            run.wait_idle(3, 60)
            rec.step("c3) ¿La sesión sigue viva y responde tras Esc?", ok)

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
                run.type_line("/exit")
                exited = run.wait_exit(15)
                rec.step("d3) Tras escribir /exit", exited)
            rec.note(f"Proceso vivo al final: {run.alive()}")
        finally:
            run.close()
    rec.note("Configuración global: " + ("SIN CAMBIOS" if not changes else "\n".join(changes)))
    rec.save()


def wait(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.3)
    return False


if __name__ == "__main__":
    main()
