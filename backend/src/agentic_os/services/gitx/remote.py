"""Remotes and the arguments of fetch, pull and push (phase 12, ADR 0017).

Those three run as jobs (`jobs.JobManager`); this only decides what to ask git.
"""

from __future__ import annotations

from typing import Literal

from agentic_os.schemas.git import RemoteInfo
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo

PullMode = Literal["ff_only", "merge", "rebase"]


def remotes(repo: Repo) -> list[RemoteInfo]:
    found: dict[str, dict[str, str]] = {}
    for line in repo.run("remote", "-v").splitlines():
        name, _, rest = line.partition("\t")
        url, _, kind = rest.rpartition(" ")
        found.setdefault(name, {})[kind.strip("()")] = url
    return [
        RemoteInfo(name=name, fetch_url=urls.get("fetch", ""), push_url=urls.get("push", ""))
        for name, urls in sorted(found.items())
    ]


def default_remote(repo: Repo, branch: str | None = None) -> str:
    """The remote of the branch's upstream, else `origin`, else the only one there is."""
    if branch:
        configured = repo.attempt("config", "--get", f"branch.{branch}.remote")
        if configured and configured.strip() not in ("", "."):
            return configured.strip()
    names = [r.name for r in remotes(repo)]
    if "origin" in names:
        return "origin"
    if len(names) == 1:
        return names[0]
    raise GitxError("no_remote", "this repository has no remote to talk to", status=422)


def fetch_args(remote: str | None = None, prune: bool = True) -> list[str]:
    return ["fetch", "--progress", *(["--prune"] if prune else []), remote or "--all"]


def pull_args(
    mode: PullMode = "ff_only", remote: str | None = None, branch: str | None = None
) -> list[str]:
    flag = {"ff_only": "--ff-only", "merge": "--no-rebase", "rebase": "--rebase"}[mode]
    return [
        "pull",
        "--progress",
        flag,
        *([remote] if remote else []),
        *([branch] if branch else []),
    ]


def push_args(
    repo: Repo, remote: str | None = None, branch: str | None = None, set_upstream: bool = False
) -> list[str]:
    """Pushes `branch` (the current one by default). A branch with no upstream is pushed with
    `-u`, so it gets one. Never forced."""
    name = branch or (repo.attempt("branch", "--show-current") or "").strip()
    if not name:
        raise GitxError("detached_head", "there is no branch to push", status=422)
    target = remote or default_remote(repo, name)
    has_upstream = bool((repo.attempt("config", "--get", f"branch.{name}.remote") or "").strip())
    flags = ["-u"] if set_upstream or not has_upstream else []
    return ["push", "--progress", *flags, target, name]
