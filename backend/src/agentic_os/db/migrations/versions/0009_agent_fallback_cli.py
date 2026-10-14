"""agent fallback cli

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 19:55:53.525110

Phase 10 (amendment): an agent may declare a secondary CLI (account + model) to switch to when
its main account is about to run out of quota, and the Inbox gets the «switch» request.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Alembic does not compare CHECK constraints: the new Inbox kind is added by hand.
OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention',"
    " 'limit', 'quota', 'account'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'switch'"


def upgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fallback_account_id", sa.String(length=36), nullable=True))
        # Existing rows get the default; the model sets it for new rows.
        batch_op.add_column(
            sa.Column("fallback_model", sa.String(length=80), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("using_fallback_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("switch_decided_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_agents_fallback_account_id"), ["fallback_account_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_agents_fallback_account_id_cli_accounts"),
            "cli_accounts",
            ["fallback_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_items WHERE kind = 'switch'")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_agents_fallback_account_id_cli_accounts"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_agents_fallback_account_id"))
        batch_op.drop_column("switch_decided_until")
        batch_op.drop_column("using_fallback_until")
        batch_op.drop_column("fallback_model")
        batch_op.drop_column("fallback_account_id")
