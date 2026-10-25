"""Packages and repositories as sources of servers (phase 18, block 8): the exact version of an
npm or PyPI package (so a connection is pinned to code the person has seen), its weekly downloads,
and a «source» that takes a package name or a GitHub address (spec G)."""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from agentic_os.services.connections import format as fmt
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.connections.registries.base import (
    Card,
    Detail,
    Field,
    Option,
    Source,
    SourceError,
)
from agentic_os.services.connections.registries.official import options_of
from agentic_os.services.connections.registries.versions import NPM, PYPI

RAW = "https://raw.githubusercontent.com"
GITHUB_API = "https://api.github.com"


def parse_reference(text: str) -> tuple[str, str]:
    """(kind, name) of what the person typed: «npm:pkg», «pypi:pkg», a package page or a GitHub
    address. Raises `needs_query` for anything else."""
    text = text.strip()
    if text.lower().startswith("npm:"):
        return "npm", text[4:].strip()
    if text.lower().startswith("pypi:"):
        return "pypi", text[5:].strip()
    parsed = urlparse(text)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.split("/") if p]
    if host == "npmjs.com" and parts[:1] == ["package"] and len(parts) >= 2:
        return "npm", "/".join(parts[1:3] if parts[1].startswith("@") else parts[1:2])
    if host == "pypi.org" and parts[:1] == ["project"] and len(parts) >= 2:
        return "pypi", parts[1]
    if host == "github.com" and len(parts) >= 2:
        return "github", f"{parts[0]}/{parts[1].removesuffix('.git')}"
    raise SourceError("needs_query", "")


class PackageSource(Source):
    """An npm or PyPI package, or a GitHub repository, given by name or address."""

    id = "package"
    title = "Paquete o repositorio"

    def search(self, query: str, page: int = 1) -> list[Card]:
        if page > 1:
            return []
        kind, name = parse_reference(query)
        return [self._card(kind, name, query)]

    def _card(self, kind: str, name: str, ref: str) -> Card:
        if kind == "npm":
            info = self.http.json(f"{NPM}/{quote(name, safe='@')}/latest")
            return Card(
                source="package",
                ref=ref,
                name=name,
                description=info.get("description", ""),
                author="npm",
                url=f"https://www.npmjs.com/package/{name}",
                transport="stdio",
                version=str(info.get("version", "")),
            )
        if kind == "pypi":
            info = self.http.json(f"{PYPI}/{quote(name)}/json")["info"]
            return Card(
                source="package",
                ref=ref,
                name=name,
                description=info.get("summary", ""),
                author="PyPI",
                url=f"https://pypi.org/project/{name}/",
                transport="stdio",
                version=str(info.get("version", "")),
            )
        repo = self.http.json(f"{GITHUB_API}/repos/{name}")
        return Card(
            source="package",
            ref=ref,
            name=repo.get("name", name),
            description=repo.get("description") or "",
            author=name.split("/")[0],
            stars=repo.get("stargazers_count"),
            updated_at=repo.get("pushed_at"),
            url=repo.get("html_url", ""),
            transport="",
        )

    def detail(self, ref: str) -> Detail:
        kind, name = parse_reference(ref)
        card = self._card(kind, name, ref)
        if kind in ("npm", "pypi"):
            option = Option(
                kind=kind,
                label="Paquete npm" if kind == "npm" else "Paquete PyPI",
                package=name,
                version=card.version,
            )
            return Detail(
                card=card,
                options=[option],
                license="",
                repo_url=card.url,
                note="Este paquete no dice qué variables necesita: míralo en su página.",
                manifest={"version": card.version, "name": name},
            )
        return self._github_detail(card, name)

    def _github_detail(self, card: Card, name: str) -> Detail:
        repo = self.http.json(f"{GITHUB_API}/repos/{name}")
        branch = repo.get("default_branch") or "main"
        license_id = ((repo.get("license") or {}).get("spdx_id")) or ""
        base = f"{RAW}/{name}/{branch}"
        options: list[Option] = []
        note = ""
        try:
            server = self.http.json(f"{base}/server.json")
            options = options_of(server)
        except SourceError:
            pass
        if not options:
            try:
                readme = self.http.get(f"{base}/README.md").text
                options = _options_from_readme(readme)
                note = "Sacado del README del repositorio: comprueba el comando antes de instalar."
            except SourceError:
                pass
        if not options:
            raise SourceError(
                "bad_server",
                "No encuentro cómo ejecutarlo: el repositorio no trae server.json ni un bloque "
                "mcpServers en su README.",
            )
        card.transport = "both" if len({o.transport for o in options}) > 1 else options[0].transport
        return Detail(
            card=card,
            options=options,
            license=license_id,
            repo_url=repo.get("html_url", ""),
            note=note,
            manifest={"version": card.version or branch, "name": name},
        )


def _options_from_readme(readme: str) -> list[Option]:
    """The first ```json block of the README that holds a `mcpServers` entry."""
    for block in re.findall(r"```(?:json|jsonc)?\s*\n(.*?)```", readme, flags=re.DOTALL):
        if "mcpServers" not in block and '"command"' not in block:
            continue
        try:
            drafts = fmt.parse_servers(block)
        except ConnectionError_:
            continue
        options = []
        for draft in drafts[:3]:
            option = Option(
                kind="remote" if draft.transport != "stdio" else "command",
                label=f"Del README ({draft.name})",
                transport=draft.transport,
                url=draft.url,
                command=draft.command,
                command_args=list(draft.args),
            )
            for where, pairs in (("env", draft.env), ("header", draft.headers)):
                for key, value in pairs.items():
                    secret = bool(fmt.SECRET_KEY_RE.search(key))
                    option.fields.append(
                        Field(
                            key=key,
                            label=key,
                            where=where,
                            name=key,
                            secret=secret,
                            required=secret,
                            default="" if secret else value,
                        )
                    )
            options.append(option)
        if options:
            return options
    return []
