"""The registry explorer (phase 17, block 6): «most used» and search across the enabled sources,
a preview downloaded at one fixed revision (what the person reviews is what gets installed),
installing it at a level, and the updates of what was installed (never applied by themselves)."""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Skill, SkillOrigin, SkillOriginKind, SkillVersion, VersionAuthor
from agentic_os.services.skills import config as skills_config
from agentic_os.services.skills import history
from agentic_os.services.skills.errors import SkillError
from agentic_os.services.skills.format import check_files, normalize_path
from agentic_os.services.skills.importer import renamed
from agentic_os.services.skills.library import Author, SkillLibrary
from agentic_os.services.skills.registries.base import Card, Fetched, Http, Source, SourceError
from agentic_os.services.skills.registries.github import GitHubUrlSource
from agentic_os.services.skills.registries.sources import (
    RANKING_ATTRIBUTION,
    AnthropicSource,
    ClawHubSource,
    RankingSource,
    SkillsMpSource,
    SkillsShSource,
)

log = structlog.get_logger()
CACHE_SECONDS = 600  # searches and lists (spec D)
PREVIEW_SECONDS = 3600
DAY = 24 * 3600
SOURCES: dict[str, type[Source]] = {
    s.id: s
    for s in (
        RankingSource,
        SkillsShSource,
        AnthropicSource,
        SkillsMpSource,
        ClawHubSource,
        GitHubUrlSource,
    )
}
SWITCHABLE = ("skills_sh", "anthropic", "skillsmp", "clawhub")  # ranking and github: always


@dataclass
class Listing:
    cards: list[Card] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source → code
    attribution: str = ""


@dataclass
class Preview:
    id: str
    fetched: Fetched
    executables: list[str]
    name: str


def enabled(db: Session) -> dict[str, bool]:
    stored = skills_config.load(db).registries
    return {s: bool(stored.get(s, SOURCES[s].default_enabled)) for s in SWITCHABLE}


