"""Managing remotes and the forced push (phase 12, ADR 0017). Listing remotes and the plain
fetch/pull/push live in `remote.py`."""

from __future__ import annotations

import re

from pydantic import BaseModel

from agentic_os.services.gitx import remote
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")


def _check_name(name: str) -> str:
    clean = name.strip()
    if not NAME.match(clean):
        raise GitxError("invalid_remote", f"{name!r} is not a valid remote name", status=422)
    return clean


def _check_url(url: str) -> str:
    clean = url.strip()
    # Whatever git accepts as a location, but nothing that looks like an option or a command.
    if not clean or clean.startswith("-") or "\n" in clean or "\0" in clean:
        raise GitxError("invalid_url", "that is not a valid address", status=422)
    if clean.lower().startswith("ext::"):  # `ext::` runs arbitrary commands
        raise GitxError("invalid_url", "that kind of address is not allowed", status=422)
    return clean


def add(repo: Repo, name: str, url: str) -> None:
    with repo.write():
        repo.run("remote", "add", _check_name(name), _check_url(url))


def set_url(repo: Repo, name: str, url: str) -> None:
    with repo.write():
        repo.run("remote", "set-url", _check_name(name), _check_url(url))


def rename(repo: Repo, old: str, new: str) -> None:
    with repo.write():
        repo.run("remote", "rename", _check_name(old), _check_name(new))


def remove(repo: Repo, name: str) -> None:
    with repo.write():
        repo.run("remote", "remove", _check_name(name))


class Reachability(BaseModel):
    ok: bool
    error_code: str | None = None
    message: str = ""
    branches: int = 0


def test_connection(repo: Repo, name: str) -> Reachability:
    """Can git talk to the remote with the credentials it has? Never waits for a login."""
    try:
        out = repo.run("ls-remote", "--heads", _check_name(name), timeout=30)
    except GitxError as error:
        return Reachability(ok=False, error_code=error.code, message=error.message)
    return Reachability(ok=True, branches=len([line for line in out.splitlines() if line.strip()]))


def would_overwrite(repo: Repo, name: str, branch: str) -> list[str]:
    """Subjects of the commits on the remote's copy of `branch` that a forced push would
    destroy (those the local branch does not have). Reads what the last fetch knows."""
    ref = f"refs/remotes/{name}/{branch}"
    if repo.attempt("rev-parse", "--verify", "-q", ref) is None:
        return []
    out = repo.run("log", "--format=%h %s", ref, "--not", f"refs/heads/{branch}", "-n", "50")
    return [line for line in out.splitlines() if line.strip()]


def force_push_args(
    repo: Repo, remote_name: str | None = None, branch: str | None = None
) -> list[str]:
    """`push --force-with-lease`, pinned to the commit the remote branch was at when last seen:
    if someone pushed since, git refuses instead of overwriting their work."""
    name = branch or (repo.attempt("branch", "--show-current") or "").strip()
    if not name:
        raise GitxError("detached_head", "there is no branch to push", status=422)
    target = remote_name or remote.default_remote(repo, name)
    seen = repo.attempt("rev-parse", "--verify", "-q", f"refs/remotes/{target}/{name}")
    lease = f"--force-with-lease={name}:{seen.strip()}" if seen else f"--force-with-lease={name}"
    return ["push", "--progress", lease, target, name]
