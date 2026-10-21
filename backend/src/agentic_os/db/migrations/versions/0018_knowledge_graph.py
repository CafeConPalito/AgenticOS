"""knowledge proposals and graph

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21 10:00:00.000000

Phase 15: documents proposed by agents (`origin`, `review`, `summary`, the `markdown` source
kind), their provenance, the «derived from» and «related» links between documents, what the
person rejected, the centroid of every document and the new Inbox kind «knowledge».
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Migration 0016 gave its checks a name that the naming convention prefixed a second time.
OLD_SOURCE_CHECK = "ck_knowledge_docs_ck_knowledge_docs_source_kind"
OLD_SOURCES = "'file', 'image', 'url'"
NEW_SOURCES = "'file', 'image', 'url', 'markdown'"
ORIGINS = "'user', 'agent'"
REVIEWS = "'none', 'proposed'"
OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention', 'limit',"
    " 'quota', 'account', 'switch'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'knowledge'"


def upgrade() -> None:
    with op.batch_alter_table("knowledge_docs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("origin", sa.String(length=8), nullable=False, server_default="user")
        )
        batch_op.add_column(
            sa.Column("review", sa.String(length=8), nullable=False, server_default="none")
        )
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("centroid", sa.LargeBinary(), nullable=True))
        batch_op.add_column(
            sa.Column("centroid_model", sa.String(length=80), nullable=False, server_default="")
        )
        batch_op.drop_constraint(op.f(OLD_SOURCE_CHECK), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_knowledge_docs_source_kind"), f"source_kind IN ({NEW_SOURCES})"
        )
        batch_op.create_check_constraint(op.f("ck_knowledge_docs_origin"), f"origin IN ({ORIGINS})")
        batch_op.create_check_constraint(op.f("ck_knowledge_docs_review"), f"review IN ({REVIEWS})")
        batch_op.create_index("ix_knowledge_docs_review", ["review"])

    op.create_table(
        "knowledge_provenance",
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("agent_name", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("task_title", sa.Text(), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suggested_scope", sa.String(length=8), nullable=False),
        sa.Column("replaces_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_provenance_doc_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name="fk_knowledge_provenance_run_id_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name="fk_knowledge_provenance_task_id_tasks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaces_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_provenance_replaces_id_knowledge_docs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("doc_id", name="pk_knowledge_provenance"),
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("source_title", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_sources_doc_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_sources_source_id_knowledge_docs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_sources"),
        sa.UniqueConstraint("doc_id", "source_id", name="uq_knowledge_sources_pair"),
    )
    op.create_index("ix_knowledge_sources_doc_id", "knowledge_sources", ["doc_id"])
    op.create_index("ix_knowledge_sources_source_id", "knowledge_sources", ["source_id"])

    op.create_table(
        "knowledge_related",
        sa.Column("a_id", sa.String(length=36), nullable=False),
        sa.Column("b_id", sa.String(length=36), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.CheckConstraint("a_id < b_id", name="ck_knowledge_related_order"),
        sa.ForeignKeyConstraint(
            ["a_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_related_a_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["b_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_related_b_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("a_id", "b_id", name="pk_knowledge_related"),
    )
    op.create_index("ix_knowledge_related_b_id", "knowledge_related", ["b_id"])

    op.create_table(
        "knowledge_rejections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("md_sha256", sa.String(length=64), nullable=False),
        sa.Column("centroid", sa.LargeBinary(), nullable=True),
        sa.Column("centroid_model", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_rejections"),
    )
    op.create_index("ix_knowledge_rejections_md_sha256", "knowledge_rejections", ["md_sha256"])

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("knowledge_doc_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_inbox_items_knowledge_doc_id", ["knowledge_doc_id"])
        batch_op.create_foreign_key(
            "fk_inbox_items_knowledge_doc_id_knowledge_docs",
            "knowledge_docs",
            ["knowledge_doc_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM inbox_items WHERE kind = 'knowledge'")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )
        batch_op.drop_constraint(
            "fk_inbox_items_knowledge_doc_id_knowledge_docs", type_="foreignkey"
        )
        batch_op.drop_index("ix_inbox_items_knowledge_doc_id")
        batch_op.drop_column("knowledge_doc_id")

    op.drop_index("ix_knowledge_rejections_md_sha256", table_name="knowledge_rejections")
    op.drop_table("knowledge_rejections")
    op.drop_index("ix_knowledge_related_b_id", table_name="knowledge_related")
    op.drop_table("knowledge_related")
    op.drop_index("ix_knowledge_sources_source_id", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_doc_id", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.drop_table("knowledge_provenance")

    # Proposals and agent documents have no place in the old schema.
    op.execute("DELETE FROM knowledge_docs WHERE source_kind = 'markdown'")
    with op.batch_alter_table("knowledge_docs", schema=None) as batch_op:
        batch_op.drop_index("ix_knowledge_docs_review")
        batch_op.drop_constraint(op.f("ck_knowledge_docs_review"), type_="check")
        batch_op.drop_constraint(op.f("ck_knowledge_docs_origin"), type_="check")
        batch_op.drop_constraint(op.f("ck_knowledge_docs_source_kind"), type_="check")
        batch_op.create_check_constraint(op.f(OLD_SOURCE_CHECK), f"source_kind IN ({OLD_SOURCES})")
        batch_op.drop_column("centroid_model")
        batch_op.drop_column("centroid")
        batch_op.drop_column("summary")
        batch_op.drop_column("review")
        batch_op.drop_column("origin")
