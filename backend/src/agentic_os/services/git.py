import shutil
import subprocess
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from agentic_os.services import proc

TIMEOUT = 5


class GitInfo(BaseModel):
    is_repo: bool
    branch: str | None = None
    dirty: bool = False


@cache
def _git_executable() -> str | None:
    return shutil.which("git")


def _git(path: str, *args: str) -> subprocess.CompletedProcess[str] | None:
    git = _git_executable()
    if git is None:
        return None
    try:
        return proc.run([git, "-C", path, *args], TIMEOUT)
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


class GitError(RuntimeError):
    pass


def run(path: str, *args: str, timeout: float = 60, config: tuple[str, ...] = ()) -> str:
    """Runs a git command that must succeed (worktrees, commits); returns its stdout."""
    git = _git_executable()
    if git is None:
        raise GitError("git is not installed")
    command = [git, *(arg for pair in config for arg in ("-c", pair)), "-C", path, *args]
    try:
        result = proc.run(command, timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitError(f"git {args[0]}: {error}") from error
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise GitError(f"git {args[0]}: {message[-1] if message else result.returncode}")
    return result.stdout


def branch_exists(path: str, branch: str) -> bool:
    found = _git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    return bool(found and found.returncode == 0)
