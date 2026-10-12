"""usage, limits and quota

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12 10:35:21.562103
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Alembic does not compare CHECK constraints: the new Inbox kinds are added by hand.
OLD_INBOX_KINDS = "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention'"
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'limit', 'quota'"
USAGE_STATUSES = "'pending', 'partial', 'final', 'unavailable'"
TOKENS = (
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("transcript_path", sa.Text(), nullable=True))
        # Existing rows get the defaults; the models set them for new rows.
        batch_op.add_column(
            sa.Column("extra_transcripts", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("cli_version", sa.String(length=40), nullable=True))
        for column in TOKENS:
            batch_op.add_column(sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("cost_usd", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("usage_models", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("usage_source", sa.String(length=24), nullable=True))
        batch_op.add_column(
            sa.Column(
                "usage_status", sa.String(length=12), nullable=False, server_default="pending"
            )
        )
        batch_op.add_column(sa.Column("usage_read_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_runs_usage_status"), ["usage_status"], unique=False)
        batch_op.create_check_constraint(
            op.f("ck_runs_usage_status"), f"usage_status IN ({USAGE_STATUSES})"
        )

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_items WHERE kind IN ('limit', 'quota')")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_runs_usage_status"), type_="check")
        batch_op.drop_index(batch_op.f("ix_runs_usage_status"))
        for column in (
            "usage_read_at",
            "usage_status",
            "usage_source",
            "usage_models",
            "cost_usd",
            *reversed(TOKENS),
            "cli_version",
            "extra_transcripts",
            "transcript_path",
        ):
            batch_op.drop_column(column)
