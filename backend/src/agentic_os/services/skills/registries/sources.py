"""The public registries (phase 17, block 6; spike S3):

- **ranking**: the open daily rankings of LinklyAI/best-skills (CC BY 4.0), the «most used» list;
  its rows point to the source that can install each skill;
- **skills_sh**: the public routes its own CLI uses (search with installs, download, audit);
- **anthropic**: the official `anthropics/skills` repository;
- **skillsmp**: the largest index (search only; 50 requests a day without a key); off by default;
- **clawhub**: OpenClaw's registry; off by default (its security reports need a login).
"""

from __future__ import annotations

import csv
import io
import time

from agentic_os.services.skills.format import parse_skill_md
from agentic_os.services.skills.importer import read_zip
from agentic_os.services.skills.registries.base import (
    Card,
    Fetched,
    Source,
    SourceError,
    snapshot_hash,
)
from agentic_os.services.skills.registries.github import GitHub, Repo, card_from, parse_url
from agentic_os.services.skills.selection import tokens

RANKING_URL = (
    "https://raw.githubusercontent.com/LinklyAI/best-skills/main/data/latest/rankings/"
    "top-installs.csv"
)
RANKING_ATTRIBUTION = "Clasificación: Best Skills by Linkly AI (CC BY 4.0)"
SKILLS_SH = "https://skills.sh"
CLAWHUB = "https://clawhub.ai"
SKILLSMP = "https://skillsmp.com"
PAGE = 30
LONG = 6 * 3600  # lists that change once a day


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class _Memo:
    """A value kept for a while (the source's own lists)."""

    def __init__(self, seconds: float) -> None:
        self.seconds, self.value, self.at = seconds, None, 0.0

    def get(self, make):
        if self.value is None or time.monotonic() - self.at > self.seconds:
            self.value, self.at = make(), time.monotonic()
        return self.value


class RankingSource(Source):
    id = "ranking"
    title = "Más usadas"
    has_popular = True

    def __init__(self, http) -> None:
        super().__init__(http)
        self._rows = _Memo(LONG)

    def _cards(self) -> list[Card]:
        text = self.http.get(RANKING_URL).text
        cards: list[Card] = []
        for row in csv.DictReader(io.StringIO(text)):
            installs = _int(row.get("installs_skillssh")) or _int(row.get("downloads_clawhub"))
            name = row.get("skill") or ""
            if row.get("platform") == "skills.sh" and row.get("source_skillssh"):
                slug = (row.get("skill_key") or "").rsplit("/", 1)[-1] or name
                card = Card("skills_sh", f"{row['source_skillssh']}/{slug}", name)
            elif row.get("slug_clawhub"):
                card = Card("clawhub", row["slug_clawhub"], name)
            else:
                continue
            card.description = (row.get("description") or "").strip()
            card.author = row.get("vendor") or ""
            card.installs = installs
            card.category = row.get("category") or ""
            card.url = row.get("url") or ""
            cards.append(card)
        return cards

    def popular(self, page: int = 1) -> list[Card]:
        cards = self._rows.get(self._cards)
        return cards[(page - 1) * PAGE : page * PAGE]

    def search(self, query: str, page: int = 1) -> list[Card]:
        wanted = set(tokens(query))
        cards = self._rows.get(self._cards)
        hits = [c for c in cards if wanted & set(tokens(f"{c.name} {c.description}"))]
        return hits[(page - 1) * PAGE : page * PAGE]

    def fetch(self, ref: str) -> Fetched:
        raise SourceError(
            "not_found", "la clasificación no instala: lo hace la fuente de cada skill"
        )


class SkillsShSource(Source):
    id = "skills_sh"
    title = "skills.sh"

    def search(self, query: str, page: int = 1) -> list[Card]:
        if len(query.strip()) < 2:
            raise SourceError("needs_query", "escribe al menos dos letras")
        data = self.http.json(f"{SKILLS_SH}/api/search", params={"q": query, "limit": PAGE})
        cards = []
        for item in data.get("skills", []):
            ref = str(item.get("id") or "")
            card = Card(self.id, ref, str(item.get("name") or ref.rsplit("/", 1)[-1]))
            card.installs = _int(item.get("installs"))
            card.author = str(item.get("source") or "").split("/", 1)[0]
            card.url = f"{SKILLS_SH}/{ref}"
            cards.append(card)
        return cards

    def fetch(self, ref: str) -> Fetched:
        owner, repo, slug = ref.split("/", 2)
        data = self.http.json(f"{SKILLS_SH}/api/download/{owner}/{repo}/{slug}")
        files = {
            str(f["path"]): str(f.get("contents") or "").encode("utf-8")
            for f in data.get("files", [])
            if str(f.get("path")) != "metadata.json"
        }
        if "SKILL.md" not in files:
            raise SourceError("bad_skill", "la descarga no trae un SKILL.md")
        card = card_from(files, self.id, ref)
        card.author, card.url = owner, f"{SKILLS_SH}/{ref}"
        security = {}
        try:
            audit = self.http.json(
                "https://www.skills.sh/tele/audit",
                params={"source": f"{owner}/{repo}", "skills": slug},
            )
            security = audit.get(slug) or {}
        except SourceError:
            pass  # without the audit the skill can still be reviewed and installed
        header = parse_skill_md(files["SKILL.md"].decode("utf-8")).meta
        return Fetched(
            card,
            files,
            snapshot_hash(files),
            repo_url=f"https://github.com/{owner}/{repo}",
            path=slug,
            license=str(header.get("license") or ""),
            security={"skills_sh": security} if security else {},
        )


