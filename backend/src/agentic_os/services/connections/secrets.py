"""The secrets of the connections, in the system's credential store (ADR 0018, extended).

Windows Credential Manager, macOS Keychain or the Secret Service, through `keyring`. Nothing
secret is kept in the database or in the app's files. The Windows store takes at most 1 280
characters per entry (spike S5), so a value is cut into pieces of `CHUNK` characters: the main
entry says how many pieces there are and the pieces are `<name>#<i>`.

A secret is named `mcp:<connection id>:<key>`. The connection declares its keys
(`McpConnection.secret_keys`) and refers to them with `${secret:KEY}` placeholders in `env`,
`headers`, `args` and `url`.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from agentic_os.services.connections.errors import ConnectionError_

SERVICE = "agentic-os"
CHUNK = 1_000
KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PLACEHOLDER = re.compile(r"\$\{(secret|env):([A-Za-z0-9_.-]{1,64})\}")


class CredentialStore(Protocol):
    def get(self, service: str, name: str) -> str | None: ...
    def set(self, service: str, name: str, value: str) -> None: ...
    def delete(self, service: str, name: str) -> None: ...


class KeyringStore:
    """The real thing. Any failure of the store is reported as «secrets_unavailable»."""

    def _call(self, action: str, fn, *args):
        try:
            return fn(*args)
        except Exception as error:
            if action == "delete" and type(error).__name__ == "PasswordDeleteError":
                return None  # already gone
            raise ConnectionError_(
                "secrets_unavailable",
                "No se puede usar el almacén de credenciales del sistema para guardar el "
                "secreto. Usa una variable del sistema (${env:NOMBRE}) en su lugar.",
                detail=f"{type(error).__name__}: {error}"[:200],
            ) from error

    def get(self, service: str, name: str) -> str | None:
        import keyring

        return self._call("get", keyring.get_password, service, name)

    def set(self, service: str, name: str, value: str) -> None:
        import keyring

        self._call("set", keyring.set_password, service, name, value)

    def delete(self, service: str, name: str) -> None:
        import keyring

        self._call("delete", keyring.delete_password, service, name)


class MemoryStore:
    """For the tests (never the person's own credential manager) and as a fallback."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], str] = {}

    def get(self, service: str, name: str) -> str | None:
        return self.entries.get((service, name))

    def set(self, service: str, name: str, value: str) -> None:
        self.entries[(service, name)] = value

    def delete(self, service: str, name: str) -> None:
        self.entries.pop((service, name), None)


_store: CredentialStore = KeyringStore()


def use(store: CredentialStore) -> CredentialStore:
    """Swaps the store (tests). Returns the previous one."""
    global _store
    previous, _store = _store, store
    return previous


def current() -> CredentialStore:
    return _store


def entry_name(connection_id: str, key: str) -> str:
    return f"mcp:{connection_id}:{key}"


def check_key(key: str) -> str:
    if not KEY_RE.match(key):
        raise ConnectionError_(
            "secret_key_invalid",
            f"El nombre del secreto «{key}» no es válido: usa letras, números, «_», «-» o «.».",
            key=key,
        )
    return key


# -- pieces -------------------------------------------------------------------------------------
def put_raw(name: str, value: str) -> None:
    parts = [value[i : i + CHUNK] for i in range(0, len(value), CHUNK)] or [""]
    previous = _count(name) or 0
    # Pieces first, the head last: a reader never sees a head whose pieces are not there yet.
    for index, part in enumerate(parts):
        _store.set(SERVICE, f"{name}#{index}", part)
    _store.set(SERVICE, name, json.dumps({"n": len(parts)}))
    for index in range(len(parts), previous):  # a shorter value leaves old pieces behind
        _store.delete(SERVICE, f"{name}#{index}")


def get_raw(name: str) -> str | None:
    count = _count(name)
    if count is None:
        return None
    return "".join(_store.get(SERVICE, f"{name}#{i}") or "" for i in range(count))


def delete_raw(name: str) -> None:
    count = _count(name) or 0
    _store.delete(SERVICE, name)
    for index in range(count):
        _store.delete(SERVICE, f"{name}#{index}")


def _count(name: str) -> int | None:
    head = _store.get(SERVICE, name)
    if head is None:
        return None
    try:
        return int(json.loads(head)["n"])
    except (ValueError, KeyError, TypeError):
        return None


# -- a connection's secrets ---------------------------------------------------------------------
def put(connection_id: str, key: str, value: str) -> None:
    put_raw(entry_name(connection_id, check_key(key)), value)


def get(connection_id: str, key: str) -> str | None:
    return get_raw(entry_name(connection_id, key))


def has(connection_id: str, key: str) -> bool:
    return _count(entry_name(connection_id, key)) is not None


def delete(connection_id: str, key: str) -> None:
    delete_raw(entry_name(connection_id, key))


def delete_all(connection_id: str, keys: list[str]) -> None:
    for key in keys:
        delete(connection_id, key)


def status(connection_id: str, keys: list[str]) -> dict[str, bool]:
    """Which of the declared secrets are set. Never the values."""
    found = {}
    for key in keys:
        try:
            found[key] = has(connection_id, key)
        except ConnectionError_:  # the store is not there: it can still be listed
            found[key] = False
    return found


# -- placeholders -------------------------------------------------------------------------------
def placeholders(text: str) -> list[tuple[str, str]]:
    """[(kind, name)] of the `${secret:KEY}` / `${env:NAME}` in a text, in order."""
    return [(m.group(1), m.group(2)) for m in PLACEHOLDER.finditer(text)]


def secret_keys_in(*texts: str) -> list[str]:
    keys: list[str] = []
    for text in texts:
        for kind, name in placeholders(text):
            if kind == "secret" and name not in keys:
                keys.append(name)
    return keys


class MissingSecret(ConnectionError_):
    def __init__(self, connection: str, kind: str, name: str) -> None:
        where = "la variable del sistema" if kind == "env" else "el secreto"
        super().__init__(
            "secret_missing",
            f"Falta {where} «{name}» de la conexión «{connection}».",
            connection=connection,
            kind=kind,
            name=name,
        )


def resolve_text(
    text: str, connection_id: str, connection_name: str, secrets_seen: set[str]
) -> str:
    """Replaces the placeholders with their values. Every secret value used goes into
    `secrets_seen` (what the run must hide from its output)."""

    def value(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        found = get(connection_id, name) if kind == "secret" else os.environ.get(name)
        if found is None or found == "":
            raise MissingSecret(connection_name, kind, name)
        secrets_seen.add(found)
        return found

    return PLACEHOLDER.sub(value, text)
