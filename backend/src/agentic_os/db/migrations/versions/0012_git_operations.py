"""git operations

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17 21:00:00.000000

Phase 12: what the app did to a repository that can be undone.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "git_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repo_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refs_before", sa.JSON(), nullable=False),
        sa.Column("refs_after", sa.JSON(), nullable=True),
        sa.Column("head_before", sa.String(length=160), nullable=True),
        sa.Column("backup_ref", sa.String(length=200), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["project_repos.id"],
            name="fk_git_operations_repo_id_project_repos",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_git_operations"),
    )
    op.create_index("ix_git_operations_repo_id", "git_operations", ["repo_id"])
    op.create_index("ix_git_operations_group_id", "git_operations", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_git_operations_group_id", table_name="git_operations")
    op.drop_index("ix_git_operations_repo_id", table_name="git_operations")
    op.drop_table("git_operations")
