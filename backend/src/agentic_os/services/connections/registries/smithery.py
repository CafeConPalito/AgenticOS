"""Smithery (registry.smithery.ai, spike S4): open, no key. It gives the number of uses, whether a
server is verified and the tools it declares. Only the servers it hosts remotely can be used from
here (the others are installed with its own tool). Its remotes go through its gateway, so the
connection asks for the person's login (OAuth) by default."""

from __future__ import annotations

from urllib.parse import quote

from agentic_os.services.connections.registries.base import (
    Card,
    Detail,
    Option,
    Source,
    SourceError,
)

BASE = "https://registry.smithery.ai"
PAGE = 30


def _card(server: dict) -> Card:
    name = server.get("qualifiedName", "")
    return Card(
        source="smithery",
        ref=name,
        name=server.get("displayName") or name,
        description=server.get("description", ""),
        author=server.get("namespace", ""),
        uses=server.get("useCount"),
        updated_at=server.get("createdAt"),
        url=server.get("homepage") or f"https://smithery.ai/servers/{name}",
        transport="http" if server.get("remote") else "",
        verified=bool(server.get("verified")),
    )


class SmitherySource(Source):
    id = "smithery"
    title = "Smithery"
    has_popular = True

    def _list(self, **params) -> list[Card]:
        data = self.http.json(f"{BASE}/servers", params={"pageSize": PAGE, **params})
        return [
            _card(s)
            for s in data.get("servers", [])
            if s.get("remote") and not s.get("unlisted") and not s.get("inactive")
        ]

    def popular(self, page: int = 1) -> list[Card]:
        return self._list(page=page)

    def search(self, query: str, page: int = 1) -> list[Card]:
        return self._list(q=query, page=page)

    def detail(self, ref: str) -> Detail:
        data = self.http.json(f"{BASE}/servers/{quote(ref, safe='/')}")
        remote = next(
            (
                c
                for c in data.get("connections") or []
                if c.get("type") in ("http", "streamable-http")
            ),
            None,
        )
        url = (remote or {}).get("deploymentUrl") or data.get("deploymentUrl") or ""
        if not url:
            raise SourceError(
                "bad_server",
                "Este servidor no se puede usar desde aquí: no tiene una dirección remota.",
            )
        card = _card({**data, "qualifiedName": ref, "remote": True})
        option = Option(
            kind="remote",
            label="Servidor remoto (por Smithery)",
            transport="http",
            url=url,
            oauth=True,
        )
        tools = [
            {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema") or {},
            }
            for t in data.get("tools") or []
        ]
        return Detail(
            card=card,
            options=[option],
            tools=tools,
            security=data.get("security") or {},
            repo_url=data.get("homepage") or "",
            note=(
                "Es un servidor alojado por Smithery: tus peticiones pasan por su pasarela. "
                "Se conecta con tu cuenta (OAuth)."
            ),
            manifest={"version": "", "name": ref, "url": url},
        )
