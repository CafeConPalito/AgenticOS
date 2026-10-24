"""Skills that live in a GitHub repository (spike S3): the tree in one request, the files from
`raw.githubusercontent.com` (no API quota) at a fixed commit."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from agentic_os.services.skills.format import MAX_FILES, MAX_TOTAL_BYTES, parse_skill_md
from agentic_os.services.skills.registries.base import (
    Card,
    Fetched,
    Http,
    Source,
    SourceError,
)

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
URL = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/(?P<ref>[^/]+)(?:/(?P<path>.*?))?)?/?$"
)


@dataclass
class Repo:
    owner: str
    repo: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


def parse_url(url: str) -> tuple[Repo, str | None, str]:
    """(repository, branch or commit or None, folder inside it)."""
    match = URL.match(url.strip())
    if not match:
        raise SourceError("not_found", "no es la dirección de un repositorio de GitHub")
    path = (match.group("path") or "").strip("/")
    if path.lower().endswith("skill.md"):
        path = posixpath.dirname(path)
    return Repo(match.group("owner"), match.group("repo")), match.group("ref"), path


class GitHub:
    def __init__(self, http: Http) -> None:
        self.http = http

    def commit(self, repo: Repo, ref: str | None = None) -> str:
        data = self.http.json(f"{API}/repos/{repo.owner}/{repo.repo}/commits/{ref or 'HEAD'}")
        return str(data["sha"])

    def tree(self, repo: Repo, sha: str) -> list[dict]:
        data = self.http.json(f"{API}/repos/{repo.owner}/{repo.repo}/git/trees/{sha}?recursive=1")
        return [e for e in data.get("tree", []) if e.get("type") == "blob"]

    def raw(self, repo: Repo, sha: str, path: str) -> bytes:
        return self.http.get(f"{RAW}/{repo.owner}/{repo.repo}/{sha}/{path}").content

    @staticmethod
    def skill_folders(tree: list[dict], under: str = "") -> list[str]:
        prefix = f"{under}/" if under else ""
        return sorted(
            posixpath.dirname(e["path"])
            for e in tree
            if e["path"].startswith(prefix) and posixpath.basename(e["path"]) == "SKILL.md"
        )

    def files(self, repo: Repo, sha: str, folder: str, tree: list[dict]) -> dict[str, bytes]:
        prefix = f"{folder}/" if folder else ""
        entries = [e for e in tree if e["path"].startswith(prefix)]
        nested = {
            posixpath.dirname(e["path"])
            for e in entries
            if posixpath.basename(e["path"]) == "SKILL.md"
            and posixpath.dirname(e["path"]) != folder
        }
        # A folder inside the skill with its own SKILL.md is another skill: not part of this one.
        entries = [e for e in entries if not any(e["path"].startswith(f"{n}/") for n in nested)]
        if (
            len(entries) > MAX_FILES
            or sum(int(e.get("size") or 0) for e in entries) > MAX_TOTAL_BYTES
        ):
            raise SourceError("bad_skill", "la skill es demasiado grande para instalarla")
        return {e["path"][len(prefix) :]: self.raw(repo, sha, e["path"]) for e in entries}

    def fetch(self, repo: Repo, folder: str, ref: str | None, source: str) -> Fetched:
        sha = self.commit(repo, ref)
        tree = self.tree(repo, sha)
        files = self.files(repo, sha, folder, tree)
        if "SKILL.md" not in files:
            raise SourceError("not_found", "esa carpeta no tiene un SKILL.md")
        card = card_from(files, source, f"{repo.owner}/{repo.repo}/{folder}".rstrip("/"))
        card.author, card.url = repo.owner, f"{repo.url}/tree/{sha}/{folder}".rstrip("/")
        return Fetched(
            card,
            files,
            sha,
            repo_url=repo.url,
            path=folder,
            license=str(_header(files).get("license") or ""),
        )


def _header(files: dict[str, bytes]) -> dict:
    try:
        return parse_skill_md(files["SKILL.md"].decode("utf-8")).meta
    except Exception:
        return {}


def card_from(files: dict[str, bytes], source: str, ref: str) -> Card:
    meta = _header(files)
    name = str(meta.get("name") or posixpath.basename(ref))
    return Card(source, ref, name, " ".join(str(meta.get("description") or "").split()))


class GitHubUrlSource(Source):
    """Any repository: the person pastes its address and picks one of its skills."""

    id = "github"
    title = "Repositorio de GitHub"

    def search(self, query: str, page: int = 1) -> list[Card]:
        repo, ref, under = parse_url(query)
        hub = GitHub(self.http)
        sha = hub.commit(repo, ref)
        tree = hub.tree(repo, sha)
        cards = []
        for folder in GitHub.skill_folders(tree, under)[:100]:
            data = hub.raw(repo, sha, f"{folder}/SKILL.md" if folder else "SKILL.md")
            card = card_from({"SKILL.md": data}, self.id, f"{repo.owner}/{repo.repo}/{folder}")
            card.author, card.url = repo.owner, f"{repo.url}/tree/{sha}/{folder}"
            cards.append(card)
        return cards

    def fetch(self, ref: str) -> Fetched:
        owner, repo, *rest = ref.split("/")
        return GitHub(self.http).fetch(Repo(owner, repo), "/".join(rest), None, self.id)

    def latest(self, ref: str) -> str:
        owner, repo, *_ = ref.split("/")
        return GitHub(self.http).commit(Repo(owner, repo))
