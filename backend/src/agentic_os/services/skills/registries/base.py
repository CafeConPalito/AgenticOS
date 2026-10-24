"""What every public skill registry offers (phase 17, block 6; spike S3), and the HTTP client they
share: short timeouts, a size cap and the failures turned into a code the UI can show per source
(a source that fails never breaks the others, CA18)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

TIMEOUT = 8.0
MAX_DOWNLOAD = 12 * 1024 * 1024
USER_AGENT = "agentic-os"


@dataclass
class Card:
    """A skill as a registry lists it."""

    source: str  # the module that can fetch it
    ref: str  # its id in that source
    name: str
    description: str = ""
    author: str = ""
    installs: int | None = None
    stars: int | None = None
    updated_at: str | None = None  # ISO date, when the source says
    category: str = ""
    url: str = ""  # its page (registry or repository)


@dataclass
class Fetched:
    """A skill downloaded at one fixed revision: what the person reviews is what gets installed."""

    card: Card
    files: dict[str, bytes]
    revision: str  # a commit, a hash of the files or a version
    repo_url: str = ""
    path: str = ""
    license: str = ""
    security: dict = field(default_factory=dict)


class SourceError(Exception):
    """offline · unavailable · rate_limited · not_found · bad_skill · needs_query"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class Http:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        github_token: Callable[[], str | None] | None = None,
    ) -> None:
        self.client = httpx.Client(
            transport=transport,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.github_token = github_token

    def get(self, url: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if url.startswith("https://api.github.com") and self.github_token:
            token = self.github_token()
            if token:
                headers.setdefault("Authorization", f"Bearer {token}")
        try:
            response = self.client.get(url, headers=headers, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise SourceError("offline", "sin conexión con el registro") from exc
        except httpx.HTTPError as exc:
            raise SourceError("unavailable", f"el registro no responde ({exc})") from exc
        if response.status_code in (403, 429) and (
            "rate limit" in response.text.lower() or response.status_code == 429
        ):
            raise SourceError("rate_limited", "el registro limita las peticiones: prueba más tarde")
        if response.status_code == 404:
            raise SourceError("not_found", "no está en el registro")
        if response.status_code >= 400:
            raise SourceError("unavailable", f"el registro respondió {response.status_code}")
        if len(response.content) > MAX_DOWNLOAD:
            raise SourceError("bad_skill", "la descarga es demasiado grande")
        return response

    def json(self, url: str, **kwargs):
        try:
            return self.get(url, **kwargs).json()
        except ValueError as exc:
            raise SourceError("unavailable", "el registro respondió algo que no es JSON") from exc

    def close(self) -> None:
        self.client.close()


def snapshot_hash(files: dict[str, bytes]) -> str:
    """The revision of a source that has no commits: the hash of its files, as the skills.sh CLI
    computes it (sorted by path, path then contents)."""
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode())
        digest.update(files[path])
    return digest.hexdigest()


class Source(ABC):
    id: str
    title: str
    default_enabled: bool = True
    has_popular: bool = False  # it can list without a query

    def __init__(self, http: Http) -> None:
        self.http = http

    def popular(self, page: int = 1) -> list[Card]:
        return []

    @abstractmethod
    def search(self, query: str, page: int = 1) -> list[Card]: ...

    @abstractmethod
    def fetch(self, ref: str) -> Fetched: ...

    def latest(self, ref: str) -> str:
        """The revision the source has now (to offer an update)."""
        return self.fetch(ref).revision
