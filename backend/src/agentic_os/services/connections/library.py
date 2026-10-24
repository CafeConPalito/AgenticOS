"""The catalog of connections (phase 18): create, edit, switch off, delete and list, with their
secrets kept in the credential store and never in the database (CA2, CA3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import NotFound
from agentic_os.models import (
    McpAssignment,
    McpConnection,
    McpOriginKind,
    RunConnection,
    RunConnectionStatus,
    RunToolCall,
)
from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import secrets
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.knowledge.docs import validate_level

# What a change of changes what a run receives: the revision goes up (the run records it).
CONFIG_FIELDS = (
    "name",
    "transport",
    "command",
    "args",
    "cwd",
    "url",
    "env",
    "headers",
    "auth",
    "tool_mode",
    "allowed_tools",
    "preapproved_tools",
)
EDITABLE = (*CONFIG_FIELDS, "description", "icon", "enabled", "tools_changed")
# Secrets the app itself keeps for a connection (OAuth), apart from the ones the person declares.
RESERVED_PREFIX = "_oauth"


def get(db: Session, connection_id: str) -> McpConnection:
    connection = db.get(McpConnection, connection_id)
    if connection is None or connection.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("connection")
    return connection


def by_name(db: Session, name: str) -> McpConnection | None:
    return db.scalar(
        select(McpConnection).where(
            McpConnection.workspace_id == DEFAULT_WORKSPACE, McpConnection.name == name
        )
    )


def list_all(db: Session) -> list[McpConnection]:
    return list(
        db.scalars(
            select(McpConnection)
            .where(McpConnection.workspace_id == DEFAULT_WORKSPACE)
            .order_by(McpConnection.name)
        )
    )


def name_free(db: Session, name: str, except_id: str | None = None) -> None:
    other = by_name(db, name)
    if other is not None and other.id != except_id:
        raise ConnectionError_(
            "name_taken", f"Ya hay una conexión llamada «{name}»: elige otro nombre.", name=name
        )


def unique_name(db: Session, wanted: str) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`… if it is taken."""
    base = fmt.slug_name(wanted)
    name, number = base, 2
    while by_name(db, name) is not None:
        suffix = f"-{number}"
        name = f"{base[: 40 - len(suffix)]}{suffix}"
        number += 1
    return name


# -- create -------------------------------------------------------------------------------------
def create(
    db: Session, draft: fmt.Draft, *, origin: str = McpOriginKind.USER, auth: str | None = None
) -> McpConnection:
    """A new connection from a checked draft. The secret values of the draft go to the store."""
    fmt.check(draft)
    name_free(db, draft.name)
    connection = McpConnection(
        name=draft.name,
        description=draft.description,
        icon=draft.icon,
        transport=draft.transport,
        command=draft.command,
        args=list(draft.args),
        cwd=draft.cwd,
        url=draft.url,
        env=dict(draft.env),
        headers=dict(draft.headers),
        secret_keys=draft.secret_keys,
        auth=auth or draft.auth,
        origin=origin,
    )
    db.add(connection)
    db.flush()
    try:
        for key, value in draft.secrets.items():
            secrets.put(connection.id, key, value)
    except ConnectionError_:
        db.rollback()
        secrets.delete_all(connection.id, list(draft.secrets))
        raise
    return connection


# -- edit ---------------------------------------------------------------------------------------
def update(
    db: Session,
    connection: McpConnection,
    values: Mapping[str, Any],
    set_secrets: Mapping[str, str] | None = None,
    remove_secrets: list[str] | None = None,
) -> McpConnection:
    """Only the given fields change. A change of what a run receives raises the revision."""
    config_changed = bool(set_secrets or remove_secrets)
    new_name = values.get("name")
    if new_name and new_name != connection.name:
        fmt.check_name(new_name)
        name_free(db, new_name, connection.id)  # before the change: a flush would hit the index
    for field_name in EDITABLE:
        if field_name not in values or values[field_name] is None:
            continue
        value = values[field_name]
        if field_name in ("args", "allowed_tools", "preapproved_tools"):
            value = list(value)
        elif field_name in ("env", "headers"):
            value = dict(value)
        if getattr(connection, field_name) != value:
            setattr(connection, field_name, value)
            config_changed = config_changed or field_name in CONFIG_FIELDS
    draft = fmt.Draft(
        name=connection.name,
        transport=connection.transport,
        command=connection.command,
        args=connection.args,
        cwd=connection.cwd,
        url=connection.url,
        env=connection.env,
        headers=connection.headers,
    )
    fmt.check(draft)
    _check_tools(connection)
    for key, value in (set_secrets or {}).items():
        secrets.put(connection.id, key, value)
    for key in remove_secrets or []:
        secrets.delete(connection.id, key)
    declared = list(dict.fromkeys([*draft.secret_keys, *(set_secrets or {})]))
    gone = [
        k for k in connection.secret_keys if k not in declared and not k.startswith(RESERVED_PREFIX)
    ]
    secrets.delete_all(connection.id, gone)
    connection.secret_keys = declared
    if config_changed:
        connection.revision += 1
    connection.updated_at = utcnow()
    db.flush()
    return connection


