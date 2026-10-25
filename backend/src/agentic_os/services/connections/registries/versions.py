"""The exact version of an npm or PyPI package, and its weekly downloads (phase 18, block 8): a
connection is pinned to code the person has seen, and the official registry (which publishes no
usage figure) is ordered by npm downloads."""

from __future__ import annotations

from urllib.parse import quote

from agentic_os.services.connections.registries.base import Http, SourceError

NPM = "https://registry.npmjs.org"
NPM_DOWNLOADS = "https://api.npmjs.org/downloads/point/last-week"
PYPI = "https://pypi.org/pypi"


def latest_npm(http: Http, name: str) -> str:
    data = http.json(f"{NPM}/{quote(name, safe='@')}/latest")
    return str(data["version"])


def latest_pypi(http: Http, name: str) -> str:
    return str(http.json(f"{PYPI}/{quote(name)}/json")["info"]["version"])


def latest_version(http: Http, kind: str, package: str) -> str:
    """The version a registry has now for a package ('' for what has no versions)."""
    if kind == "npm":
        return latest_npm(http, package)
    if kind == "pypi":
        return latest_pypi(http, package)
    return ""


def npm_downloads(http: Http, name: str) -> int | None:
    try:
        return int(http.json(f"{NPM_DOWNLOADS}/{quote(name, safe='@')}").get("downloads", 0))
    except (SourceError, ValueError, KeyError, TypeError):
        return None