class RegistryService:
    def __init__(
        self,
        data_dir: Path,
        library: SkillLibrary,
        transport: httpx.BaseTransport | None = None,
        github_token: Callable[[], str | None] | None = None,
    ) -> None:
        self.http = Http(transport, github_token)
        self.library = library
        self.previews = Path(data_dir) / "skills" / "previews"
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._sources: dict[str, Source] = {}
        self._stop = threading.Event()

    # ----------------------------------------------------------------- sources
    def source(self, db: Session, source_id: str) -> Source:
        if source_id not in SOURCES:
            raise NotFound("registry")
        key = skills_config.load(db).skillsmp_key if source_id == "skillsmp" else ""
        cached = self._sources.get(source_id)
        if cached is None or getattr(cached, "key", "") != key:
            cls = SOURCES[source_id]
            cached = cls(self.http, key) if source_id == "skillsmp" else cls(self.http)
            self._sources[source_id] = cached
        return cached

    def status(self, db: Session) -> list[dict]:
        on = enabled(db)
        return [
            {
                "id": s.id,
                "title": s.title,
                "enabled": on.get(s.id, True),
                "switchable": s.id in SWITCHABLE,
                "default_enabled": s.default_enabled,
                "has_popular": s.has_popular,
            }
            for s in SOURCES.values()
        ]

    def _cached(self, key: tuple, make: Callable[[], list[Card]]) -> list[Card]:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]  # type: ignore[return-value]
        value = make()
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    def _gather(
        self, db: Session, ids: list[str], call: Callable[[Source], list[Card]], key
    ) -> Listing:
        listing = Listing()
        seen: set[tuple[str, str]] = set()
        on = enabled(db)
        for source_id in ids:
            try:
                cards = self._cached(
                    (source_id, *key), lambda s=source_id: call(self.source(db, s))
                )
            except SourceError as error:
                listing.errors[source_id] = error.code
                continue
            for card in cards:
                if card.source in SWITCHABLE and not on[card.source]:
                    continue  # a ranking row of a source the person switched off
                if (card.source, card.ref) not in seen:
                    seen.add((card.source, card.ref))
                    listing.cards.append(card)
            if source_id == "ranking":
                listing.attribution = RANKING_ATTRIBUTION
        return listing

    def popular(self, db: Session, source: str | None = None, page: int = 1) -> Listing:
        on = enabled(db)
        ids = [source] if source else ["ranking", *[s for s in ("anthropic", "clawhub") if on[s]]]
        return self._gather(db, ids, lambda s: s.popular(page), ("popular", page))

    def search(self, db: Session, query: str, source: str | None = None, page: int = 1) -> Listing:
        query = query.strip()
        if query.startswith(("http://", "https://")):
            ids = ["github"]
        elif source:
            ids = [source]
        else:
            on = enabled(db)
            ids = ["ranking", *[s for s in SWITCHABLE if on[s]]]
        listing = self._gather(db, ids, lambda s: s.search(query, page), ("search", query, page))
        listing.errors = {k: v for k, v in listing.errors.items() if v != "needs_query"}
        listing.cards.sort(key=lambda c: -((c.installs or 0) + (c.stars or 0)))
        return listing

    # ----------------------------------------------------------------- previews
    def _clean(self) -> None:
        if not self.previews.exists():
            return
        for folder in self.previews.iterdir():
            meta = folder / "meta.json"
            try:
                created = json.loads(meta.read_text("utf-8"))["created"]
            except (OSError, ValueError, KeyError):
                created = 0
            if time.time() - created > PREVIEW_SECONDS:
                shutil.rmtree(folder, ignore_errors=True)

    def preview(self, db: Session, source_id: str, ref: str) -> Preview:
        """Downloads the skill at the source's current revision and keeps it for an hour."""
        self._clean()
        try:
            fetched = self.source(db, source_id).fetch(ref)
        except SourceError as error:
            raise ApiError(502, f"registry_{error.code}", error.message) from error
        try:
            checked = check_files(fetched.files)
        except SkillError as error:
            raise SkillError(
                error.code, f"La skill del registro no es válida: {error.message}"
            ) from error
        fetched.files = checked.files
        preview_id = uuid.uuid4().hex
        folder = self.previews / preview_id
        for path, data in fetched.files.items():
            target = folder / "files" / Path(*normalize_path(path).split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        meta = {
            "created": time.time(),
            "card": asdict(fetched.card),
            "revision": fetched.revision,
            "repo_url": fetched.repo_url,
            "path": fetched.path,
            "license": fetched.license,
            "security": fetched.security,
        }
        (folder / "meta.json").write_text(json.dumps(meta), "utf-8")
        return Preview(preview_id, fetched, checked.executables, checked.parsed.name)

    def load(self, preview_id: str) -> Preview:
        folder = self.previews / preview_id
        if len(preview_id) != 32 or not (folder / "meta.json").is_file():
            raise ApiError(410, "preview_expired", "the preview expired: open the skill again")
        meta = json.loads((folder / "meta.json").read_text("utf-8"))
        root = folder / "files"
        files = {
            p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
        }
        checked = check_files(files)
        fetched = Fetched(
            Card(**meta["card"]),
            checked.files,
            meta["revision"],
            meta["repo_url"],
            meta["path"],
            meta["license"],
            meta["security"],
        )
        return Preview(preview_id, fetched, checked.executables, checked.parsed.name)

    @staticmethod
    def _opened(preview: Preview, opened: list[str]) -> None:
        seen = {normalize_path(p) for p in opened}
        missing = [p for p in preview.executables if p not in seen]
        if missing:
            raise ApiError(
                409,
                "scripts_not_opened",
                "open every executable file before installing",
                extra={"files": missing},
            )

    def _label(self, preview: Preview) -> str:
        title = SOURCES[preview.fetched.card.source].title
        where = (
            preview.fetched.repo_url.removeprefix("https://github.com/") or preview.fetched.card.ref
        )
        return f"{title} · {where}@{preview.fetched.revision[:10]}"

    # ----------------------------------------------------------------- install
    def install(
        self,
        db: Session,
        preview_id: str,
        scope: str,
        project_id: str | None,
        agent_id: str | None,
        opened: list[str],
    ) -> tuple[Skill, str | None]:
        """(the skill, the name it got if its own was taken at that level)."""
        preview = self.load(preview_id)
        self._opened(preview, opened)
        files = preview.fetched.files
        name = self.library.free_name(db, preview.name, scope, project_id, agent_id)
        if name != preview.name:
            files = renamed(files, name)
        title = SOURCES[preview.fetched.card.source].title
        skill, version = self.library.create(
            db,
            scope=scope,
            project_id=project_id,
            agent_id=agent_id,
            files=files,
            origin=SkillOriginKind.REGISTRY,
            author=Author(VersionAuthor.REGISTRY, self._label(preview)),
            note=f"Instalada desde {title}",
        )
        fetched = preview.fetched
        db.add(
            SkillOrigin(
                skill_id=skill.id,
                source=fetched.card.source,
                ref=fetched.card.ref,
                repo_url=fetched.repo_url,
                path=fetched.path,
                revision=fetched.revision,
                license=fetched.license[:120],
                security=fetched.security,
                latest_revision=fetched.revision,
                checked_at=utcnow(),
                installed_version_id=version.id,
            )
        )
        db.flush()
        shutil.rmtree(self.previews / preview_id, ignore_errors=True)
        return skill, (name if name != preview.name else None)

    # ----------------------------------------------------------------- updates
    def check_updates(self, db: Session) -> dict[str, str]:
        """Asks each source for the latest revision of what was installed from it. Returns the
        skills whose source failed, with the reason."""
        failed: dict[str, str] = {}
        for origin in db.scalars(select(SkillOrigin)):
            try:
                origin.latest_revision = self.source(db, origin.source).latest(origin.ref)
                origin.checked_at = utcnow()
            except (SourceError, ApiError) as error:
                failed[origin.skill_id] = getattr(error, "code", "unavailable")
        db.flush()
        return failed

    def update_preview(self, db: Session, skill: Skill) -> tuple[Preview, list[history.FilePair]]:
        origin = db.get(SkillOrigin, skill.id)
        if origin is None:
            raise ApiError(409, "not_installed", "the skill was not installed from a registry")
        preview = self.preview(db, origin.source, origin.ref)
        current = self.library.version(db, skill)
        new = self.library.store.put_files(preview.fetched.files)
        return preview, history.diff(self.library.store, current.manifest, new)

    def apply_update(
        self, db: Session, skill: Skill, preview_id: str, opened: list[str]
    ) -> SkillVersion:
        """The new version from the registry, on top of the history (the person's own edits
        stay there and can be restored, CA17)."""
        origin = db.get(SkillOrigin, skill.id)
        if origin is None:
            raise ApiError(409, "not_installed", "the skill was not installed from a registry")
        preview = self.load(preview_id)
        if (preview.fetched.card.source, preview.fetched.card.ref) != (origin.source, origin.ref):
            raise ApiError(409, "other_skill", "that preview is of another skill")
        self._opened(preview, opened)
        files = preview.fetched.files
        if preview.name != skill.name:
            files = renamed(files, skill.name)
        title = SOURCES[origin.source].title
        version = self.library.add_version(
            db,
            skill,
            files,
            Author(VersionAuthor.REGISTRY, self._label(preview)),
            f"Actualizada desde {title}",
        )
        origin.revision = origin.latest_revision = preview.fetched.revision
        origin.security, origin.checked_at = preview.fetched.security, utcnow()
        origin.installed_version_id = version.id
        shutil.rmtree(self.previews / preview_id, ignore_errors=True)
        return version

    # ----------------------------------------------------------------- daily check
    def start(self, sessions) -> None:
        def loop() -> None:
            while not self._stop.wait(60):
                try:
                    with sessions() as db:
                        if db.scalar(select(SkillOrigin.skill_id).limit(1)) is not None:
                            self.check_updates(db)
                            db.commit()
                except Exception:
                    log.exception("skills_update_check_failed")
                if self._stop.wait(DAY):
                    return

        threading.Thread(target=loop, name="skills-updates", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.http.close()
