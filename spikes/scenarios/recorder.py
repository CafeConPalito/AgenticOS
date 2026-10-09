"""Records scenario steps (action, timing, screen snapshot) into a Markdown evidence file."""

from __future__ import annotations

from pathlib import Path

from pty_run import PtyRun


class Recorder:
    def __init__(self, title: str, path: Path, run: PtyRun | None = None) -> None:
        self.path = path
        self.run = run
        self.parts: list[str] = [f"# {title}\n"]

    def note(self, text: str) -> None:
        print(text)
        self.parts.append(f"{text}\n")

    def step(self, label: str, ok: bool | None = None, screen: bool = True) -> None:
        mark = "" if ok is None else (" ✅" if ok else " ❌")
        elapsed = f"t={self.run.elapsed():.1f}s" if self.run else ""
        header = f"## {label}{mark} ({elapsed})"
        print(header)
        self.parts.append(header + "\n")
        if screen and self.run:
            shot = self.run.snapshot()
            print(shot)
            self.parts.append("```text\n" + shot + "\n```\n")

    def save(self) -> None:
        self.path.write_text("\n".join(self.parts), "utf-8")
