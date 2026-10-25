"""mcp connections

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-24 21:00:00.000000

Phase 18: the catalog of external MCP servers (connections), where each one is given (levels) and
taken away (agents and pipeline stages), the OAuth login and the registry origin of a connection,
which connections each run received, the calls it made to their tools and the new Inbox kind
«connection».
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention', 'limit',"
    " 'quota', 'account', 'switch', 'knowledge', 'skill'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'connection'"
LEVEL = (
    "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
    " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
    " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)"
)


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("transport", sa.String(length=8), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("env", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("secret_keys", sa.JSON(), nullable=False),
        sa.Column("auth", sa.String(length=8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("prompts", sa.JSON(), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_error", sa.JSON(), nullable=True),
        sa.Column("tools_changed", sa.Boolean(), nullable=False),
        sa.Column("tool_mode", sa.String(length=8), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("preapproved_tools", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "transport IN ('stdio', 'http', 'sse')", name=op.f("ck_mcp_connections_transport")
        ),
        sa.CheckConstraint("auth IN ('none', 'oauth')", name=op.f("ck_mcp_connections_auth")),
        sa.CheckConstraint(
            "tool_mode IN ('all', 'selected')", name=op.f("ck_mcp_connections_tool_mode")
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'template', 'import', 'registry')",
            name=op.f("ck_mcp_connections_origin"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_connections"),
    )
    op.create_index("ix_mcp_connections_workspace_id", "mcp_connections", ["workspace_id"])
    op.create_index(
        "uq_mcp_connections_name", "mcp_connections", ["workspace_id", "name"], unique=True
    )

    op.create_table(
        "mcp_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('general', 'project', 'agent')", name=op.f("ck_mcp_assignments_scope")
        ),
        sa.CheckConstraint(LEVEL, name=op.f("ck_mcp_assignments_level")),
        _fk("mcp_assignments", "connection_id", "mcp_connections", "CASCADE"),
        _fk("mcp_assignments", "project_id", "projects", "CASCADE"),
        _fk("mcp_assignments", "agent_id", "agents", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_assignments"),
    )
    op.create_index("ix_mcp_assignments_connection_id", "mcp_assignments", ["connection_id"])
    op.create_index("ix_mcp_assignments_project_id", "mcp_assignments", ["project_id"])
    op.create_index("ix_mcp_assignments_agent_id", "mcp_assignments", ["agent_id"])
    op.create_index(
        "uq_mcp_assignments_level",
        "mcp_assignments",
        [
            "connection_id",
            "scope",
            sa.text("coalesce(project_id, '')"),
            sa.text("coalesce(agent_id, '')"),
        ],
        unique=True,
    )

    op.create_table(
        "mcp_exclusions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("stage_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "(agent_id IS NULL) != (stage_id IS NULL)", name=op.f("ck_mcp_exclusions_target")
        ),
        sa.UniqueConstraint("connection_id", "agent_id", name="uq_mcp_exclusions_agent"),
        sa.UniqueConstraint("connection_id", "stage_id", name="uq_mcp_exclusions_stage"),
        _fk("mcp_exclusions", "connection_id", "mcp_connections", "CASCADE"),
        _fk("mcp_exclusions", "agent_id", "agents", "CASCADE"),
        _fk("mcp_exclusions", "stage_id", "stages", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_exclusions"),
    )
    op.create_index("ix_mcp_exclusions_connection_id", "mcp_exclusions", ["connection_id"])
    op.create_index("ix_mcp_exclusions_agent_id", "mcp_exclusions", ["agent_id"])
    op.create_index("ix_mcp_exclusions_stage_id", "mcp_exclusions", ["stage_id"])

    op.create_table(
        "mcp_oauth",
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_pasted", sa.Boolean(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("account_label", sa.String(length=160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('connected', 'needs_reauth', 'disconnected')",
            name=op.f("ck_mcp_oauth_status"),
        ),
        _fk("mcp_oauth", "connection_id", "mcp_connections", "CASCADE"),
        sa.PrimaryKeyConstraint("connection_id", name="pk_mcp_oauth"),
    )

    op.create_table(
        "mcp_origins",
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("package_type", sa.String(length=8), nullable=False),
        sa.Column("package", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=False),
        sa.Column("official", sa.Boolean(), nullable=False),
        sa.Column("latest_version", sa.String(length=80), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        _fk("mcp_origins", "connection_id", "mcp_connections", "CASCADE"),
        sa.PrimaryKeyConstraint("connection_id", name="pk_mcp_origins"),
    )

    op.create_table(
        "run_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("connection_name", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('sent', 'connected', 'failed', 'skipped')",
            name=op.f("ck_run_connections_status"),
        ),
        sa.UniqueConstraint("run_id", "connection_name", name="uq_run_connections_pair"),
        _fk("run_connections", "run_id", "runs", "CASCADE"),
        _fk("run_connections", "connection_id", "mcp_connections", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_run_connections"),
    )
    op.create_index("ix_run_connections_run_id", "run_connections", ["run_id"])

    op.create_table(
        "run_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("connection_name", sa.String(length=40), nullable=False),
        sa.Column("tool", sa.String(length=120), nullable=False),
        sa.Column("call_key", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        _fk("run_tool_calls", "run_id", "runs", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_run_tool_calls"),
    )
    op.create_index("ix_run_tool_calls_run_id", "run_tool_calls", ["run_id"])
    op.create_index(
        "ix_run_tool_calls_name_started", "run_tool_calls", ["connection_name", "started_at"]
    )

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("connection_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_inbox_items_connection_id", ["connection_id"])
        batch_op.create_foreign_key(
            "fk_inbox_items_connection_id_mcp_connections",
            "mcp_connections",
            ["connection_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_items WHERE kind = 'connection'")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )
        batch_op.drop_constraint("fk_inbox_items_connection_id_mcp_connections", type_="foreignkey")
        batch_op.drop_index("ix_inbox_items_connection_id")
        batch_op.drop_column("connection_id")
    op.drop_index("ix_run_tool_calls_name_started", table_name="run_tool_calls")
    op.drop_index("ix_run_tool_calls_run_id", table_name="run_tool_calls")
    op.drop_table("run_tool_calls")
    op.drop_index("ix_run_connections_run_id", table_name="run_connections")
    op.drop_table("run_connections")
    op.drop_table("mcp_origins")
    op.drop_table("mcp_oauth")
    for index in ("stage_id", "agent_id", "connection_id"):
        op.drop_index(f"ix_mcp_exclusions_{index}", table_name="mcp_exclusions")
    op.drop_table("mcp_exclusions")
    for index in (
        "uq_mcp_assignments_level",
        "ix_mcp_assignments_agent_id",
        "ix_mcp_assignments_project_id",
        "ix_mcp_assignments_connection_id",
    ):
        op.drop_index(index, table_name="mcp_assignments")
    op.drop_table("mcp_assignments")
    op.drop_index("uq_mcp_connections_name", table_name="mcp_connections")
    op.drop_index("ix_mcp_connections_workspace_id", table_name="mcp_connections")
    op.drop_table("mcp_connections")
    # The secrets in the system's credential store are deleted with each connection, not here.
