"""The explorer of public registries of MCP servers (phase 18, block 8, CA14 and CA15): «most used»
and search across the enabled sources, a ficha that says what exactly would run and what is
missing, installing it as a connection pinned to a version, and the updates of what was
installed (never applied by themselves)."""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import McpConnection, McpOrigin, McpOriginKind
from agentic_os.services.connections import config as connection_config
from agentic_os.services.connections import library
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.connections.registries.base import (
    Card,
    Detail,
    Http,
    Option,
    Source,
    SourceError,
    build_draft,
)
from agentic_os.services.connections.registries.official import OfficialSource
from agentic_os.services.connections.registries.packages import PackageSource
from agentic_os.services.connections.registries.smithery import SmitherySource
from agentic_os.services.connections.registries.versions import latest_version

log = structlog.get_logger()
CACHE_SECONDS = 600
DAY = 24 * 3600
SOURCES: dict[str, type[Source]] = {
    s.id: s for s in (OfficialSource, SmitherySource, PackageSource)
}
SWITCHABLE = ("official", "smithery")  # the package / repository source always works


@dataclass
class Listing:
    cards: list[Card] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source → code


@dataclass
class View:
    """A ficha: the detail plus what the machine is missing and the exact command of each way."""

    detail: Detail
    missing: dict[str, list[str]]  # option index → programs not installed
    commands: dict[int, str]
    installed_as: str | None = None


def enabled(db: Session) -> dict[str, bool]:
    stored = connection_config.load(db).registries
    return {s: bool(stored.get(s, SOURCES[s].default_enabled)) for s in SWITCHABLE}


def command_line(option: Option, version: str = "") -> str:
    """What would run, as a sentence-sized command (secrets only as their names)."""
    pinned = version or option.version
    pinned = "" if pinned == "latest" else pinned
    fixed: list[str] = []  # the arguments the registry fixes, which the person must see too
    for argument in option.args:
        if argument.get("value"):
            fixed += (
                [argument["name"], argument["value"]]
                if argument.get("name")
                else [argument["value"]]
            )
    tail = "".join(f" {a}" for a in fixed)
    if option.kind == "npm":
        pin = f"{option.package}@{pinned}" if pinned else f"{option.package}@<última>"
        return f"npx -y {pin}{tail}"
    if option.kind == "pypi":
        pin = f"{option.package}=={pinned}" if pinned else f"{option.package}==<última>"
        return f"uvx {pin}{tail}"
    if option.kind == "oci":
        options = "".join(f" {a}" for a in option.runtime_args)
        image = option.package + (f":{pinned}" if pinned else "")
        return f"docker run -i --rm{options} {image}{tail}"
    if option.kind == "command":
        return " ".join([option.command, *option.command_args])
    return option.url


def manifest_of(detail: Detail, option: Option, version: str) -> dict:
    """What an installation was made of: kept to show what an update changes."""
    return {
        "kind": option.kind,
        "package": option.package,
        "version": version,
        "command": command_line(option, version),
        "url": option.url,
        "variables": sorted(f.name or f.key for f in option.fields if f.where in ("env", "url")),
        "headers": sorted(f.name or f.key for f in option.fields if f.where == "header"),
        "args": sorted(f.key for f in option.fields if f.where == "arg"),
        "tools": sorted(t["name"] for t in detail.tools),
    }