def _check_tools(connection: McpConnection) -> None:
    """The tools the person allows or pre-approves have to be ones the server has (the ones the
    last test found). Before any test there is nothing to compare with."""
    known = {tool["name"] for tool in connection.tools}
    if not known:
        return
    for names in (connection.allowed_tools, connection.preapproved_tools):
        unknown = [n for n in names if n not in known]
        if unknown:
            raise ConnectionError_(
                "tool_unknown",
                f"El servidor «{connection.name}» no tiene la herramienta «{unknown[0]}». "
                "Vuelve a probar la conexión para ver las que tiene.",
                tool=unknown[0],
            )


def apply_probe(db: Session, connection: McpConnection, result) -> None:
    """Keeps what a test found. A failed test keeps the tools of the last good one."""
    connection.tested_at = utcnow()
    if result.ok:
        before = {tool["name"] for tool in connection.tools}
        after = {tool["name"] for tool in result.tools}
        connection.tools_changed = bool(before) and before != after
        connection.tools = result.tools
        connection.resources = result.resources
        connection.prompts = result.prompts
        connection.test_error = None
    else:
        connection.test_error = result.error.as_dict()
    db.flush()


def set_secret(db: Session, connection: McpConnection, key: str, value: str) -> None:
    secrets.check_key(key)
    secrets.put(connection.id, key, value)
    if key not in connection.secret_keys:
        connection.secret_keys = [*connection.secret_keys, key]
    connection.revision += 1
    db.flush()


def clear_secret(db: Session, connection: McpConnection, key: str) -> None:
    secrets.delete(connection.id, key)
    connection.revision += 1
    db.flush()


def delete(db: Session, connection: McpConnection) -> None:
    """The connection, what hangs from it (levels, exclusions, login) and its secrets. The calls
    it received stay in the runs, under its name."""
    secrets.delete_all(connection.id, [*connection.secret_keys, "_oauth_tokens", "_oauth_client"])
    db.delete(connection)
    db.flush()


# -- levels -------------------------------------------------------------------------------------
def assign(
    db: Session,
    connection: McpConnection,
    scope: str,
    project_id: str | None = None,
    agent_id: str | None = None,
) -> McpAssignment:
    validate_level(db, scope, project_id, agent_id)
    existing = db.scalar(
        select(McpAssignment).where(
            McpAssignment.connection_id == connection.id,
            McpAssignment.scope == scope,
            McpAssignment.project_id.is_(None)
            if project_id is None
            else McpAssignment.project_id == project_id,
            McpAssignment.agent_id.is_(None)
            if agent_id is None
            else McpAssignment.agent_id == agent_id,
        )
    )
    if existing is not None:
        return existing
    row = McpAssignment(
        connection_id=connection.id, scope=scope, project_id=project_id, agent_id=agent_id
    )
    db.add(row)
    db.flush()
    return row


def assignments(db: Session, connection_id: str) -> list[McpAssignment]:
    return list(
        db.scalars(
            select(McpAssignment)
            .where(McpAssignment.connection_id == connection_id)
            .order_by(McpAssignment.created_at)
        )
    )


# -- usage --------------------------------------------------------------------------------------
@dataclass
class Usage:
    received_runs: int = 0
    used_runs: int = 0
    calls: int = 0
    failed_calls: int = 0
    last_used: Any = None


def usage(db: Session, names: list[str]) -> dict[str, Usage]:
    """What each connection has done, by name (it survives the deletion of the connection)."""
    out = {name: Usage() for name in names}
    if not names:
        return out
    received = db.execute(
        select(RunConnection.connection_name, func.count(distinct(RunConnection.run_id)))
        .where(
            RunConnection.connection_name.in_(names),
            RunConnection.status != RunConnectionStatus.SKIPPED,
        )
        .group_by(RunConnection.connection_name)
    )
    for name, count in received:
        out[name].received_runs = count
    calls = db.execute(
        select(
            RunToolCall.connection_name,
            func.count(distinct(RunToolCall.run_id)),
            func.count(RunToolCall.id),
            func.sum(case((RunToolCall.ok.is_(False), 1), else_=0)),
            func.max(RunToolCall.started_at),
        )
        .where(RunToolCall.connection_name.in_(names))
        .group_by(RunToolCall.connection_name)
    )
    for name, runs, total, failed, last in calls:
        out[name].used_runs, out[name].calls = runs, total
        out[name].failed_calls, out[name].last_used = int(failed or 0), last
    return out


# -- as a draft / as JSON -----------------------------------------------------------------------
def to_draft(connection: McpConnection) -> fmt.Draft:
    return fmt.Draft(
        name=connection.name,
        transport=connection.transport,
        command=connection.command,
        args=list(connection.args),
        cwd=connection.cwd,
        url=connection.url,
        env=dict(connection.env),
        headers=dict(connection.headers),
        description=connection.description,
        icon=connection.icon,
        auth=connection.auth,
    )


def export(connection: McpConnection) -> dict:
    """The `mcpServers` block of one connection, without secrets (`${NAME}` instead)."""
    return {"mcpServers": {connection.name: fmt.export_server(to_draft(connection))}}
