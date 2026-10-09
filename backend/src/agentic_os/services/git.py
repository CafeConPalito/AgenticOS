import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

TIMEOUT = 5


class GitInfo(BaseModel):
    is_repo: bool
    branch: str | None = None
    dirty: bool = False


def _git(path: str, *args: str) -> subprocess.CompletedProcess[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        return subprocess.run(
            [git, "-C", path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect(path: str) -> GitInfo | None:
    """Git state of a folder, computed on the fly. None when git is unavailable."""
    if not Path(path).is_dir():
        return GitInfo(is_repo=False)
    inside = _git(path, "rev-parse", "--is-inside-work-tree")
    if inside is None:
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return GitInfo(is_repo=False)
    # symbolic-ref also works in a repo without commits; detached HEAD falls back to the sha.
    branch = _git(path, "symbolic-ref", "--short", "-q", "HEAD")
    name = branch.stdout.strip() if branch and branch.returncode == 0 else None
    if not name:
        head = _git(path, "rev-parse", "--short", "HEAD")
        name = head.stdout.strip() if head and head.returncode == 0 else None
    status = _git(path, "status", "--porcelain")
    dirty = bool(status and status.returncode == 0 and status.stdout.strip())
    return GitInfo(is_repo=True, branch=name, dirty=dirty)
