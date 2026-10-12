"""resume and log retention

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12 16:26:00.523438
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resumed_from_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("usage_baseline", sa.JSON(), nullable=True))
        # Existing rows get the default; the model sets it for new rows.
        batch_op.add_column(
            sa.Column("log_purged", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index(
            batch_op.f("ix_runs_resumed_from_id"), ["resumed_from_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_resumed_from_id_runs"),
            "runs",
            ["resumed_from_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_resumed_from_id_runs"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_runs_resumed_from_id"))
        batch_op.drop_column("log_purged")
        batch_op.drop_column("usage_baseline")
        batch_op.drop_column("resumed_from_id")
