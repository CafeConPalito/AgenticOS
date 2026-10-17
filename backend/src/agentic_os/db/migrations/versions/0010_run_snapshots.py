"""run snapshots

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15 22:30:00.000000

Phase 11: every run keeps the shas of the snapshots of its folder (start and end) and the summary
of what it changed; a worktree task keeps the commit it started from. Existing rows have no data.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("snapshot_start", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("snapshot_end", sa.String(length=40), nullable=True))
        # Existing rows get the default; the model sets it for new rows.
        batch_op.add_column(
            sa.Column("snapshot_skipped", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("changes_files", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("changes_added", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("changes_deleted", sa.Integer(), nullable=True))
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("base_commit", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("base_commit")
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("changes_deleted")
        batch_op.drop_column("changes_added")
        batch_op.drop_column("changes_files")
        batch_op.drop_column("snapshot_skipped")
        batch_op.drop_column("snapshot_end")
        batch_op.drop_column("snapshot_start")
