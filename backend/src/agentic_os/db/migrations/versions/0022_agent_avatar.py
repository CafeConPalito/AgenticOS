"""agent avatar

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-28 09:00:00.000000

Phase 20: the picture of an agent and of a saved template. Null: its initials; `owl:<id>`: an
owl of the gallery; `photo:<hash>`: the cropped photo in `<data>/avatars/<hash>.webp`.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("agents", "agent_templates"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("avatar", sa.String(length=80), nullable=True))


def downgrade() -> None:
    for table in ("agent_templates", "agents"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("avatar")
