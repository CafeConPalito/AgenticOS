"""The official registry of MCP servers (registry.modelcontextprotocol.io, spike S4): open, no
key, `server.json` entries with `packages` (npm, PyPI, OCI) and `remotes`. It publishes no usage
figure, so the «most used» list is ordered by the weekly downloads of their npm packages."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

from agentic_os.services.connections.registries.base import (
    Card,
    Detail,
    Field,
    Option,
    Source,
    SourceError,
)
from agentic_os.services.connections.registries.versions import npm_downloads

BASE = "https://registry.modelcontextprotocol.io/v0.1"
LIMIT = 40
HOSTED_BY_SMITHERY = "ai.smithery/"  # also listed by Smithery itself: shown there
_PACKAGE_KINDS = {"npm": "npm", "pypi": "pypi", "oci": "oci"}


def _meta(entry: dict) -> dict:
    return (entry.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}


def published_by_its_author(server: dict) -> bool:
    """The name's namespace belongs to the repository's owner or to the site's domain: the
    registry checked that the publisher controls it (GitHub login or DNS)."""
    name = server.get("name", "")
    namespace, _, _ = name.partition("/")
    repo = urlparse((server.get("repository") or {}).get("url", "")).path.strip("/").split("/")
    if namespace.startswith("io.github.") and repo and repo[0]:
        return namespace.removeprefix("io.github.").lower() == repo[0].lower()
    domain = ".".join(reversed(namespace.split(".")))
    hosts = [urlparse(server.get("websiteUrl", "")).netloc] + [
        urlparse(r.get("url", "")).netloc for r in server.get("remotes") or []
    ]
    return bool(domain) and any(h == domain or h.endswith("." + domain) for h in hosts if h)


def _transport(server: dict) -> str:
    stdio = any(
        (p.get("transport") or {}).get("type") == "stdio"
        and p.get("registryType") in _PACKAGE_KINDS
        for p in server.get("packages") or []
    )
    remote = bool(server.get("remotes"))
    return "both" if stdio and remote else "stdio" if stdio else "http" if remote else ""


GENERIC = {"mcp", "server", "mcp-server", "server-mcp", "api", "app"}


def display_name(full: str) -> str:
    """«acme/pg-mcp» → «pg-mcp»; a name too generic to tell servers apart gets its owner:
    «io.github.acme/mcp» → «acme-mcp»."""
    namespace, _, short = full.partition("/")
    if short.lower() not in GENERIC:
        return short or full
    owner = namespace.rsplit(".", 1)[-1]
    return f"{owner}-{short}"


def card_of(entry: dict) -> Card:
    server = entry["server"]
    meta = _meta(entry)
    return Card(
        source="official",
        ref=server["name"],
        name=display_name(server["name"]),
        description=server.get("description", ""),
        author=server["name"].split("/", 1)[0],
        updated_at=meta.get("updatedAt"),
        url=server.get("websiteUrl") or (server.get("repository") or {}).get("url", ""),
        transport=_transport(server),
        verified=published_by_its_author(server),
        version=server.get("version", ""),
    )


def _fields_of_variables(variables: dict, where: str) -> list[Field]:
    return [
        Field(
            key=name,
            label=name,
            where=where,
            name=name,
            secret=bool(spec.get("isSecret")),
            required=bool(spec.get("isRequired", True)),
            default=str(spec.get("default") or ""),
            description=spec.get("description", ""),
        )
        for name, spec in (variables or {}).items()
    ]


def _package_option(package: dict) -> Option | None:
    kind = _PACKAGE_KINDS.get(package.get("registryType", ""))
    if kind is None or (package.get("transport") or {}).get("type") != "stdio":
        return None  # nuget, mcpb…, or a package that serves HTTP on a port we do not know
    option = Option(
        kind=kind,
        label={"npm": "Paquete npm", "pypi": "Paquete PyPI", "oci": "Imagen Docker"}[kind],
        package=package["identifier"],
        version=str(package.get("version") or ""),
    )
    for var in package.get("environmentVariables") or []:
        option.fields.append(
            Field(
                key=var["name"],
                label=var["name"],
                where="env",
                name=var["name"],
                secret=bool(var.get("isSecret")),
                required=bool(var.get("isRequired")),
                default=str(var.get("default") or ""),
                description=var.get("description", ""),
            )
        )
    for index, arg in enumerate(package.get("packageArguments") or [], start=1):
        flag = arg.get("name", "") if arg.get("type") == "named" else ""
        if arg.get("value") and "{" not in str(arg["value"]):
            option.args.append({"name": flag, "value": str(arg["value"])})
            continue
        key = (
            (flag.lstrip("-") or arg.get("valueHint") or f"arg{index}")
            if flag or arg.get("valueHint")
            else f"arg{index}"
        )
        option.args.append({"name": flag, "value": ""})
        option.fields.append(
            Field(
                key=key,
                label=arg.get("valueHint") or flag or f"Argumento {index}",
                where="arg",
                name=flag,
                secret=bool(arg.get("isSecret")),
                required=bool(arg.get("isRequired")),
                default=str(arg.get("default") or ""),
                description=arg.get("description", ""),
            )
        )
    option.runtime_args = [
        str(x)
        for a in package.get("runtimeArguments") or []
        for x in (
            [a["name"], a["value"]]
            if a.get("name") and a.get("value")
            else [a.get("value") or a.get("name")]
        )
        if x
    ]
    return option


def _remote_option(remote: dict) -> Option:
    kind = remote.get("type", "streamable-http")
    option = Option(
        kind="remote",
        label="Servidor remoto",
        transport="sse" if kind == "sse" else "http",
        url=remote.get("url", ""),
    )
    option.fields += _fields_of_variables(remote.get("variables") or {}, "url")
    for header in remote.get("headers") or []:
        value = str(header.get("value") or "")
        tokens = [t for t in re.findall(r"\{([A-Za-z_][\w.-]*)\}", value)]
        key = tokens[0] if tokens else header["name"]
        option.fields.append(
            Field(
                key=key,
                label=header["name"],
                where="header",
                name=header["name"],
                secret=bool(header.get("isSecret")),
                required=bool(header.get("isRequired")),
                default="" if tokens else value,
                description=header.get("description", ""),
                template=re.sub(r"\{[A-Za-z_][\w.-]*\}", "{value}", value) if tokens else "{value}",
            )
        )
    return option


def options_of(server: dict) -> list[Option]:
    options = [o for p in server.get("packages") or [] if (o := _package_option(p))]
    options += [_remote_option(r) for r in server.get("remotes") or []]
    return options


class OfficialSource(Source):
    id = "official"
    title = "Registro oficial de MCP"
    has_popular = True

    def _list(self, **params) -> list[dict]:
        data = self.http.json(f"{BASE}/servers", params={"limit": LIMIT, **params})
        return [
            e
            for e in data.get("servers", [])
            if not e["server"]["name"].startswith(HOSTED_BY_SMITHERY)
        ]

    def search(self, query: str, page: int = 1) -> list[Card]:
        if page > 1:
            return []
        return [card_of(e) for e in self._list(search=query)]

    def popular(self, page: int = 1) -> list[Card]:
        if page > 1:
            return []
        entries = self._list()
        cards = [card_of(e) for e in entries]
        names = {}
        for entry, card in zip(entries, cards, strict=True):
            for package in entry["server"].get("packages") or []:
                if package.get("registryType") == "npm":
                    names[card.ref] = package["identifier"]
                    break
        with ThreadPoolExecutor(8) as pool:
            counts = dict(
                zip(
                    names,
                    pool.map(lambda n: npm_downloads(self.http, n), names.values()),
                    strict=True,
                )
            )
        for card in cards:
            card.uses = counts.get(card.ref)
        cards.sort(key=lambda c: -(c.uses or 0))
        return cards

    def detail(self, ref: str) -> Detail:
        entry = self.http.json(f"{BASE}/servers/{quote(ref, safe='')}/versions/latest")
        server = entry["server"]
        card = card_of(entry)
        options = options_of(server)
        if not options:
            raise SourceError(
                "bad_server",
                "No se puede ejecutar desde aquí: no tiene un paquete ni una dirección "
                "compatibles.",
            )
        repo = (server.get("repository") or {}).get("url", "")
        return Detail(
            card=card,
            options=options,
            repo_url=repo,
            website=server.get("websiteUrl", ""),
            manifest={"version": server.get("version", ""), "name": server["name"]},
        )
