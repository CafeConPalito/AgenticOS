"""Reading and checking the configuration of an MCP server (phase 18).

`parse_servers` understands what the CLIs and the servers' READMEs publish: the `mcpServers`
block of Claude Code (`~/.claude.json`, `.mcp.json`) and of `agy` (`mcp_config.json`), VS Code's
`servers`, a map of servers, or one server object. Values that look like secrets (a token in an
environment variable, an `Authorization` header, a password inside a connection string) become
`${secret:KEY}` placeholders and the real value is kept apart in `Draft.secrets`, so it goes to
the credential store and never into the database. `${NAME}` references to the system's
environment become `${env:NAME}`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
RESERVED = {"agentic-os", "agentic_os", "agenticos"}
TRANSPORTS = {"stdio", "http", "sse"}
_TYPE_ALIASES = {
    "stdio": "stdio",
    "http": "http",
    "streamable-http": "http",
    "streamablehttp": "http",
    "streamable_http": "http",
    "sse": "sse",
}
SECRET_KEY_RE = re.compile(
    r"(token|secret|passw(or)?d|pwd|api[_-]?key|apikey|auth|credential|private[_-]?key|bearer)",
    re.IGNORECASE,
)
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}")
_URL_PASSWORD = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^:/\s@]+:)([^@\s/]+)(@)")
_SCHEME = re.compile(r"^(Bearer|Basic|Token|ApiKey)\s+(.+)$", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\$\{(secret|env):[A-Za-z0-9_.-]+\}")


@dataclass
class Draft:
    """One server as it will become a connection."""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    description: str = ""
    icon: str = ""
    auth: str = "none"
    # Secret values found in the source, by key. They go to the credential store.
    secrets: dict[str, str] = field(default_factory=dict)
    # What the source had that this app does not keep (for the «no importado» list).
    ignored: list[str] = field(default_factory=list)

    @property
    def secret_keys(self) -> list[str]:
        keys = secrets.secret_keys_in(
            self.url, *self.args, *self.env.values(), *self.headers.values()
        )
        return list(dict.fromkeys([*keys, *self.secrets]))


# -- values -------------------------------------------------------------------------------------
def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_").upper() or "VALUE"


def _env_refs(value: str) -> str:
    """`${NAME}` (and `${NAME:-default}`) of Claude's files → `${env:NAME}`."""
    return _ENV_REF.sub(lambda m: "${env:" + m.group(1) + "}", value)


def _unique_key(key: str, draft: Draft) -> str:
    base, number = key, 2
    while key in draft.secrets:
        key = f"{base}_{number}"
        number += 1
    return key


def _hide(value: str, key_hint: str, draft: Draft) -> str:
    """The value, or a placeholder if it is a secret that is written out."""
    value = _env_refs(value)
    if not value or _PLACEHOLDER.search(value):
        return value
    scheme = _SCHEME.match(value)
    prefix, secret = (f"{scheme.group(1)} ", scheme.group(2)) if scheme else ("", value)
    key = _unique_key(_slug(key_hint), draft)
    draft.secrets[key] = secret
    return f"{prefix}${{secret:{key}}}"


def _hide_in_url(text: str, draft: Draft, hint: str = "PASSWORD") -> str:
    """A password inside a connection string (`postgres://user:pass@host/db`)."""
    if _PLACEHOLDER.search(text):
        return _env_refs(text)

    def swap(match: re.Match[str]) -> str:
        key = _unique_key(hint, draft)
        draft.secrets[key] = match.group(2)
        return f"{match.group(1)}${{secret:{key}}}{match.group(3)}"

    return _env_refs(_URL_PASSWORD.sub(swap, text))


def _string_map(raw: object, field_name: str, name: str) -> dict[str, str]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ConnectionError_(
            "config_invalid",
            f"En «{name}», «{field_name}» tiene que ser un objeto con pares clave: valor.",
            connection=name,
            field=field_name,
        )
    return {str(k): "" if v is None else str(v) for k, v in raw.items()}


