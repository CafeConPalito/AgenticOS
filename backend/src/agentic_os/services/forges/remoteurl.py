"""Which code host and project a remote URL points at."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentic_os.services.forges.base import Kind

# https://host/owner/repo(.git), ssh://git@host[:port]/owner/repo and git@host:owner/repo.git
HTTP = re.compile(r"^https?://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?/?$")
SSH_URL = re.compile(r"^ssh://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+?)(?:\.git)?/?$")
SCP = re.compile(r"^(?:[^@/]+@)?(?P<host>[^/:]+):(?P<path>[^/].*?)(?:\.git)?/?$")


@dataclass(frozen=True)
class Remote:
    host: str
    path: str  # owner/repo, or group/subgroup/repo on GitLab

    @property
    def owner(self) -> str:
        return self.path.rsplit("/", 1)[0]

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


def parse(url: str) -> Remote | None:
    for pattern in (HTTP, SSH_URL, SCP):
        match = pattern.match(url.strip())
        if match and "/" in match["path"]:
            return Remote(match["host"].lower(), match["path"])
    return None


def kind_of(host: str, override: str | None = None) -> Kind | None:
    """github.com and gitlab.com are told apart by name; any other host needs `override`."""
    if override in ("github", "gitlab"):
        return override  # type: ignore[return-value]
    if host == "github.com" or host.startswith("github."):
        return "github"
    if host == "gitlab.com" or host.startswith("gitlab."):
        return "gitlab"
    return None
