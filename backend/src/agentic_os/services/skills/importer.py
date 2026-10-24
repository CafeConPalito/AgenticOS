"""Bringing skills into the library (phase 17, CA2): a folder, a `.zip` or a lone `SKILL.md` on
disk, and the skills the person already has in their CLIs. The originals are only read."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import Project, Skill, SkillVersion
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import (
    MAX_FILES,
    MAX_TOTAL_BYTES,
    SKILL_MD,
    compose_skill_md,
    parse_skill_md,
)

# Never part of a skill, even if they sit in its folder.
SKIPPED_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", ".DS_Store", "__MACOSX"})
SKIPPED_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def _too_large() -> SkillError:
    return SkillError("skill_too_large", "La skill pasa de 5 MB en total.", limit=MAX_TOTAL_BYTES)


def read_folder(folder: Path) -> dict[str, bytes]:
    """The files of a skill folder (its `SKILL.md` at the root), stopping early at the limits."""
    if not (folder / SKILL_MD).is_file() and not any(
        p.name.lower() == "skill.md" for p in folder.iterdir() if p.is_file()
    ):
        raise SkillError("no_skill_md", f"La carpeta «{folder.name}» no tiene un SKILL.md.")
    files: dict[str, bytes] = {}
    total = 0
    for root, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        for name in sorted(names):
            if name in SKIPPED_FILES:
                continue
            path = Path(root) / name
            if path.is_symlink():
                continue  # it could point anywhere on the disk
            total += path.stat().st_size
            if total > MAX_TOTAL_BYTES:
                raise _too_large()
            files[path.relative_to(folder).as_posix()] = path.read_bytes()
            if len(files) > MAX_FILES:
                raise SkillError(
                    "too_many_files",
                    f"La skill tiene más de {MAX_FILES} ficheros.",
                    limit=MAX_FILES,
                )
    return files


def read_zip(data: bytes) -> dict[str, bytes]:
    """The files of a zipped skill. If everything is inside one folder, that folder is the
    skill. Sizes are checked before anything is extracted (zip bombs)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillError("bad_zip", "El fichero no es un .zip válido.") from exc
    entries = [i for i in archive.infolist() if not i.is_dir()]
    names = [i.filename.replace("\\", "/") for i in entries]
    entries = [
        i
        for i, n in zip(entries, names, strict=True)
        if not any(
            part in SKIPPED_DIRS or part in SKIPPED_FILES or part.startswith("._")
            for part in n.split("/")
        )
    ]
    if len(entries) > MAX_FILES:
        raise SkillError("too_many_files", f"La skill tiene más de {MAX_FILES} ficheros.")
    if sum(i.file_size for i in entries) > MAX_TOTAL_BYTES:
        raise _too_large()
    paths = [i.filename.replace("\\", "/") for i in entries]
    prefix = ""
    if not any(p.lower() == "skill.md" for p in paths):
        tops = {p.split("/", 1)[0] for p in paths}
        if len(tops) == 1 and all("/" in p for p in paths):
            prefix = f"{tops.pop()}/"
    files: dict[str, bytes] = {}
    for info, path in zip(entries, paths, strict=True):
        files[path[len(prefix) :]] = archive.read(info)  # check_files normalises the paths
    return files


def read_path(path: Path) -> dict[str, bytes]:
    if path.is_dir():
        return read_folder(path)
    if not path.is_file():
        raise SkillError("not_found", f"No se encuentra «{path}».", path=str(path))
    if path.suffix.lower() == ".zip":
        if path.stat().st_size > MAX_TOTAL_BYTES * 2:
            raise _too_large()
        return read_zip(path.read_bytes())
    if path.name.lower() == "skill.md" or path.suffix.lower() == ".md":
        return {SKILL_MD: path.read_bytes()}
    raise SkillError(
        "unsupported",
        "Solo se importan carpetas con SKILL.md, ficheros .zip o un SKILL.md.",
        path=str(path),
    )


def renamed(files: dict[str, bytes], name: str) -> dict[str, bytes]:
    """The same skill with another name in its header (an import whose name is taken)."""
    parsed = parse_skill_md(files[SKILL_MD].decode("utf-8"))
    meta = {**parsed.meta, "name": name}
    return {**files, SKILL_MD: compose_skill_md(meta, parsed.body).encode("utf-8")}


# ------------------------------------------------------------------ the CLIs' skills
@dataclass
class CliSkill:
    source: str  # claude_user · claude_project · agy_global · agy_project
    path: str
    name: str
    description: str
    project_id: str | None = None
    project_name: str = ""
    imported: bool = False  # the library has a skill with this same SKILL.md
    error: str = ""


def _folders(home: Path, projects: list[Project]) -> list[tuple[str, Path, Project | None]]:
    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    places: list[tuple[str, Path, Project | None]] = [
        ("claude_user", claude_home / "skills", None),
        ("agy_global", home / ".gemini" / "config" / "skills", None),
    ]
    for project in projects:
        root = Path(project.path)
        places.append(("claude_project", root / ".claude" / "skills", project))
        places.append(("agy_project", root / ".agents" / "skills", project))
    return places


def scan_cli_skills(db: Session, home: Path | None = None) -> list[CliSkill]:
    """Every skill the CLIs would load on their own: the person's (Claude and agy) and the ones
    in the projects' repositories (spikes S1, S2)."""
    home = home or Path.home()
    projects = list(db.scalars(select(Project).where(Project.workspace_id == DEFAULT_WORKSPACE)))
    known = {
        entry["sha256"]
        for manifest in db.scalars(
            select(SkillVersion.manifest)
            .join(Skill, Skill.current_version_id == SkillVersion.id)
            .where(Skill.workspace_id == DEFAULT_WORKSPACE)
        )
        for path, entry in manifest.items()
        if path == SKILL_MD
    }
    found: list[CliSkill] = []
    for source, folder, project in _folders(home, projects):
        if not folder.is_dir():
            continue
        for child in sorted(folder.iterdir()):
            skill_md = child / SKILL_MD
            if not child.is_dir() or not skill_md.is_file():
                continue
            item = CliSkill(
                source,
                str(child),
                child.name,
                "",
                project.id if project else None,
                project.name if project else "",
            )
            try:
                data = skill_md.read_bytes()
                parsed = parse_skill_md(data.decode("utf-8"))
                item.name, item.description = parsed.name, parsed.description
                item.imported = hashlib.sha256(data).hexdigest() in known
            except (OSError, UnicodeDecodeError, SkillError) as exc:
                item.error = getattr(exc, "message", str(exc))
            found.append(item)
    return found
