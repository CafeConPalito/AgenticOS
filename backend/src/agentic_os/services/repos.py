"""The git repositories of a project: finding them, keeping the list, linking outside ones
(phase 12, ADR 0016).

A project folder may be a repository, hold several (`backend/`, `frontend/`…) or none. They are
found by walking the folder down to the project's `repo_scan_depth`. Repositories outside the
folder are linked by hand. Submodules belong to their parent repository and are not listed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import Project, ProjectRepo
from agentic_os.services import git, paths

log = structlog.get_logger()

# Folders never walked into: dependencies and build output (a real repo is never in there).
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        "target",
        ".tox",
        ".next",
        ".cache",
        ".gradle",
    }
)
MAX_FOUND = 200  # a folder with more repositories than this is not a project


@dataclass(frozen=True)
class Found:
    path: str
    rel_path: str  # "" for the project folder itself


def is_repo_root(folder: Path) -> bool:
    """A `.git` folder, or the `.git` file of a worktree or submodule."""
    return (folder / ".git").exists()


def _submodule_paths(repo: Path) -> set[str]:
    """Relative paths (POSIX) of the submodules a repository declares."""
    if not (repo / ".gitmodules").is_file():
        return set()
    try:
        out = git.run(
            str(repo),
            "config",
            "--file",
            ".gitmodules",
            "--get-regexp",
            r"^submodule\..*\.path$",
            timeout=10,
        )
    except git.GitError:
        return set()
    return {line.split(maxsplit=1)[1].strip() for line in out.splitlines() if " " in line}


def _ignored(repo: Path, candidates: list[Path]) -> set[Path]:
    """The candidate folders the repository ignores (`node_modules/` without being listed…)."""
    if not candidates:
        return set()
    names = [str(c.relative_to(repo)) for c in candidates]
    try:
        out = git.run(
            str(repo),
            "check-ignore",
            "--stdin",
            "-z",
            timeout=20,
            input="\0".join(names) + "\0",
        )
    except git.GitError:  # exit code 1: none is ignored
        return set()
    ignored = {n for n in out.split("\0") if n}
    return {c for c, n in zip(candidates, names, strict=True) if n in ignored}


def scan(folder: str, depth: int = 3) -> list[Found]:
    """Repositories in `folder` and down to `depth` levels below it, the folder first."""
    root = Path(folder)
    if not root.is_dir():
        return []
    found: list[Found] = []
    # (folder, levels below the root, the repo it sits in and that repo's own submodules)
    pending: list[tuple[Path, int, Path | None, set[str]]] = [(root, 0, None, set())]
    while pending and len(found) < MAX_FOUND:
        current, level, parent_repo, parent_subs = pending.pop(0)
        repo, subs = parent_repo, parent_subs
        if is_repo_root(current):
            found.append(Found(str(current), _rel(root, current)))
            repo, subs = current, _submodule_paths(current)
        if level >= depth:
            continue
        try:
            children = sorted(
                (c for c in current.iterdir() if c.is_dir() and c.name not in SKIP_DIRS),
                key=lambda c: c.name.lower(),
            )
        except OSError:
            continue
        if repo is not None:
            children = [c for c in children if c.relative_to(repo).as_posix() not in subs]
            ignored = _ignored(repo, children)
            children = [c for c in children if c not in ignored]
        pending.extend((c, level + 1, repo, subs) for c in children)
    return found


def _rel(root: Path, folder: Path) -> str:
    return "" if folder == root else folder.relative_to(root).as_posix()


def _display_name(project: Project, found: Found) -> str:
    name = Path(found.path).name if found.rel_path else Path(project.path).name
    return (name or project.name)[:80]


def _current_branch(path: str) -> str | None:
    info = git.detect(path)
    return info.branch if info and info.is_repo else None


def enclosing_repo(folder: str) -> str | None:
    """The repository a folder is a subfolder of (None when it is a repo root or in none)."""
    try:
        top = git.run(folder, "rev-parse", "--show-toplevel", timeout=10).strip()
    except git.GitError:
        return None
    if not top:
        return None
    resolved, key = paths.normalize(top)
    return None if key == paths.normalize(folder)[1] else resolved


def sync(db: Session, project: Project) -> list[ProjectRepo]:
    """Brings the project's repository list up to date with the disk: new repositories are
    added (with the current branch as their base), those that disappeared are marked `missing`
    (never deleted: the user removes them), linked ones are only checked. Returns the list."""
    existing = {
        r.path_key: r
        for r in db.scalars(select(ProjectRepo).where(ProjectRepo.project_id == project.id))
    }
    seen: set[str] = set()
    position = max((r.position for r in existing.values()), default=-1) + 1
    for item in scan(project.path, project.repo_scan_depth):
        path, key = paths.normalize(item.path)
        seen.add(key)
        repo = existing.get(key)
        if repo is None:
            base = project.base_branch if not item.rel_path else None
            repo = ProjectRepo(
                workspace_id=project.workspace_id,
                project_id=project.id,
                path=path,
                path_key=key,
                rel_path=item.rel_path,
                name=_display_name(project, item),
                base_branch=base or _current_branch(path),
                linked=False,
                position=position,
            )
            position += 1
            db.add(repo)
            existing[key] = repo
        else:
            repo.rel_path = item.rel_path
            repo.linked = False
        repo.missing = False
    parent = None if seen else enclosing_repo(project.path)
    if parent is not None:  # the project is a subfolder of a repository: that one is its repo
        key = paths.normalize(parent)[1]
        seen.add(key)
        repo = existing.get(key)
        if repo is None:
            repo = ProjectRepo(
                workspace_id=project.workspace_id,
                project_id=project.id,
                path=parent,
                path_key=key,
                rel_path=None,
                name=Path(parent).name[:80],
                base_branch=project.base_branch or _current_branch(parent),
                linked=True,
                position=position,
            )
            db.add(repo)
            existing[key] = repo
        repo.missing = False
    for key, repo in existing.items():
        if key in seen:
            continue
        if repo.linked or repo.rel_path is None:
            repo.missing = not (Path(repo.path).is_dir() and is_repo_root(Path(repo.path)))
        else:
            repo.missing = True
    db.flush()
    return ordered(db, project)


def ordered(db: Session, project: Project) -> list[ProjectRepo]:
    return list(
        db.scalars(
            select(ProjectRepo)
            .where(ProjectRepo.project_id == project.id)
            .order_by(ProjectRepo.position, ProjectRepo.name)
        )
    )


def ensure(db: Session, project: Project) -> list[ProjectRepo]:
    """The project's repositories; a project nobody has looked at yet (no rows) is scanned."""
    count = db.scalar(
        select(func.count()).select_from(ProjectRepo).where(ProjectRepo.project_id == project.id)
    )
    return sync(db, project) if not count else ordered(db, project)


