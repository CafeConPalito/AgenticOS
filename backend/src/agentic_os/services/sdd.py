"""Spec-driven development (phase 24, ADR 0030): which SDD format a project already uses.

The requirements stage decides whether a task goes with SDD (`tasks.work_mode`); to follow the
project's own format it is told what this finds. The marks come from spike S3; the agent reads
the rest of the repository to follow the format in detail. Without any, the app's own format is
`specs/NNN-name/` with `spec.md`, `plan.md` and `tasks.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_FORMAT = "specs/NNN-nombre/ con spec.md, plan.md y tasks.md (NNN: el siguiente número libre)"


@dataclass(frozen=True)
class SddFormat:
    name: str  # what it is called, for the agent and the person
    where: str  # where its specs live, relative to the project


def _any(folder: Path, pattern: str) -> bool:
    return folder.is_dir() and next(folder.glob(pattern), None) is not None


def detect(project_path: str | Path) -> SddFormat | None:
    """The SDD format of the project in `project_path`, or None if it uses none (or the folder
    is not there). The order matters: tool marks first, then plain spec folders."""
    root = Path(project_path)
    if not root.is_dir():
        return None
    if (root / ".specify").is_dir():
        return SddFormat("spec-kit", "specs/NNN-nombre/ (spec.md, plan.md, tasks.md); .specify/")
    if (root / ".kiro" / "specs").is_dir():
        return SddFormat("Kiro", ".kiro/specs/<nombre>/ (requirements.md, design.md, tasks.md)")
    if (root / "openspec").is_dir():
        return SddFormat(
            "OpenSpec",
            "openspec/specs/ y openspec/changes/<id>/ (proposal.md, design.md, tasks.md)",
        )
    if _any(root / "docs" / "phases", "*/spec.md"):
        return SddFormat("specs por fase", "docs/phases/NN-nombre/ (spec.md, plan.md)")
    if _any(root / "specs", "*/spec.md"):
        return SddFormat("specs", "specs/<nombre>/spec.md")
    return None


def describe(found: SddFormat | None) -> str:
    """One line for the requirements stage's context."""
    if found is None:
        return (
            f"El proyecto no usa SDD. Si la tarea lo necesita, usa el formato de la app: "
            f"{APP_FORMAT}."
        )
    return f"El proyecto usa SDD ({found.name}): {found.where}. Sigue ese formato."