class RegistryService:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        github_token: Callable[[], str | None] | None = None,
    ) -> None:
        self.http = Http(transport, github_token)
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._sources: dict[str, Source] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ sources
    def source(self, source_id: str) -> Source:
        if source_id not in SOURCES:
            raise NotFound("registry")
        if source_id not in self._sources:
            self._sources[source_id] = SOURCES[source_id](self.http)
        return self._sources[source_id]

    def status(self, db: Session) -> list[dict]:
        on = enabled(db)
        return [
            {
                "id": s.id,
                "title": s.title,
                "enabled": on.get(s.id, True),
                "switchable": s.id in SWITCHABLE,
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

    def _gather(self, ids: list[str], call: Callable[[Source], list[Card]], key: tuple) -> Listing:
        listing = Listing()
        seen: set[tuple[str, str]] = set()
        for source_id in ids:
            try:
                cards = self._cached((source_id, *key), lambda s=source_id: call(self.source(s)))
            except SourceError as error:
                listing.errors[source_id] = error.code
                continue
            for card in cards:
                if (card.source, card.ref) not in seen:
                    seen.add((card.source, card.ref))
                    listing.cards.append(card)
        return listing

    @staticmethod
    def _filter(cards: list[Card], transport: str | None) -> list[Card]:
        if transport in ("stdio", "http"):
            cards = [c for c in cards if c.transport in (transport, "both", "")]
        return cards

    def popular(
        self, db: Session, source: str | None = None, transport: str | None = None, page: int = 1
    ) -> Listing:
        on = enabled(db)
        ids = [source] if source else [s for s in SWITCHABLE if on[s]]
        listing = self._gather(ids, lambda s: s.popular(page), ("popular", page))
        listing.cards = self._filter(listing.cards, transport)
        listing.cards.sort(key=lambda c: -((c.uses or 0) + (c.stars or 0)))
        return listing

    def search(
        self,
        db: Session,
        query: str,
        source: str | None = None,
        transport: str | None = None,
        page: int = 1,
    ) -> Listing:
        query = query.strip()
        if not query:
            return self.popular(db, source, transport, page)
        if query.lower().startswith(("npm:", "pypi:", "http://", "https://")):
            ids = ["package"]
        elif source:
            ids = [source]
        else:
            on = enabled(db)
            ids = [s for s in SWITCHABLE if on[s]]
        listing = self._gather(ids, lambda s: s.search(query, page), ("search", query, page))
        listing.errors = {k: v for k, v in listing.errors.items() if v != "needs_query"}
        listing.cards = self._filter(listing.cards, transport)
        listing.cards.sort(key=lambda c: -((c.uses or 0) + (c.stars or 0)))
        return listing

    # ------------------------------------------------------------------ the ficha
    def view(self, db: Session, source_id: str, ref: str) -> View:
        try:
            detail = self.source(source_id).detail(ref)
        except SourceError as error:
            raise ApiError(502, f"registry_{error.code}", error.message) from error
        commands: dict[int, str] = {}
        missing: dict[str, list[str]] = {}
        for index, option in enumerate(detail.options):
            version = ""
            if option.kind in ("npm", "pypi") and option.version in ("", "latest"):
                try:
                    version = latest_version(self.http, option.kind, option.package)
                except SourceError:
                    version = ""
            commands[index] = command_line(option, version)
            absent = [p for p in option.requires if not shutil.which(p)]
            if absent:
                missing[str(index)] = absent
        origin = db.scalar(
            select(McpOrigin).where(McpOrigin.source == source_id, McpOrigin.ref == detail.card.ref)
        )
        installed = db.get(McpConnection, origin.connection_id) if origin else None
        return View(detail, missing, commands, installed.name if installed else None)

    # ------------------------------------------------------------------ install
    def install(
        self,
        db: Session,
        source_id: str,
        ref: str,
        option_index: int,
        values: dict[str, str],
        name: str = "",
        level=None,
        oauth: bool | None = None,
    ) -> McpConnection:
        """Creates the connection from the way the person chose, with the form's values. Nothing
        is run: the person tests it afterwards. A package is pinned to its exact version."""
        try:
            detail = self.source(source_id).detail(ref)
        except SourceError as error:
            raise ApiError(502, f"registry_{error.code}", error.message) from error
        if not 0 <= option_index < len(detail.options):
            raise ConnectionError_("option_unknown", "Esa forma de ejecutarlo no existe.")
        option = detail.options[option_index]
        if oauth is not None and option.kind == "remote":
            option.oauth = oauth
        resolved = ""
        if option.kind in ("npm", "pypi") and option.version in ("", "latest"):
            try:
                resolved = latest_version(self.http, option.kind, option.package)
            except SourceError as error:
                raise ApiError(
                    502, "registry_unavailable", "No se pudo saber la versión exacta del paquete."
                ) from error
        chosen = name or library.unique_name(db, detail.card.name)
        draft, version = build_draft(option, chosen, values, resolved)
        draft.description = detail.card.description[:300]
        connection = library.create(db, draft, origin=McpOriginKind.REGISTRY)
        db.add(
            McpOrigin(
                connection_id=connection.id,
                source=source_id,
                ref=detail.card.ref,
                package_type=option.kind,
                package=option.package,
                version=version,
                repo_url=detail.repo_url,
                license=detail.license,
                official=detail.card.verified,
                latest_version=version,
                checked_at=utcnow(),
                manifest=manifest_of(detail, option, version),
            )
        )
        if level is not None:
            library.assign(db, connection, level.scope, level.project_id, level.agent_id)
        db.flush()
        return connection

    # ------------------------------------------------------------------ updates
    def check_updates(self, db: Session) -> list[McpOrigin]:
        """Asks the registries for the current version of every installed package. Returns the
        ones that have a newer one. Nothing is changed in the connections."""
        newer: list[McpOrigin] = []
        for origin in db.scalars(
            select(McpOrigin).where(McpOrigin.package_type.in_(["npm", "pypi"]))
        ):
            try:
                latest = latest_version(self.http, origin.package_type, origin.package)
            except SourceError:
                continue
            origin.latest_version, origin.checked_at = latest, utcnow()
            if latest and latest != origin.version:
                newer.append(origin)
        db.flush()
        return newer

    def update_preview(self, db: Session, connection: McpConnection) -> dict:
        """What would change: the version, the command and, if the registry still lists the
        package, its variables and declared tools."""
        origin = self._origin(db, connection)
        latest = origin.latest_version
        if not latest or latest == origin.version:
            raise ConnectionError_("up_to_date", "Ya tiene la última versión.")
        old = origin.manifest or {}
        new = dict(old)
        new["version"] = latest
        new["command"] = _repin(old.get("command", ""), origin, latest)
        try:
            detail = self.source(origin.source).detail(origin.ref)
            option = next(
                (
                    o
                    for o in detail.options
                    if o.kind == origin.package_type and o.package == origin.package
                ),
                None,
            )
            if option is not None:
                new = manifest_of(detail, option, latest)
        except (SourceError, ApiError):
            pass
        changes = []
        for key, label in (
            ("command", "Comando"),
            ("variables", "Variables"),
            ("headers", "Cabeceras"),
            ("args", "Argumentos"),
            ("tools", "Herramientas declaradas"),
        ):
            if old.get(key) != new.get(key):
                changes.append(
                    {"field": key, "label": label, "from": old.get(key), "to": new.get(key)}
                )
        return {"from": origin.version, "to": latest, "changes": changes}

    def apply_update(self, db: Session, connection: McpConnection) -> McpConnection:
        origin = self._origin(db, connection)
        latest = origin.latest_version
        if not latest or latest == origin.version:
            raise ConnectionError_("up_to_date", "Ya tiene la última versión.")
        preview = self.update_preview(db, connection)
        old_pin, new_pin = _pin(origin, origin.version), _pin(origin, latest)
        if old_pin not in connection.args:
            raise ConnectionError_(
                "update_edited",
                "Has cambiado el comando de esta conexión a mano: actualízala editándolo.",
            )
        connection.args = [new_pin if a == old_pin else a for a in connection.args]
        connection.revision += 1
        connection.tools_changed = True  # the new version may have other tools: test it again
        origin.version = latest
        origin.manifest = {
            **(origin.manifest or {}),
            "version": latest,
            **{c["field"]: c["to"] for c in preview["changes"]},
        }
        db.flush()
        return connection

    @staticmethod
    def _origin(db: Session, connection: McpConnection) -> McpOrigin:
        origin = db.get(McpOrigin, connection.id)
        if origin is None:
            raise ConnectionError_("not_from_registry", "Esta conexión no viene de un registro.")
        return origin

    # ------------------------------------------------------------------ background
    def start(self, factory: sessionmaker, first_after: float = 90) -> None:
        def run() -> None:
            if self._stop.wait(first_after):
                return
            while True:
                try:
                    with factory() as db:
                        self.check_updates(db)
                        db.commit()
                except Exception:
                    log.exception("checking the MCP server updates failed")
                if self._stop.wait(DAY):
                    return

        self._thread = threading.Thread(target=run, name="mcp-registry-updates", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.http.close()


def _pin(origin: McpOrigin, version: str) -> str:
    return (
        f"{origin.package}@{version}"
        if origin.package_type == "npm"
        else f"{origin.package}=={version}"
    )


def _repin(command: str, origin: McpOrigin, latest: str) -> str:
    return command.replace(_pin(origin, origin.version), _pin(origin, latest))
