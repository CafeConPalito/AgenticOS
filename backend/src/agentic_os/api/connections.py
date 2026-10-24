"""MCP connections (phase 18): the catalog, its secrets, the templates and the import."""

import shutil
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.errors import NotFound
from agentic_os.models import (
    Agent,
    McpAssignment,
    McpConnection,
    McpOAuth,
    McpOrigin,
    Pipeline,
    Stage,
)
from agentic_os.schemas.connections import (
    AgentConnectionsRead,
    AssignmentRead,
    ConnectionCreate,
    ConnectionRead,
    ConnectionSettingsRead,
    ConnectionSettingsWrite,
    ConnectionUpdate,
    DraftRead,
    EffectiveRead,
    ExcludedRead,
    ExclusionsWrite,
    FlowRead,
    FoundRead,
    FromTemplate,
    ImportProblem,
    ImportRequest,
    ImportResult,
    OAuthStart,
    ParseRead,
    ParseRequest,
    PreviewRead,
    RequirementRead,
    SecretWrite,
    StageConnectionsRead,
    TemplateRead,
    TestRead,
    TryRequest,
    brief,
    read_connection,
)
from agentic_os.schemas.knowledge import Level
from agentic_os.services.connections import config as connection_config
from agentic_os.services.connections import format as fmt
from agentic_os.services.connections import importer, library, oauth, probe, resolve, templates
from agentic_os.services.connections.errors import ConnectionError_
from agentic_os.services.connections.render import render
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


def _flow_read(db: Session, flow: oauth.Flow) -> FlowRead:
    connection = None
    if flow.state == "done":
        row = db.get(McpConnection, flow.connection_id)
        if row is not None:
            db.refresh(row)
            connection = _read(db, row)
    return FlowRead(
        id=flow.id,
        connection_id=flow.connection_id,
        state=flow.state,
        authorization_url=flow.authorization_url,
        redirect_uri=flow.redirect_uri,
        error=flow.error,
        connection=connection,
    )


@static.get("/connections/oauth/flows/{flow_id}")
def get_oauth_flow(flow_id: str, request: Request, db: DbSession) -> FlowRead:
    flow = request.app.state.oauth_flows.get(flow_id)
    if flow is None:
        raise NotFound("flow")
    return _flow_read(db, flow)


