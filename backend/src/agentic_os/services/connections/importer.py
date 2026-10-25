"""Importing the MCP servers the person already has in their CLIs (phase 18, CA9).

Read only: the original files are never touched. The servers of `~/.claude.json` (global and the
ones of each project), of a project's `.mcp.json` and of `agy`'s `mcp_config.json` are listed;
the person picks which to import and at which level. The secrets found go to the credential
store (spike S6: there are `Authorization` headers in clear in real configurations).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import McpConnection, McpOriginKind, Project
from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import library
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.knowledge.docs import validate_level


@dataclass
class Found:
    id: str  # stable: the source, the file and the name
    source: str  # «claude», «claude-project», «mcp-json» or «agy»
    origin: str  # where, in words (a path or «global»)
    name: str
    draft: fmt.Draft
    imported: bool = False  # a connection with this name and the same command or URL exists

    def summary(self) -> dict:
        draft = self.draft
        return {
            "id": self.id,
            "source": self.source,
            "origin": self.origin,
            "name": self.name,
            "transport": draft.transport,
            "target": draft.url
            if draft.transport != "stdio"
            else " ".join([draft.command, *draft.args]).strip(),
            "env_keys": sorted(draft.env),
            "header_keys": sorted(draft.headers),
            "has_secrets": bool(draft.secrets),
            "ignored": draft.ignored,
            "imported": self.imported,
        }


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _found(source: str, origin: str, path: Path, name: str, raw: object) -> Found | None:
    try:
        draft = fmt.parse_server(name, raw)
    except ConnectionError_:
        return None  # an entry this app cannot read is simply not listed
    key = f"{source}|{path}|{name}"
    return Found(hashlib.sha1(key.encode()).hexdigest()[:16], source, origin, name, draft)


def scan(
    db: Session, claude_config: Path, agy_config: Path, extra_projects: list[Path] | None = None
) -> list[Found]:
    found: list[Found] = []
    seen_files: set[Path] = set()

    claude = _read_json(claude_config)
    for name, raw in (claude.get("mcpServers") or {}).items():
        if item := _found("claude", "Claude Code (global)", claude_config, name, raw):
            found.append(item)
    project_dirs: list[Path] = [Path(p) for p in (claude.get("projects") or {})]
    for folder, config in (claude.get("projects") or {}).items():
        for name, raw in ((config or {}).get("mcpServers") or {}).items():
            if item := _found(
                "claude-project", f"Claude Code · {folder}", claude_config, f"{name}", raw
            ):
                # The same name can exist in several projects: the file id keeps them apart.
                item.id = hashlib.sha1(f"claude-project|{folder}|{name}".encode()).hexdigest()[:16]
                found.append(item)

    # The projects of Agentic OS and the ones Claude knows may have a .mcp.json.
    folders = [Path(p.path) for p in db.scalars(select(Project)) if p.path]
    for folder in [*folders, *project_dirs, *(extra_projects or [])]:
        file = folder / ".mcp.json"
        if file in seen_files or not file.is_file():
            continue
        seen_files.add(file)
        for name, raw in (_read_json(file).get("mcpServers") or {}).items():
            if item := _found("mcp-json", f"{folder}", file, name, raw):
                found.append(item)

    for name, raw in (_read_json(agy_config).get("mcpServers") or {}).items():
        if item := _found("agy", "Antigravity (global)", agy_config, name, raw):
            found.append(item)

    existing = {c.name: c for c in library.list_all(db)}
    for item in found:
        current = existing.get(item.name)
        if current is not None:
            same = (current.command, current.url) == (item.draft.command, item.draft.url)
            item.imported = same
    return found


def import_items(
    db: Session,
    found: list[Found],
    choices: list[dict],
) -> tuple[list[McpConnection], list[dict]]:
    """Creates the chosen ones. Each choice: {id, scope, project_id?, agent_id?, name?}. A name
    that is taken gets a number (`name-2`); an entry that cannot be created is reported."""
    by_id = {f.id: f for f in found}
    created: list[McpConnection] = []
    problems: list[dict] = []
    for choice in choices:
        item = by_id.get(choice.get("id", ""))
        if item is None:
            problems.append({"id": choice.get("id"), "reason": "No se encontró esa entrada."})
            continue
        draft = item.draft
        draft.name = library.unique_name(db, choice.get("name") or item.name)
        scope = choice.get("scope", "general")
        try:
            # The level is checked first: nothing is created (or stored) for a level that fails.
            validate_level(db, scope, choice.get("project_id"), choice.get("agent_id"))
            connection = library.create(db, draft, origin=McpOriginKind.IMPORT)
            library.assign(db, connection, scope, choice.get("project_id"), choice.get("agent_id"))
        except Exception as error:
            reason = getattr(error, "message", None) or str(error)
            problems.append({"id": item.id, "name": item.name, "reason": reason})
            continue
        created.append(connection)
    return created, problems
