"""project avatar

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-01 18:00:00.000000

Phase 24: the photo of a project. Null: its initials on its color; `photo:<hash>`: the cropped
photo in `<data>/avatars/<hash>.webp` (projects have no owls).
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("avatar", sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("avatar")
