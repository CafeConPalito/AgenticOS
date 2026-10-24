"""MCP connections (phase 18): the catalog, its secrets, the templates and the import."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.models import McpAssignment, McpConnection, McpOAuth, McpOrigin
from agentic_os.schemas.connections import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionSettingsRead,
    ConnectionSettingsWrite,
    ConnectionUpdate,
    DraftRead,
    FoundRead,
    FromTemplate,
    ImportProblem,
    ImportRequest,
    ImportResult,
    ParseRead,
    ParseRequest,
    SecretWrite,
    TemplateRead,
    read_connection,
)
from agentic_os.services.connections import config as connection_config
from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import importer, library, templates
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.trust import claude_config

router = APIRouter(tags=["connections"])
# Fixed paths (/connections/<word>): registered before /connections/{connection_id}.
static = APIRouter(tags=["connections"])
DbSession = Annotated[Session, Depends(get_session)]


def _read_many(db: Session, connections: list[McpConnection]) -> list[ConnectionRead]:
    ids = [c.id for c in connections]
    assigned: dict[str, list[McpAssignment]] = {}
    for row in db.scalars(
        select(McpAssignment)
        .where(McpAssignment.connection_id.in_(ids))
        .order_by(McpAssignment.created_at)
    ):
        assigned.setdefault(row.connection_id, []).append(row)
    oauth = {
        o.connection_id: o
        for o in db.scalars(select(McpOAuth).where(McpOAuth.connection_id.in_(ids)))
    }
    origins = {
        o.connection_id: o
        for o in db.scalars(select(McpOrigin).where(McpOrigin.connection_id.in_(ids)))
    }
    used = library.usage(db, [c.name for c in connections])
    return [
        read_connection(
            c, assigned.get(c.id, []), used.get(c.name), oauth.get(c.id), origins.get(c.id)
        )
        for c in connections
    ]


def _read(db: Session, connection: McpConnection) -> ConnectionRead:
    return _read_many(db, [connection])[0]


def _created(db: Session, draft: fmt.Draft, level, origin: str, auth: str | None = None):
    connection = library.create(db, draft, origin=origin, auth=auth)
    if level is not None:
        library.assign(db, connection, level.scope, level.project_id, level.agent_id)
    db.commit()
    return connection


# -------------------------------------------------------------------- static paths
@static.get("/connections/templates")
def list_templates() -> list[TemplateRead]:
    return [TemplateRead(**templates.card(t)) for t in templates.TEMPLATES]


@static.post("/connections/from-template", status_code=status.HTTP_201_CREATED)
def from_template(payload: FromTemplate, db: DbSession) -> ConnectionRead:
    draft = templates.build(payload.template, payload.values, payload.name)
    if not payload.name:
        draft.name = library.unique_name(db, draft.name)
    connection = _created(db, draft, payload.level, "template")
    return _read(db, connection)


@static.post("/connections/parse")
def parse(payload: ParseRequest) -> ParseRead:
    """What a pasted JSON would create, to review it. The secret values stay out of the answer."""
    drafts = fmt.parse_servers(payload.text, payload.name)
    return ParseRead(
        servers=[
            DraftRead(
                name=d.name,
                transport=d.transport,
                command=d.command,
                args=d.args,
                cwd=d.cwd,
                url=d.url,
                env=d.env,
                headers=d.headers,
                secret_keys=d.secret_keys,
                ignored=d.ignored,
            )
            for d in drafts
        ]
    )


def _scan(request: Request, db: Session) -> list[importer.Found]:
    settings = request.app.state.settings
    claude = settings.claude_config_file or claude_config()
    from agentic_os.services.trust import agy_settings

    agy = settings.agy_mcp_config_file or (
        agy_settings().parent.parent / "config" / "mcp_config.json"
    )
    return importer.scan(db, claude, agy)


@static.get("/connections/import/scan")
def scan_cli_connections(request: Request, db: DbSession) -> list[FoundRead]:
    return [FoundRead(**item.summary()) for item in _scan(request, db)]


@static.post("/connections/import", status_code=status.HTTP_201_CREATED)
def import_cli_connections(payload: ImportRequest, request: Request, db: DbSession) -> ImportResult:
    created, problems = importer.import_items(
        db, _scan(request, db), [item.model_dump() for item in payload.items]
    )
    db.commit()
    return ImportResult(
        created=_read_many(db, created), problems=[ImportProblem(**p) for p in problems]
    )


def _settings_read(db: Session) -> ConnectionSettingsRead:
    values = connection_config.load(db)
    return ConnectionSettingsRead(**values.__dict__)


@static.get("/settings/connections")
def get_connection_settings(db: DbSession) -> ConnectionSettingsRead:
    return _settings_read(db)


@static.put("/settings/connections")
def put_connection_settings(
    payload: ConnectionSettingsWrite, db: DbSession
) -> ConnectionSettingsRead:
    connection_config.save(db, payload.model_dump(exclude_none=True))
    db.commit()
    return _settings_read(db)


# -------------------------------------------------------------------- the catalog
@router.get("/connections")
def list_connections(db: DbSession) -> list[ConnectionRead]:
    return _read_many(db, library.list_all(db))


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(payload: ConnectionCreate, db: DbSession) -> list[ConnectionRead]:
    """One connection from the form, or one or more from a pasted `mcpServers` block."""
    if payload.json_text is not None:
        drafts = fmt.parse_servers(payload.json_text, payload.name)
        if payload.name and len(drafts) > 1:
            drafts = [d for d in drafts if d.name == payload.name] or drafts
    else:
        drafts = [
            fmt.Draft(
                name=payload.name,
                transport=payload.transport,
                command=payload.command,
                args=payload.args,
                cwd=payload.cwd,
                url=payload.url,
                env=payload.env,
                headers=payload.headers,
                description=payload.description,
                icon=payload.icon,
                auth=payload.auth,
                secrets=dict(payload.secrets),
            )
        ]
    created = []
    for draft in drafts:
        if payload.json_text is not None and payload.description:
            draft.description = payload.description
        connection = library.create(db, draft, origin="user", auth=draft.auth)
        if payload.level is not None:
            lvl = payload.level
            library.assign(db, connection, lvl.scope, lvl.project_id, lvl.agent_id)
        created.append(connection)
    db.commit()
    return _read_many(db, created)


@router.get("/connections/{connection_id}")
def get_connection(connection_id: str, db: DbSession) -> ConnectionRead:
    return _read(db, library.get(db, connection_id))


@router.patch("/connections/{connection_id}")
def update_connection(
    connection_id: str, payload: ConnectionUpdate, db: DbSession
) -> ConnectionRead:
    connection = library.get(db, connection_id)
    values = payload.model_dump(exclude_unset=True, exclude={"secrets", "remove_secrets"})
    library.update(db, connection, values, payload.secrets, payload.remove_secrets)
    db.commit()
    return _read(db, connection)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, db: DbSession) -> Response:
    library.delete(db, library.get(db, connection_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/connections/{connection_id}/secrets/{key}")
def put_secret(connection_id: str, key: str, payload: SecretWrite, db: DbSession) -> ConnectionRead:
    connection = library.get(db, connection_id)
    if key.startswith(library.RESERVED_PREFIX):
        raise ConnectionError_("secret_key_invalid", "Ese nombre está reservado.", key=key)
    library.set_secret(db, connection, key, payload.value)
    db.commit()
    return _read(db, connection)


@router.delete("/connections/{connection_id}/secrets/{key}")
def delete_secret(connection_id: str, key: str, db: DbSession) -> ConnectionRead:
    connection = library.get(db, connection_id)
    if key.startswith(library.RESERVED_PREFIX):
        raise ConnectionError_("secret_key_invalid", "Ese nombre está reservado.", key=key)
    library.clear_secret(db, connection, key)
    db.commit()
    return _read(db, connection)


@router.get("/connections/{connection_id}/export")
def export_connection(connection_id: str, db: DbSession) -> dict:
    """The `mcpServers` JSON, without secrets (`${NAME}` where they were)."""
    return library.export(library.get(db, connection_id))
