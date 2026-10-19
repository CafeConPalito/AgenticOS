"""knowledge images: order, kind, notice and count

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-19 19:00:00.000000

Phase 14, block 4: a picture is numbered inside its document (`kimg:<ord>`), the document can
carry a warning (e.g. the OCR model is missing) and counts its pictures.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_docs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notice", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("image_count", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("knowledge_images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ord", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("kind", sa.String(length=8), nullable=False, server_default="embedded")
        )
        batch_op.create_unique_constraint("uq_knowledge_images_doc_ord", ["doc_id", "ord"])


def downgrade() -> None:
    with op.batch_alter_table("knowledge_images", schema=None) as batch_op:
        batch_op.drop_constraint("uq_knowledge_images_doc_ord", type_="unique")
        batch_op.drop_column("kind")
        batch_op.drop_column("ord")
    with op.batch_alter_table("knowledge_docs", schema=None) as batch_op:
        batch_op.drop_column("image_count")
        batch_op.drop_column("notice")