class AnthropicSource(Source):
    id = "anthropic"
    title = "Anthropic (oficiales)"
    has_popular = True
    repo = Repo("anthropics", "skills")

    def __init__(self, http) -> None:
        super().__init__(http)
        self._list = _Memo(LONG)

    def _cards(self) -> list[Card]:
        hub = GitHub(self.http)
        sha = hub.commit(self.repo)
        tree = hub.tree(self.repo, sha)
        cards = []
        for folder in GitHub.skill_folders(tree, "skills"):
            card = card_from(
                {"SKILL.md": hub.raw(self.repo, sha, f"{folder}/SKILL.md")}, self.id, folder
            )
            card.author, card.url = "anthropics", f"{self.repo.url}/tree/main/{folder}"
            cards.append(card)
        return cards

    def popular(self, page: int = 1) -> list[Card]:
        return self._list.get(self._cards)[(page - 1) * PAGE : page * PAGE]

    def search(self, query: str, page: int = 1) -> list[Card]:
        wanted = set(tokens(query))
        cards = self._list.get(self._cards)
        return [c for c in cards if wanted & set(tokens(f"{c.name} {c.description}"))]

    def fetch(self, ref: str) -> Fetched:
        return GitHub(self.http).fetch(self.repo, ref, None, self.id)

    def latest(self, ref: str) -> str:
        return GitHub(self.http).commit(self.repo)


class SkillsMpSource(Source):
    id = "skillsmp"
    title = "SkillsMP"
    default_enabled = False

    def __init__(self, http, key: str = "") -> None:
        super().__init__(http)
        self.key = key

    def search(self, query: str, page: int = 1) -> list[Card]:
        if len(query.strip()) < 2:
            raise SourceError("needs_query", "escribe al menos dos letras")
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        data = self.http.json(
            f"{SKILLSMP}/api/v1/skills/search",
            params={"q": query, "limit": PAGE, "page": page},
            headers=headers,
        )
        cards = []
        for item in (data.get("data") or {}).get("skills", []):
            url = str(item.get("githubUrl") or "")
            card = Card(self.id, url, str(item.get("name") or ""))
            card.description = str(item.get("description") or "")
            card.author = str(item.get("author") or "")
            card.stars = _int(item.get("stars"))  # the repository's (S3), shown as such
            card.url = str(item.get("skillUrl") or url)
            updated = _int(item.get("updatedAt"))
            card.updated_at = time.strftime("%Y-%m-%d", time.gmtime(updated)) if updated else None
            cards.append(card)
        return cards

    def fetch(self, ref: str) -> Fetched:
        repo, branch, folder = parse_url(ref)
        fetched = GitHub(self.http).fetch(repo, folder, branch, self.id)
        fetched.card.ref = ref
        return fetched

    def latest(self, ref: str) -> str:
        repo, branch, _ = parse_url(ref)
        return GitHub(self.http).commit(repo, branch)


class ClawHubSource(Source):
    id = "clawhub"
    title = "ClawHub"
    default_enabled = False
    has_popular = True

    @staticmethod
    def _card(item: dict) -> Card:
        skill = (item.get("native") or {}).get("skill") or item
        owner = item.get("ownerHandle") or (item.get("native") or {}).get("ownerHandle") or ""
        slug = skill.get("slug") or item.get("slug") or ""
        card = Card(
            "clawhub",
            f"{owner}/{slug}",
            str(item.get("displayName") or skill.get("displayName") or slug),
        )
        card.description = " ".join(str(skill.get("summary") or item.get("summary") or "").split())
        card.author = owner
        stats = skill.get("stats") or item.get("stats") or {}
        card.installs = _int(stats.get("downloads"))
        card.stars = _int(stats.get("stars"))
        card.url = f"{CLAWHUB}/{owner}/skills/{slug}"
        return card

    def popular(self, page: int = 1) -> list[Card]:
        data = self.http.json(
            f"{CLAWHUB}/api/v1/skills", params={"limit": PAGE, "sort": "downloads"}
        )
        return [self._card(i) for i in data.get("items", [])]

    def search(self, query: str, page: int = 1) -> list[Card]:
        data = self.http.json(f"{CLAWHUB}/api/v1/search", params={"q": query, "limit": PAGE})
        return [self._card(i) for i in data.get("results", [])]

    def fetch(self, ref: str) -> Fetched:
        owner, slug = ref.split("/", 1)
        detail = self.http.json(f"{CLAWHUB}/api/v1/skills/{slug}", params={"ownerHandle": owner})
        archive = self.http.get(
            f"{CLAWHUB}/api/v1/download", params={"slug": slug, "ownerHandle": owner}
        ).content
        files = {p: d for p, d in read_zip(archive).items() if p != "_meta.json"}
        version = str((detail.get("latestVersion") or {}).get("version") or snapshot_hash(files))
        card = self._card({**(detail.get("skill") or {}), "ownerHandle": owner})
        suspicious = (detail.get("skill") or {}).get("isSuspicious")
        return Fetched(
            card,
            files,
            version,
            repo_url=card.url,
            path=slug,
            license="MIT-0",  # everything published on ClawHub (its documentation)
            security={"clawhub": {"suspicious": bool(suspicious)}}
            if suspicious is not None
            else {},
        )

    def latest(self, ref: str) -> str:
        owner, slug = ref.split("/", 1)
        detail = self.http.json(f"{CLAWHUB}/api/v1/skills/{slug}", params={"ownerHandle": owner})
        return str((detail.get("latestVersion") or {}).get("version") or "")
