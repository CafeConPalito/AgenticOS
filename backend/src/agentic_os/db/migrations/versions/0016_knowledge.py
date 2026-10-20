"""knowledge library

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-18 21:00:00.000000

Phase 14: documents kept by reference (knowledge_docs), the pieces they are searched by
(knowledge_chunks), the images extracted from them (knowledge_images) and a full-text index
(knowledge_fts, SQLite FTS5). `runs.kind` is a plain string, so the new «describe» kind needs
no change here.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SCOPES = "'general', 'project', 'agent'"
MODES = "'auto', 'context', 'search', 'off'"
SOURCES = "'file', 'image', 'url'"
PRESENCES = "'ok', 'missing', 'changed'"
STATUSES = "'queued', 'converting', 'images', 'describing', 'indexing', 'ready', 'failed'"
LEVEL = (
    "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
    " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
    " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)"
)


def upgrade() -> None:
    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("describe_images", sa.Boolean(), nullable=True),
        sa.Column("source_kind", sa.String(length=8), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("source_mtime", sa.Float(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("presence", sa.String(length=8), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("progress_done", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("md_tokens", sa.Integer(), nullable=False),
        sa.Column("embed_model", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"scope IN ({SCOPES})", name="ck_knowledge_docs_scope"),
        sa.CheckConstraint(f"mode IN ({MODES})", name="ck_knowledge_docs_mode"),
        sa.CheckConstraint(f"source_kind IN ({SOURCES})", name="ck_knowledge_docs_source_kind"),
        sa.CheckConstraint(f"presence IN ({PRESENCES})", name="ck_knowledge_docs_presence"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_knowledge_docs_status"),
        sa.CheckConstraint(LEVEL, name="ck_knowledge_docs_level"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_knowledge_docs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name="fk_knowledge_docs_agent_id_agents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_docs"),
    )
    op.create_index("ix_knowledge_docs_workspace_id", "knowledge_docs", ["workspace_id"])
    op.create_index("ix_knowledge_docs_project_id", "knowledge_docs", ["project_id"])
    op.create_index("ix_knowledge_docs_agent_id", "knowledge_docs", ["agent_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=True),
        sa.Column("vector_model", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_chunks_doc_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_chunks"),
        sa.UniqueConstraint("doc_id", "ord", name="uq_knowledge_chunks_doc_ord"),
    )
    op.create_index("ix_knowledge_chunks_doc_id", "knowledge_chunks", ["doc_id"])

    op.create_table(
        "knowledge_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file", sa.String(length=300), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("described_by", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["knowledge_docs.id"],
            name="fk_knowledge_images_doc_id_knowledge_docs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_images"),
    )
    op.create_index("ix_knowledge_images_doc_id", "knowledge_images", ["doc_id"])

    # The words index: no accents, and the chunk it belongs to travels with the row. The text
    # itself is not in `knowledge_chunks` (they only point into the document's Markdown).
    op.execute(
        "CREATE VIRTUAL TABLE knowledge_fts USING fts5("
        "text, chunk_id UNINDEXED, doc_id UNINDEXED, tokenize='unicode61 remove_diacritics 2')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE knowledge_fts")
    op.drop_index("ix_knowledge_images_doc_id", table_name="knowledge_images")
    op.drop_table("knowledge_images")
    op.drop_index("ix_knowledge_chunks_doc_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_docs_agent_id", table_name="knowledge_docs")
    op.drop_index("ix_knowledge_docs_project_id", table_name="knowledge_docs")
    op.drop_index("ix_knowledge_docs_workspace_id", table_name="knowledge_docs")
    op.drop_table("knowledge_docs")
