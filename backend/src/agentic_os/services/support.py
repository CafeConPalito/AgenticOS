"""The logs to send when something fails (phase 20, ADR 0027).

A `.zip` with the backend's log (its rotated files, newest first, up to MAX_LOG_BYTES), the
desktop shell's log and an `info.txt` with versions, system and counts. Every line goes through
`Redactor` first: the run tokens, credentials and key formats, the actual secrets of the
connections, e-mail addresses and the user's name in paths. The runs' terminal output, tasks,
knowledge and conversations are never included.
"""

from __future__ import annotations

import io
import platform
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os import __version__
from agentic_os.models import Agent, Project, Run, Task
from agentic_os.services.clis import SPECS
from agentic_os.services.redact import Redactor, home_hint, stored_secrets

MAX_LOG_BYTES = 10 * 1024 * 1024  # of the backend's log, newest lines kept
MAX_DESKTOP_BYTES = 2 * 1024 * 1024
LABELS = {
    "run_token": "tokens de ejecución",
    "header": "cabeceras de autenticación",
    "query": "valores en URLs",
    "assignment": "claves y contraseñas",
    "key": "claves de API conocidas",
    "secret": "secretos de las conexiones",
    "email": "correos",
    "user_path": "nombres de usuario en rutas",
}


@dataclass
class LogFile:
    name: str  # in the zip
    path: Path
    size: int  # what goes in (after trimming), before redaction


@dataclass
class Bundle:
    path: Path
    size: int
    files: list[str]
    redactions: dict[str, int] = field(default_factory=dict)


def log_files(folder: Path) -> list[LogFile]:
    """What would go in: the backend's log (current first, then .1, .2…) and the shell's."""
    found: list[LogFile] = []
    budget = MAX_LOG_BYTES
    current = folder / "backend.log"
    rotated = sorted(folder.glob("backend.log.*"), key=lambda p: _suffix(p.name))
    for path in [current, *rotated]:
        if budget <= 0 or not path.is_file():
            continue
        size = min(path.stat().st_size, budget)
        budget -= size
        found.append(LogFile(f"logs/{path.name}", path, size))
    desktop = folder / "desktop.log"
    if desktop.is_file():
        found.append(
            LogFile("logs/desktop.log", desktop, min(desktop.stat().st_size, MAX_DESKTOP_BYTES))
        )
    return found


def _suffix(name: str) -> int:
    tail = name.rsplit(".", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _tail(path: Path, size: int) -> str:
    """The last `size` bytes, from the first whole line."""
    with path.open("rb") as handle:
        total = path.stat().st_size
        handle.seek(max(0, total - size))
        data = handle.read(size)
    text = data.decode("utf-8", errors="replace")
    if total > size and "\n" in text:
        text = text.split("\n", 1)[1]
    return text


def info_text(db: Session, cli_version: Callable[[str], str | None], redactions: dict) -> str:
    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    lines = [
        f"Agentic OS {__version__}",
        f"Generado: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Sistema: {platform.platform()} ({platform.machine()})",
        f"Python: {sys.version.split()[0]}",
        "",
        "CLIs:",
        *[f"  {spec.name}: {cli_version(spec.id) or 'sin comprobar'}" for spec in SPECS],
        "",
        f"Agentes: {count(Agent)} · Proyectos: {count(Project)} · Tareas: {count(Task)}"
        f" · Ejecuciones: {count(Run)}",
        "",
        "Ocultado al preparar este archivo:",
        *(
            [f"  {LABELS.get(kind, kind)}: {n}" for kind, n in sorted(redactions.items()) if n]
            or ["  nada"]
        ),
        "",
        "No se incluyen las salidas de terminal de las ejecuciones, el contenido de las tareas,",
        "el conocimiento ni las conversaciones.",
    ]
    return home_hint("\n".join(lines)) + "\n"


def default_target(now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    downloads = Path.home() / "Downloads"
    folder = downloads if downloads.is_dir() else Path.home()
    return folder / f"agentic-os-registros-{stamp}.zip"


def bundle(
    db: Session,
    logs_dir: Path,
    target: Path,
    cli_version: Callable[[str], str | None] = lambda _cli: None,
) -> Bundle:
    """Writes the zip at `target` (atomically) and says what went in and what was hidden."""
    redactor = Redactor(stored_secrets(db))
    files = log_files(logs_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            text = _tail(item.path, item.size)
            archive.writestr(item.name, "\n".join(redactor.line(line) for line in text.split("\n")))
        archive.writestr("info.txt", info_text(db, cli_version, dict(redactor.counts)))
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(buffer.getvalue())
    partial.replace(target)
    return Bundle(
        path=target,
        size=target.stat().st_size,
        files=[item.name for item in files] + ["info.txt"],
        redactions={k: v for k, v in redactor.counts.items() if v},
    )
