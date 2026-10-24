"""API shapes of the MCP connections (phase 18). A secret value never appears in a response:
only whether each declared secret is set."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentic_os.models import McpAssignment, McpConnection, McpOAuth, McpOrigin
from agentic_os.schemas.knowledge import Level
from agentic_os.services.connections import secrets as secret_store
from agentic_os.services.connections.library import Usage

Transport = Literal["stdio", "http", "sse"]
Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class SecretStatus(BaseModel):
    key: str
    set: bool


class AssignmentRead(BaseModel):
    id: str
    scope: str
    project_id: str | None
    agent_id: str | None


class UsageRead(BaseModel):
    received_runs: int = 0
    used_runs: int = 0
    calls: int = 0
    failed_calls: int = 0
    last_used: datetime | None = None


class OAuthRead(BaseModel):
    status: str
    account_label: str
    expires_at: datetime | None
    client_pasted: bool
    redirect_uri: str


class OriginRead(BaseModel):
    source: str
    ref: str
    package_type: str
    package: str
    version: str
    repo_url: str
    license: str
    official: bool
    latest_version: str
    update_available: bool


class ToolRead(BaseModel):
    name: str
    description: str = ""
    read_only: bool | None = None
    destructive: bool | None = None
    input_schema: dict = Field(default_factory=dict)


class ConnectionRead(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    transport: str
    command: str
    args: list[str]
    cwd: str
    url: str
    env: dict[str, str]
    headers: dict[str, str]
    secrets: list[SecretStatus]
    auth: str
    enabled: bool
    tools: list[ToolRead]
    resources: list[dict]
    prompts: list[dict]
    tested_at: datetime | None
    test_error: dict | None
    tools_changed: bool
    tool_mode: str
    allowed_tools: list[str]
    preapproved_tools: list[str]
    origin: str
    revision: int
    assignments: list[AssignmentRead]
    usage: UsageRead
    oauth: OAuthRead | None
    registry: OriginRead | None
    created_at: datetime
    updated_at: datetime


def read_connection(
    connection: McpConnection,
    assignments: list[McpAssignment],
    usage: Usage | None,
    oauth: McpOAuth | None,
    origin: McpOrigin | None,
) -> ConnectionRead:
    status = secret_store.status(connection.id, connection.secret_keys)
    used = usage or Usage()
    return ConnectionRead(
        id=connection.id,
        name=connection.name,
        description=connection.description,
        icon=connection.icon,
        transport=connection.transport,
        command=connection.command,
        args=connection.args,
        cwd=connection.cwd,
        url=connection.url,
        env=connection.env,
        headers=connection.headers,
        secrets=[SecretStatus(key=k, set=status[k]) for k in connection.secret_keys],
        auth=connection.auth,
        enabled=connection.enabled,
        tools=[ToolRead(**tool) for tool in connection.tools],
        resources=connection.resources,
        prompts=connection.prompts,
        tested_at=connection.tested_at,
        test_error=connection.test_error,
        tools_changed=connection.tools_changed,
        tool_mode=connection.tool_mode,
        allowed_tools=connection.allowed_tools,
        preapproved_tools=connection.preapproved_tools,
        origin=connection.origin,
        revision=connection.revision,
        assignments=[
            AssignmentRead(id=a.id, scope=a.scope, project_id=a.project_id, agent_id=a.agent_id)
            for a in assignments
        ],
        usage=UsageRead(
            received_runs=used.received_runs,
            used_runs=used.used_runs,
            calls=used.calls,
            failed_calls=used.failed_calls,
            last_used=used.last_used,
        ),
        oauth=(
            OAuthRead(
                status=oauth.status,
                account_label=oauth.account_label,
                expires_at=oauth.expires_at,
                client_pasted=oauth.client_pasted,
                redirect_uri=oauth.redirect_uri,
            )
            if oauth
            else None
        ),
        registry=(
            OriginRead(
                source=origin.source,
                ref=origin.ref,
                package_type=origin.package_type,
                package=origin.package,
                version=origin.version,
                repo_url=origin.repo_url,
                license=origin.license,
                official=origin.official,
                latest_version=origin.latest_version,
                update_available=bool(origin.latest_version)
                and origin.latest_version != origin.version,
            )
            if origin
            else None
        ),
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


# -- writes -------------------------------------------------------------------------------------
class ConnectionCreate(BaseModel):
    """A connection from the form (`name` and the transport's fields) or from pasted JSON
    (`json_text`, with `name` only when the JSON is a single server without a name). The values
    of the declared secrets go in `secrets` and are never returned."""

    model_config = ConfigDict(extra="forbid")

    name: Text = ""
    description: str = ""
    icon: str = ""
    transport: Transport = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    cwd: str = ""
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    auth: Literal["none", "oauth"] = "none"
    secrets: dict[str, str] = Field(default_factory=dict)
    json_text: str | None = None
    level: Level | None = None  # where to give it right away (none: only in the catalog)


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Text | None = None
    description: str | None = None
    icon: str | None = None
    transport: Transport | None = None
    command: str | None = None
    args: list[str] | None = None
    cwd: str | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    auth: Literal["none", "oauth"] | None = None
    enabled: bool | None = None
    tool_mode: Literal["all", "selected"] | None = None
    allowed_tools: list[str] | None = None
    preapproved_tools: list[str] | None = None
    tools_changed: bool | None = None  # false: the person has seen the change
    secrets: dict[str, str] | None = None  # values to set
    remove_secrets: list[str] | None = None


class SecretWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=20_000)


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    name: Text = ""


class DraftRead(BaseModel):
    name: str
    transport: str
    command: str
    args: list[str]
    cwd: str
    url: str
    env: dict[str, str]
    headers: dict[str, str]
    secret_keys: list[str]  # the secrets it would store (their values are not returned)
    ignored: list[str]


class ParseRead(BaseModel):
    servers: list[DraftRead]


class FromTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str
    name: Text = ""
    values: dict[str, str] = Field(default_factory=dict)
    level: Level | None = None


class TemplateFieldRead(BaseModel):
    key: str
    label: str
    secret: bool
    required: bool
    kind: str
    help: str
    help_url: str


class TemplateRead(BaseModel):
    id: str
    name: str
    description: str
    transport: str
    auth: str
    icon: str
    requires: list[str]
    official: bool
    docs_url: str
    command: str
    url: str
    fields: list[TemplateFieldRead]


class FoundRead(BaseModel):
    id: str
    source: str
    origin: str
    name: str
    transport: str
    target: str
    env_keys: list[str]
    header_keys: list[str]
    has_secrets: bool
    ignored: list[str]
    imported: bool


class ImportChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: Text = ""
    scope: Literal["general", "project", "agent"] = "general"
    project_id: str | None = None
    agent_id: str | None = None


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImportChoice] = Field(min_length=1, max_length=200)


class ImportProblem(BaseModel):
    id: str | None = None
    name: str = ""
    reason: str


class ImportResult(BaseModel):
    created: list[ConnectionRead]
    problems: list[ImportProblem]


class ConnectionSettingsRead(BaseModel):
    probe_timeout: int
    startup_timeout: int
    agy_grace: int
    oauth_port: int
    registries: dict[str, bool]


class ConnectionSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_timeout: int | None = None
    startup_timeout: int | None = None
    agy_grace: int | None = None
    oauth_port: int | None = None
    registries: dict[str, bool] | None = None


class TestRead(BaseModel):
    __test__ = False  # pytest: not a test class

    id: str
    connection_id: str
    state: Literal["running", "done", "cancelled"]
    seconds: float
    result: dict | None = None
    connection: ConnectionRead | None = None


class RequirementRead(BaseModel):
    program: str
    found: bool
    path: str = ""