# -- one server ---------------------------------------------------------------------------------
def parse_server(name: str, raw: object) -> Draft:
    if not isinstance(raw, dict):
        raise ConnectionError_(
            "config_invalid",
            f"La configuración de «{name}» tiene que ser un objeto JSON.",
            connection=name,
        )
    kind = str(raw.get("type") or raw.get("transport") or "").lower()
    url = raw.get("url") or raw.get("serverUrl") or raw.get("httpUrl") or ""
    if kind:
        if kind not in _TYPE_ALIASES:
            raise ConnectionError_(
                "transport_invalid",
                f"El tipo «{kind}» de «{name}» no existe: usa «stdio», «http» o «sse».",
                connection=name,
                transport=kind,
            )
        transport = _TYPE_ALIASES[kind]
    elif raw.get("command"):
        transport = "stdio"
    elif url:
        transport = "sse" if str(url).rstrip("/").endswith("/sse") else "http"
    else:
        raise ConnectionError_(
            "config_invalid",
            f"«{name}» no tiene ni «command» (servidor local) ni «url» (servidor remoto).",
            connection=name,
        )
    draft = Draft(name=name, transport=transport)
    known = {"type", "transport", "command", "args", "env", "cwd", "url", "serverUrl", "httpUrl"}
    known |= {"headers", "description", "disabled", "name"}
    draft.ignored = sorted(str(k) for k in raw if k not in known)
    draft.description = str(raw.get("description") or "")
    if transport == "stdio":
        command = raw.get("command")
        if isinstance(command, list):  # some files put the whole command line in a list
            command, *rest = [str(c) for c in command] or [""]
            raw = {**raw, "args": [*rest, *(raw.get("args") or [])]}
        draft.command = str(command or "")
        args = raw.get("args") or []
        if not isinstance(args, list):
            raise ConnectionError_(
                "config_invalid",
                f"En «{name}», «args» tiene que ser una lista.",
                connection=name,
                field="args",
            )
        draft.args = [_hide_in_url(str(a), draft) for a in args]
        draft.cwd = str(raw.get("cwd") or "")
        for key, value in _string_map(raw.get("env"), "env", name).items():
            draft.env[key] = (
                _hide(value, key, draft) if SECRET_KEY_RE.search(key) else _env_refs(value)
            )
    else:
        draft.url = _hide_in_url(str(url), draft, "URL_PASSWORD")
        for key, value in _string_map(raw.get("headers"), "headers", name).items():
            draft.headers[key] = (
                _hide(value, key, draft) if SECRET_KEY_RE.search(key) else _env_refs(value)
            )
        # A stdio server may also carry env, and a remote one rarely does: keep what is there.
        env = _string_map(raw.get("env"), "env", name)
        if env:
            draft.env = {k: _env_refs(v) for k, v in env.items()}
    return draft


def parse_servers(text: str, default_name: str = "") -> list[Draft]:
    """The servers of a JSON text. Errors say in words what is wrong."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConnectionError_(
            "json_invalid",
            f"El JSON no es válido (línea {error.lineno}, columna {error.colno}): {error.msg}.",
            line=error.lineno,
            column=error.colno,
        ) from error
    if not isinstance(data, dict):
        raise ConnectionError_(
            "config_invalid", "Se esperaba un objeto JSON con «mcpServers» o con un servidor."
        )
    block = data.get("mcpServers") or data.get("servers")
    if isinstance(block, dict):
        servers = block
    elif "command" in data or "url" in data or "serverUrl" in data or "type" in data:
        servers = {default_name or str(data.get("name") or ""): data}
    elif data and all(isinstance(v, dict) for v in data.values()):
        servers = data  # a bare map of servers
    else:
        raise ConnectionError_(
            "config_invalid", "No hay ningún servidor en el JSON: falta «mcpServers»."
        )
    drafts = []
    for name, raw in servers.items():
        if not name:
            raise ConnectionError_(
                "name_invalid", "Falta el nombre del servidor: pónselo en el formulario."
            )
        drafts.append(parse_server(str(name), raw))
    if not drafts:
        raise ConnectionError_("config_invalid", "No hay ningún servidor en el JSON.")
    return drafts


# -- checks -------------------------------------------------------------------------------------
def slug_name(text: str) -> str:
    """A name that passes `check_name`, made from any text."""
    name = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-_")[:40].strip("-_")
    return name or "conexion"


def check_name(name: str) -> str:
    if name in RESERVED:
        raise ConnectionError_(
            "name_reserved",
            f"«{name}» está reservado para el servidor de Agentic OS: elige otro nombre.",
            name=name,
        )
    if not NAME_RE.match(name) or "__" in name:
        raise ConnectionError_(
            "name_invalid",
            f"El nombre «{name}» no es válido: usa minúsculas, números, «-» o «_» (máximo 40, "
            "sin «__»). Es el nombre del servidor para el agente.",
            name=name,
        )
    return name


def check(draft: Draft) -> Draft:
    """Raises in words if the connection cannot work. Returns the draft."""
    check_name(draft.name)
    if draft.transport not in TRANSPORTS:
        raise ConnectionError_(
            "transport_invalid",
            f"El tipo «{draft.transport}» no existe: usa «stdio», «http» o «sse».",
            transport=draft.transport,
        )
    if draft.transport == "stdio":
        if not draft.command.strip():
            raise ConnectionError_(
                "command_missing",
                "Falta el comando: es el programa que arranca el servidor (por ejemplo «npx»).",
            )
    else:
        parsed = urlparse(draft.url.strip())
        if not draft.url.strip():
            raise ConnectionError_("url_missing", "Falta la dirección (URL) del servidor.")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConnectionError_(
                "url_invalid",
                f"La dirección «{draft.url}» no es válida: tiene que empezar por http:// o "
                "https://.",
                url=draft.url,
            )
    for key in draft.secret_keys:
        secrets.check_key(key)
    return draft


def export_server(draft_like) -> dict:
    """The `mcpServers` entry of a connection, without secrets: `${NAME}` instead of the
    placeholders (for sharing)."""

    def plain(text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: "${" + m.group(0)[2:-1].split(":", 1)[1] + "}", text)

    entry: dict = {}
    if draft_like.transport == "stdio":
        entry["command"] = draft_like.command
        if draft_like.args:
            entry["args"] = [plain(a) for a in draft_like.args]
        if draft_like.cwd:
            entry["cwd"] = draft_like.cwd
    else:
        entry["type"] = draft_like.transport
        entry["url"] = plain(draft_like.url)
        if draft_like.headers:
            entry["headers"] = {k: plain(v) for k, v in draft_like.headers.items()}
    if draft_like.env:
        entry["env"] = {k: plain(v) for k, v in draft_like.env.items()}
    return entry
