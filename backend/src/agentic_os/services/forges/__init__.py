"""Pull requests on GitHub and GitLab (phase 12, ADR 0018)."""

from __future__ import annotations

import httpx

from agentic_os.models import ProjectRepo
from agentic_os.services.forges import remoteurl
from agentic_os.services.forges.base import Forge
from agentic_os.services.forges.github import GitHub
from agentic_os.services.forges.gitlab import GitLab
from agentic_os.services.forges.http import new_client
from agentic_os.services.gitx import credentials, remote
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo


def remote_of(repo: Repo, branch: str | None = None) -> tuple[str, str]:
    """The remote's name and URL the repository's pull requests go through."""
    name = remote.default_remote(repo, branch)
    for item in remote.remotes(repo):
        if item.name == name:
            return name, item.fetch_url
    raise GitxError("no_remote", "this repository has no remote to talk to", status=422)


def forge_for(
    row: ProjectRepo,
    repo: Repo,
    *,
    client: httpx.Client | None = None,
    interactive: bool = False,
) -> Forge:
    """The code host of the repository's remote, with the token git has for it."""
    _name, url = remote_of(repo)
    parsed = remoteurl.parse(url)
    kind = remoteurl.kind_of(parsed.host, row.forge) if parsed else None
    if parsed is None or kind is None:
        raise GitxError(
            "forge_unknown",
            "this remote is not on GitHub or GitLab: choose which one it is in its settings",
            status=422,
        )
    token = credentials.token_for(parsed.host, interactive=interactive)
    if token is None:
        raise GitxError("auth_failed", f"git has no token for {parsed.host}", status=401)
    cls = GitHub if kind == "github" else GitLab
    return cls(client or new_client(), parsed.host, parsed.path, token)
