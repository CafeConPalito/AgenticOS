"""MCP connections (phase 18): external MCP servers the agents can use.

A connection is one server (a local command or a URL) with its settings. It is global: the
person assigns it to a level (general, project, agent) and can take it away from an agent or a
pipeline stage. Secret values are never kept here: `env`, `headers`, `args` and `url` hold
placeholders (`${secret:KEY}`, `${env:NAME}`) and the secrets live in the system's credential
store (`services/connections/secrets.py`). See docs/adr/0025-mcp-connections.md.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_os.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, WorkspaceMixin, utcnow
from agentic_os.models.knowledge import KnowledgeScope


class McpTransport(StrEnum):
    STDIO = "stdio"  # a command the CLI starts
    HTTP = "http"  # streamable HTTP
    SSE = "sse"  # legacy HTTP+SSE (Claude only: agy does not support it, spike S2)


class McpAuth(StrEnum):
    NONE = "none"
    OAUTH = "oauth"


class McpToolMode(StrEnum):
    ALL = "all"
    SELECTED = "selected"


class McpOriginKind(StrEnum):
    USER = "user"
    TEMPLATE = "template"
    IMPORT = "import"  # from the CLIs' own configuration
    REGISTRY = "registry"  # installed from a public registry


class OAuthStatus(StrEnum):
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"  # the refresh failed: the person has to connect again
    DISCONNECTED = "disconnected"


class RunConnectionStatus(StrEnum):
    SENT = "sent"  # written into the CLI's configuration
    CONNECTED = "connected"  # the CLI said it connected, or a call went through
    FAILED = "failed"  # it did not start or connect
    SKIPPED = "skipped"  # not sent (OAuth expired, a secret is missing, SSE in agy…)


def _in(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class McpConnection(IdMixin, WorkspaceMixin, TimestampMixin, Base):
    __tablename__ = "mcp_connections"
    __table_args__ = (
        CheckConstraint(_in("transport", McpTransport), name="transport"),
        CheckConstraint(_in("auth", McpAuth), name="auth"),
        CheckConstraint(_in("tool_mode", McpToolMode), name="tool_mode"),
        CheckConstraint(_in("origin", McpOriginKind), name="origin"),
        Index("uq_mcp_connections_name", "workspace_id", "name", unique=True),
    )

    # The server's name in the CLI: `mcp__<name>__<tool>` in Claude, `agentic-os_<name>` in agy.
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    transport: Mapped[str] = mapped_column(String(8), nullable=False, default=McpTransport.STDIO)
    command: Mapped[str] = mapped_column(Text, nullable=False, default="")
    args: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cwd: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    env: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    # Keys of the secrets this connection uses (the values are in the credential store).
    secret_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    auth: Mapped[str] = mapped_column(String(8), nullable=False, default=McpAuth.NONE)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # What the last test found: [{name, description, input_schema, read_only, destructive}].
    tools: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    resources: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    prompts: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    test_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tools_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tool_mode: Mapped[str] = mapped_column(String(8), nullable=False, default=McpToolMode.ALL)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Tools that need no permission in the restricted / ask modes.
    preapproved_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    origin: Mapped[str] = mapped_column(String(8), nullable=False, default=McpOriginKind.USER)
    # Goes up with every change of configuration: a run records the one it received.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class McpAssignment(IdMixin, Base):
    """A connection given to a level. One connection can be given to many projects or agents."""

    __tablename__ = "mcp_assignments"
    __table_args__ = (
        CheckConstraint(_in("scope", KnowledgeScope), name="scope"),
        CheckConstraint(
            "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
            " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
            " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)",
            name="level",
        ),
        # NULLs are distinct in a unique index: the level goes through a coalesce.
        Index(
            "uq_mcp_assignments_level",
            "connection_id",
            "scope",
            text("coalesce(project_id, '')"),
            text("coalesce(agent_id, '')"),
            unique=True,
        ),
    )

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class McpExclusion(IdMixin, Base):
    """A connection taken away from one agent or from one pipeline stage (a branch is a stage)."""

    __tablename__ = "mcp_exclusions"
    __table_args__ = (
        CheckConstraint("(agent_id IS NULL) != (stage_id IS NULL)", name="target"),
        UniqueConstraint("connection_id", "agent_id", name="uq_mcp_exclusions_agent"),
        UniqueConstraint("connection_id", "stage_id", name="uq_mcp_exclusions_stage"),
    )

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stages.id", ondelete="CASCADE"), nullable=True, index=True
    )


class McpOAuth(Base):
    """The OAuth login of a connection. The tokens and the client secret are in the credential
    store, never here."""

    __tablename__ = "mcp_oauth"
    __table_args__ = (CheckConstraint(_in("status", OAuthStatus), name="status"),)

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_connections.id", ondelete="CASCADE"), primary_key=True
    )
    issuer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # True when the person pasted the client id (no dynamic registration): the redirect URI
    # has to be exactly the one registered at the service (spike S3).
    client_pasted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OAuthStatus.DISCONNECTED
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )


class McpOrigin(Base):
    """Where a connection installed from a public registry came from, to offer its updates."""

    __tablename__ = "mcp_origins"

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mcp_connections.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False)  # registry module (S4)
    ref: Mapped[str] = mapped_column(Text, nullable=False)  # the server's id in the registry
    package_type: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    package: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    repo_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    license: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latest_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # What was installed (command, variables, declared tools), to show what an update changes.
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class RunConnection(IdMixin, Base):
    """A connection a run received (or should have) and what happened to it."""

    __tablename__ = "run_connections"
    __table_args__ = (
        CheckConstraint(_in("status", RunConnectionStatus), name="status"),
        UniqueConstraint("run_id", "connection_name", name="uq_run_connections_pair"),
    )

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mcp_connections.id", ondelete="SET NULL"), nullable=True
    )
    connection_name: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The level it came from («general», «project», «agent»), for the run page.
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class RunToolCall(IdMixin, Base):
    """A call to a tool of an external server during a run. The usage of a connection comes
    from here and survives the deletion of the connection (its name is copied)."""

    __tablename__ = "run_tool_calls"
    __table_args__ = (Index("ix_run_tool_calls_name_started", "connection_name", "started_at"),)

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_name: Mapped[str] = mapped_column(String(40), nullable=False)
    tool: Mapped[str] = mapped_column(String(120), nullable=False)
    # The CLI's id for the call, to pair the start with its end.
    call_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None: still running
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")


__all__ = [
    "McpAssignment",
    "McpAuth",
    "McpConnection",
    "McpExclusion",
    "McpOAuth",
    "McpOrigin",
    "McpOriginKind",
    "McpToolMode",
    "McpTransport",
    "OAuthStatus",
    "RunConnection",
    "RunConnectionStatus",
    "RunToolCall",
]
