"""architect

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-25 21:00:00.000000

Phase 19: conversations with the Architect and their messages, proposals (of the Architect and of
propose_agent) with the drafts they create, the history of an agent's configuration, the
templates the person saves, and the new kinds «architect» (runs, skills, skill versions) and
«proposal» (Inbox).
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention', 'limit',"
    " 'quota', 'account', 'switch', 'knowledge', 'skill', 'connection'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'proposal'"
OLD_SKILL_ORIGINS = "'user', 'agent', 'import', 'registry'"
OLD_AUTHORS = "'user', 'agent', 'import', 'registry', 'restore'"


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "architect_conversations",
        *_timestamps(),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("cli", sa.String(length=16), nullable=True),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("cli_session_id", sa.String(length=80), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("sheet", sa.JSON(), nullable=False),
        sa.Column("locked_fields", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "mode IN ('agent', 'improve_agent', 'team', 'improve_team', 'improve_pipeline')",
            name=op.f("ck_architect_conversations_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'proposed', 'applied', 'discarded')",
            name=op.f("ck_architect_conversations_status"),
        ),
        _fk("architect_conversations", "agent_id", "agents", "SET NULL"),
        _fk("architect_conversations", "team_id", "teams", "SET NULL"),
        _fk("architect_conversations", "project_id", "projects", "SET NULL"),
        _fk("architect_conversations", "account_id", "cli_accounts", "SET NULL"),
        _fk("architect_conversations", "run_id", "runs", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_architect_conversations"),
    )
    for column in ("workspace_id", "status", "agent_id", "team_id", "project_id"):
        op.create_index(f"ix_architect_conversations_{column}", "architect_conversations", [column])

    op.create_table(
        "architect_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tool_events", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'architect', 'system')", name=op.f("ck_architect_messages_role")
        ),
        _fk("architect_messages", "conversation_id", "architect_conversations", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_architect_messages"),
    )
    op.create_index(
        "ix_architect_messages_conversation_id", "architect_messages", ["conversation_id"]
    )

    op.create_table(
        "proposals",
        *_timestamps(),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("source_agent_id", sa.String(length=36), nullable=True),
        sa.Column("source_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_task_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_agent_id", sa.String(length=36), nullable=True),
        sa.Column("target_team_id", sa.String(length=36), nullable=True),
        sa.Column("target_project_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("applied_fields", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('new_agent', 'agent_changes', 'team', 'team_changes', 'pipeline_changes')",
            name=op.f("ck_proposals_kind"),
        ),
        sa.CheckConstraint("origin IN ('architect', 'agent')", name=op.f("ck_proposals_origin")),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'partial', 'rejected')",
            name=op.f("ck_proposals_status"),
        ),
        _fk("proposals", "conversation_id", "architect_conversations", "SET NULL"),
        _fk("proposals", "source_agent_id", "agents", "SET NULL"),
        _fk("proposals", "source_run_id", "runs", "SET NULL"),
        _fk("proposals", "source_task_id", "tasks", "SET NULL"),
        _fk("proposals", "target_agent_id", "agents", "CASCADE"),
        _fk("proposals", "target_team_id", "teams", "CASCADE"),
        _fk("proposals", "target_project_id", "projects", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_proposals"),
    )
    for column in (
        "workspace_id",
        "status",
        "conversation_id",
        "source_run_id",
        "target_agent_id",
        "target_team_id",
        "target_project_id",
    ):
        op.create_index(f"ix_proposals_{column}", "proposals", [column])

    op.create_table(
        "agent_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('user', 'architect', 'agent', 'import')",
            name=op.f("ck_agent_changes_source"),
        ),
        _fk("agent_changes", "agent_id", "agents", "CASCADE"),
        _fk("agent_changes", "proposal_id", "proposals", "SET NULL"),
        _fk("agent_changes", "conversation_id", "architect_conversations", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_changes"),
    )
    op.create_index("ix_agent_changes_agent_id", "agent_changes", ["agent_id"])

    op.create_table(
        "agent_templates",
        *_timestamps(),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_templates"),
    )
    op.create_index("ix_agent_templates_workspace_id", "agent_templates", ["workspace_id"])
    op.create_index(
        "uq_agent_templates_name", "agent_templates", ["workspace_id", "name"], unique=True
    )

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("can_propose_agents", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("proposal_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_agents_proposal_id", ["proposal_id"])
        batch_op.create_foreign_key(
            "fk_agents_proposal_id_proposals",
            "proposals",
            ["proposal_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.alter_column("kind", existing_type=sa.String(length=8), type_=sa.String(length=12))

    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.alter_column(
            "origin", existing_type=sa.String(length=8), type_=sa.String(length=12)
        )
        batch_op.drop_constraint(op.f("ck_skills_origin"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_skills_origin"), f"origin IN ({OLD_SKILL_ORIGINS}, 'architect')"
        )
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.alter_column(
            "author_kind", existing_type=sa.String(length=8), type_=sa.String(length=12)
        )
        batch_op.drop_constraint(op.f("ck_skill_versions_author_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_skill_versions_author_kind"), f"author_kind IN ({OLD_AUTHORS}, 'architect')"
        )

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("proposal_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_inbox_items_proposal_id", ["proposal_id"])
        batch_op.create_foreign_key(
            "fk_inbox_items_proposal_id_proposals",
            "proposals",
            ["proposal_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_items WHERE kind = 'proposal'")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )
        batch_op.drop_constraint("fk_inbox_items_proposal_id_proposals", type_="foreignkey")
        batch_op.drop_index("ix_inbox_items_proposal_id")
        batch_op.drop_column("proposal_id")

    # What the Architect wrote becomes the person's: the older lists have no «architect».
    op.execute("UPDATE skill_versions SET author_kind = 'user' WHERE author_kind = 'architect'")
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_skill_versions_author_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_skill_versions_author_kind"), f"author_kind IN ({OLD_AUTHORS})"
        )
        batch_op.alter_column(
            "author_kind", existing_type=sa.String(length=12), type_=sa.String(length=8)
        )
    op.execute("UPDATE skills SET origin = 'user' WHERE origin = 'architect'")
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_skills_origin"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_skills_origin"), f"origin IN ({OLD_SKILL_ORIGINS})"
        )
        batch_op.alter_column(
            "origin", existing_type=sa.String(length=12), type_=sa.String(length=8)
        )

    op.execute("DELETE FROM runs WHERE kind = 'architect'")
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.alter_column("kind", existing_type=sa.String(length=12), type_=sa.String(length=8))

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_agents_proposal_id_proposals", type_="foreignkey")
        batch_op.drop_index("ix_agents_proposal_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("proposal_id")
        batch_op.drop_column("can_propose_agents")

    op.drop_index("uq_agent_templates_name", table_name="agent_templates")
    op.drop_index("ix_agent_templates_workspace_id", table_name="agent_templates")
    op.drop_table("agent_templates")
    op.drop_index("ix_agent_changes_agent_id", table_name="agent_changes")
    op.drop_table("agent_changes")
    for column in (
        "target_project_id",
        "target_team_id",
        "target_agent_id",
        "source_run_id",
        "conversation_id",
        "status",
        "workspace_id",
    ):
        op.drop_index(f"ix_proposals_{column}", table_name="proposals")
    op.drop_table("proposals")
    op.drop_index("ix_architect_messages_conversation_id", table_name="architect_messages")
    op.drop_table("architect_messages")
    for column in ("project_id", "team_id", "agent_id", "status", "workspace_id"):
        op.drop_index(f"ix_architect_conversations_{column}", table_name="architect_conversations")
    op.drop_table("architect_conversations")