@static.delete("/connections/oauth/flows/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_oauth_flow(flow_id: str, request: Request) -> Response:
    if not request.app.state.oauth_flows.cancel(flow_id):
        raise NotFound("flow")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


PROGRAMS = ("node", "npx", "uvx", "uv", "python", "docker", "git")


@static.get("/connections/requirements")
def requirements() -> list[RequirementRead]:
    """Which of the programs the servers usually need are installed."""
    return [
        RequirementRead(program=p, found=bool(shutil.which(p)), path=shutil.which(p) or "")
        for p in PROGRAMS
    ]


def _test_read(request: Request, db: Session, test: probe.Test) -> TestRead:
    connection = None
    if test.state == "done":
        row = db.get(McpConnection, test.connection_id)
        if row is not None:
            db.refresh(row)
            connection = _read(db, row)
    return TestRead(
        id=test.id,
        connection_id=test.connection_id,
        state=test.state,
        seconds=round(time.monotonic() - test.started_at, 1),
        result=test.result.as_dict() if test.result else None,
        connection=connection,
    )


@static.get("/connections/tests/{test_id}")
def get_test(test_id: str, request: Request, db: DbSession) -> TestRead:
    test = request.app.state.connection_probes.get(test_id)
    if test is None:
        raise NotFound("test")
    return _test_read(request, db, test)


@static.delete("/connections/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_test(test_id: str, request: Request) -> Response:
    if not request.app.state.connection_probes.cancel(test_id):
        raise NotFound("test")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post("/connections/{connection_id}/test", status_code=status.HTTP_202_ACCEPTED)
def test_connection(
    connection_id: str,
    request: Request,
    db: DbSession,
    wait: Annotated[bool, Query()] = False,
) -> TestRead:
    """Starts the server (or calls its URL) as an MCP client and lists what it offers. It runs in
    the background; `wait=true` waits for it."""
    connection = library.get(db, connection_id)
    rendered = render(connection)  # a missing secret is explained here, before starting anything
    auth = None
    if connection.auth == "oauth":
        login = db.get(McpOAuth, connection.id)
        if login is None or login.status != "connected":
            raise ConnectionError_(
                "oauth_needs_login", f"Conecta la cuenta de «{connection.name}» antes de probarla."
            )
        auth = oauth.provider_for(connection)
    timeout = connection_config.load(db).probe_timeout
    sessionmaker = request.app.state.sessionmaker

    def keep(test: probe.Test) -> None:
        with sessionmaker() as session:
            row = session.get(McpConnection, connection_id)
            if row is not None and test.result is not None:
                library.apply_probe(session, row, test.result)
                session.commit()

    test = request.app.state.connection_probes.start(
        connection_id, rendered, timeout, auth=auth, on_done=keep
    )
    if wait:
        test.done.wait(timeout + 10)
    return _test_read(request, db, test)


# -------------------------------------------------------------------- who gets what (block 4)
@router.get("/connections/{connection_id}/assignments")
def list_assignments(connection_id: str, db: DbSession) -> list[AssignmentRead]:
    library.get(db, connection_id)
    return [
        AssignmentRead(id=a.id, scope=a.scope, project_id=a.project_id, agent_id=a.agent_id)
        for a in library.assignments(db, connection_id)
    ]


@router.post("/connections/{connection_id}/assignments", status_code=status.HTTP_201_CREATED)
def add_assignment(connection_id: str, level: Level, db: DbSession) -> ConnectionRead:
    """Gives the connection to a level (general, a project or an agent). Idempotent."""
    connection = library.get(db, connection_id)
    library.assign(db, connection, level.scope, level.project_id, level.agent_id)
    db.commit()
    return _read(db, connection)


@router.delete(
    "/connections/{connection_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_assignment(connection_id: str, assignment_id: str, db: DbSession) -> Response:
    library.unassign(db, library.get(db, connection_id), assignment_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _preview(report: resolve.Report) -> dict:
    return {
        "effective": [
            EffectiveRead(
                connection=brief(e.connection), level=e.level, tools=len(e.tools), tokens=e.tokens
            )
            for e in report.effective
        ],
        "excluded": [
            ExcludedRead(connection=brief(x.connection), level=x.level, reason=x.reason)
            for x in report.excluded
        ],
        "total_tools": report.total_tools,
        "total_tokens": report.total_tokens,
    }


def _stage(db: Session, stage_id: str) -> tuple[Stage, Pipeline]:
    stage = db.get(Stage, stage_id)
    if stage is None:
        raise NotFound("stage")
    return stage, db.get(Pipeline, stage.pipeline_id)


@static.post("/connections/try")
def try_resolution(payload: TryRequest, db: DbSession) -> PreviewRead:
    """What a run of this agent, in this project and stage, would receive."""
    project_id, agent_id = payload.project_id, payload.agent_id
    if payload.stage_id:
        stage, pipeline = _stage(db, payload.stage_id)
        agent_id = agent_id or stage.agent_id
        project_id = project_id or pipeline.project_id
    return PreviewRead(**_preview(resolve.resolve(db, agent_id, project_id, payload.stage_id)))


@router.get("/agents/{agent_id}/connections")
def get_agent_connections(
    agent_id: str, db: DbSession, project_id: Annotated[str | None, Query()] = None
) -> AgentConnectionsRead:
    """What an agent receives (in a project, if given), what is taken away from it and what
    could still be given to it."""
    if db.get(Agent, agent_id) is None:
        raise NotFound("agent")
    report = resolve.resolve(db, agent_id, project_id, None)
    given = set(
        db.scalars(select(McpAssignment.connection_id).where(McpAssignment.agent_id == agent_id))
    )
    return AgentConnectionsRead(
        **_preview(report),
        excluded_ids=resolve.excluded_ids(db, agent_id=agent_id),
        available=[brief(c) for c in library.list_all(db) if c.id not in given],
    )


@router.put("/agents/{agent_id}/connections")
def put_agent_connections(
    agent_id: str,
    payload: ExclusionsWrite,
    db: DbSession,
    project_id: Annotated[str | None, Query()] = None,
) -> AgentConnectionsRead:
    """Replaces the connections taken away from the agent."""
    if db.get(Agent, agent_id) is None:
        raise NotFound("agent")
    resolve.set_exclusions(db, payload.excluded, agent_id=agent_id)
    db.commit()
    return get_agent_connections(agent_id, db, project_id)


@router.get("/stages/{stage_id}/connections")
def get_stage_connections(stage_id: str, db: DbSession) -> StageConnectionsRead:
    """What a run of this stage receives (its agent's, its project's and the general ones, minus
    what the agent and the stage take away)."""
    stage, pipeline = _stage(db, stage_id)
    report = resolve.resolve(db, stage.agent_id, pipeline.project_id, stage.id)
    return StageConnectionsRead(
        **_preview(report),
        excluded_ids=resolve.excluded_ids(db, stage_id=stage.id),
        agent_id=stage.agent_id,
    )


@router.put("/stages/{stage_id}/connections")
def put_stage_connections(
    stage_id: str, payload: ExclusionsWrite, db: DbSession
) -> StageConnectionsRead:
    _stage(db, stage_id)
    resolve.set_exclusions(db, payload.excluded, stage_id=stage_id)
    db.commit()
    return get_stage_connections(stage_id, db)


# -------------------------------------------------------------------- OAuth (block 6)
def _oauth_connection(db: Session, connection_id: str) -> McpConnection:
    connection = library.get(db, connection_id)
    if connection.auth != "oauth" or connection.transport == "stdio":
        raise ConnectionError_(
            "oauth_not_applicable",
            "Esta conexión no inicia sesión con OAuth: solo las remotas (HTTP) que lo piden.",
        )
    return connection


@router.post("/connections/{connection_id}/oauth/start")
def start_oauth(
    connection_id: str, payload: OAuthStart, request: Request, db: DbSession
) -> FlowRead:
    """Starts the login: the answer holds the page the person has to open in the browser."""
    connection = _oauth_connection(db, connection_id)
    flow = request.app.state.oauth_flows.start(
        connection, oauth.settings_port(db), payload.client_id, payload.client_secret
    )
    return _flow_read(db, flow)


@router.post("/connections/{connection_id}/oauth/disconnect")
def disconnect_oauth(connection_id: str, db: DbSession) -> ConnectionRead:
    connection = _oauth_connection(db, connection_id)
    oauth.disconnect(db, connection)
    db.commit()
    return _read(db, connection)


@router.post("/connections/{connection_id}/oauth/refresh")
def refresh_oauth(connection_id: str, db: DbSession) -> ConnectionRead:
    """Renews the token now (it is done by itself before a run when it is about to expire)."""
    connection = _oauth_connection(db, connection_id)
    try:
        oauth.renew(db, connection)
    except oauth.NeedsLogin as problem:
        db.commit()
        raise ConnectionError_("oauth_needs_login", problem.message) from problem
    db.commit()
    return _read(db, connection)
