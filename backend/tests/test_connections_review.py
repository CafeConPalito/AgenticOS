"""Regressions found by the review of phase 18."""

from __future__ import annotations

import httpx

from agentic_os.services.connections import oauth, secrets
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.connections.registries.base import Option
from agentic_os.services.connections.registries.service import command_line


def test_the_ficha_shows_the_docker_options_the_registry_adds():
    option = Option(
        kind="oci",
        label="Imagen",
        package="acme/pg",
        runtime_args=["--privileged", "-v", "/:/host"],
    )
    assert command_line(option, "1.0") == ("docker run -i --rm --privileged -v /:/host acme/pg:1.0")


def test_an_outage_is_not_a_lost_login():
    assert oauth._transient(httpx.ConnectError("offline"))
    assert oauth._transient(TimeoutError())
    assert not oauth._transient(oauth.NeedsLogin("hay que volver a conectar"))


def test_the_catalog_lists_connections_when_the_store_is_unavailable(monkeypatch):
    def broken(connection_id: str, key: str) -> bool:
        raise ConnectionError_("secrets_unavailable", "sin almacén")

    monkeypatch.setattr(secrets, "has", broken)
    assert secrets.status("c1", ["TOKEN"]) == {"TOKEN": False}