def active(db: Session, project: Project) -> list[ProjectRepo]:
    """Repositories tasks work in: present and taking part."""
    return [r for r in ensure(db, project) if r.participates and not r.missing]


def base_of(project: Project, repo: ProjectRepo) -> str | None:
    """The branch task branches start from in this repository."""
    return repo.base_branch or project.base_branch


def link(db: Session, project: Project, path: str, name: str | None = None) -> ProjectRepo:
    """Adds a repository by hand (outside the project folder, or deeper than the scan goes)."""
    resolved, key = paths.normalize(path)
    folder = Path(resolved)
    if not folder.is_dir() or not is_repo_root(folder):
        raise ApiError(422, "not_a_repository", "the folder is not a git repository root", "path")
    if db.scalar(
        select(ProjectRepo.id).where(
            ProjectRepo.project_id == project.id, ProjectRepo.path_key == key
        )
    ):
        raise ApiError(409, "repo_exists", "the project already has this repository", "path")
    project_key = paths.normalize(project.path)[1]
    inside = key == project_key or key.startswith(project_key.rstrip("\\/") + os.sep)
    position = (
        db.scalar(
            select(func.max(ProjectRepo.position)).where(ProjectRepo.project_id == project.id)
        )
        or 0
    ) + 1
    repo = ProjectRepo(
        workspace_id=project.workspace_id,
        project_id=project.id,
        path=resolved,
        path_key=key,
        rel_path=_rel(Path(project.path), folder) if inside else None,
        name=(name or folder.name)[:80],
        base_branch=_current_branch(resolved),
        linked=not inside,
        position=position,
    )
    db.add(repo)
    db.flush()
    return repo


def nested_paths(repos: list[ProjectRepo], repo: ProjectRepo) -> list[str]:
    """Paths (relative to `repo`, POSIX) of the other repositories that sit inside it: its
    snapshots must leave them out, or git would take them for submodules."""
    base = Path(repo.path)
    out: list[str] = []
    for other in repos:
        if other.id == repo.id or other.missing:
            continue
        try:
            rel = Path(other.path).relative_to(base)
        except ValueError:
            continue
        if str(rel) != ".":
            out.append(rel.as_posix())
    return sorted(out)
