"""skills

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-23 20:00:00.000000

Phase 17: the skill library (skills and their versions over a content-addressed store), the
automatic / always / never modes per agent and per stage, where an installed skill came from,
which skills each run was offered and loaded (usage statistics), rejected proposals and the new
Inbox kind «skill».
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention', 'limit',"
    " 'quota', 'account', 'switch', 'knowledge'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'skill'"
LEVEL = (
    "(scope = 'general' AND project_id IS NULL AND agent_id IS NULL)"
    " OR (scope = 'project' AND project_id IS NOT NULL AND agent_id IS NULL)"
    " OR (scope = 'agent' AND agent_id IS NOT NULL AND project_id IS NULL)"
)


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("review", sa.String(length=8), nullable=False),
        sa.Column("origin", sa.String(length=8), nullable=False),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("model_invocable", sa.Boolean(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=True),
        sa.Column("vector_model", sa.String(length=80), nullable=False),
        sa.CheckConstraint(
            "scope IN ('general', 'project', 'agent')", name=op.f("ck_skills_scope")
        ),
        sa.CheckConstraint("review IN ('none', 'proposed')", name=op.f("ck_skills_review")),
        sa.CheckConstraint(
            "origin IN ('user', 'agent', 'import', 'registry')", name=op.f("ck_skills_origin")
        ),
        sa.CheckConstraint(LEVEL, name=op.f("ck_skills_level")),
        _fk("skills", "project_id", "projects", "CASCADE"),
        _fk("skills", "agent_id", "agents", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
    )
    op.create_index("ix_skills_workspace_id", "skills", ["workspace_id"])
    op.create_index("ix_skills_project_id", "skills", ["project_id"])
    op.create_index("ix_skills_agent_id", "skills", ["agent_id"])
    op.create_index("ix_skills_review", "skills", ["review"])
    op.create_index(
        "uq_skills_level_name",
        "skills",
        [
            "workspace_id",
            "scope",
            sa.text("coalesce(project_id, '')"),
            sa.text("coalesce(agent_id, '')"),
            "name",
        ],
        unique=True,
    )

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("author_kind", sa.String(length=8), nullable=False),
        sa.Column("author_label", sa.String(length=120), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("task_title", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("base_version_id", sa.String(length=36), nullable=True),
        sa.Column("restored_from_id", sa.String(length=36), nullable=True),
        sa.Column("suggested_scope", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('accepted', 'proposed', 'rejected')",
            name=op.f("ck_skill_versions_status"),
        ),
        sa.CheckConstraint(
            "author_kind IN ('user', 'agent', 'import', 'registry', 'restore')",
            name=op.f("ck_skill_versions_author_kind"),
        ),
        _fk("skill_versions", "skill_id", "skills", "CASCADE"),
        _fk("skill_versions", "agent_id", "agents", "SET NULL"),
        _fk("skill_versions", "run_id", "runs", "SET NULL"),
        _fk("skill_versions", "task_id", "tasks", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_skill_versions"),
        sa.UniqueConstraint("skill_id", "number", name="uq_skill_versions_number"),
    )
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])

    op.create_table(
        "skill_modes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("stage_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.CheckConstraint("mode IN ('auto', 'always', 'never')", name=op.f("ck_skill_modes_mode")),
        sa.CheckConstraint(
            "(agent_id IS NULL) != (stage_id IS NULL)", name=op.f("ck_skill_modes_target")
        ),
        _fk("skill_modes", "skill_id", "skills", "CASCADE"),
        _fk("skill_modes", "agent_id", "agents", "CASCADE"),
        _fk("skill_modes", "stage_id", "stages", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_skill_modes"),
        sa.UniqueConstraint("skill_id", "agent_id", name="uq_skill_modes_agent"),
        sa.UniqueConstraint("skill_id", "stage_id", name="uq_skill_modes_stage"),
    )
    op.create_index("ix_skill_modes_skill_id", "skill_modes", ["skill_id"])
    op.create_index("ix_skill_modes_agent_id", "skill_modes", ["agent_id"])
    op.create_index("ix_skill_modes_stage_id", "skill_modes", ["stage_id"])

    op.create_table(
        "skill_origins",
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("revision", sa.String(length=80), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=False),
        sa.Column("security", sa.JSON(), nullable=False),
        sa.Column("latest_revision", sa.String(length=80), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_version_id", sa.String(length=36), nullable=True),
        _fk("skill_origins", "skill_id", "skills", "CASCADE"),
        sa.PrimaryKeyConstraint("skill_id", name="pk_skill_origins"),
    )

    op.create_table(
        "run_skills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("skill_name", sa.String(length=64), nullable=False),
        sa.Column("offered", sa.String(length=10), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("loaded_via", sa.String(length=8), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage_name", sa.String(length=80), nullable=False),
        sa.Column("pipeline_id", sa.String(length=36), nullable=True),
        sa.Column("pipeline_name", sa.String(length=80), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("team_name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "offered IN ('always', 'candidate', 'requested')", name=op.f("ck_run_skills_offered")
        ),
        sa.CheckConstraint(
            "loaded_via IS NULL OR loaded_via IN ('context', 'tool', 'native')",
            name=op.f("ck_run_skills_via"),
        ),
        _fk("run_skills", "run_id", "runs", "CASCADE"),
        _fk("run_skills", "skill_id", "skills", "CASCADE"),
        _fk("run_skills", "version_id", "skill_versions", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_run_skills"),
        sa.UniqueConstraint("run_id", "skill_id", name="uq_run_skills_pair"),
    )
    op.create_index("ix_run_skills_run_id", "run_skills", ["run_id"])
    op.create_index("ix_run_skills_skill_loaded", "run_skills", ["skill_id", "loaded_at"])

    op.create_table(
        "skill_rejections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("md_sha256", sa.String(length=64), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=True),
        sa.Column("vector_model", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_skill_rejections"),
    )
    op.create_index("ix_skill_rejections_name", "skill_rejections", ["name"])
    op.create_index("ix_skill_rejections_md_sha256", "skill_rejections", ["md_sha256"])

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("skill_version_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_inbox_items_skill_version_id", ["skill_version_id"])
        batch_op.create_foreign_key(
            "fk_inbox_items_skill_version_id_skill_versions",
            "skill_versions",
            ["skill_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )

    # The statistics filter runs by when they started (phase 17, CA20).
    op.create_index("ix_runs_started_at", "runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_started_at", table_name="runs")
    op.execute("DELETE FROM inbox_items WHERE kind = 'skill'")
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )
        batch_op.drop_constraint(
            "fk_inbox_items_skill_version_id_skill_versions", type_="foreignkey"
        )
        batch_op.drop_index("ix_inbox_items_skill_version_id")
        batch_op.drop_column("skill_version_id")
    op.drop_index("ix_skill_rejections_md_sha256", table_name="skill_rejections")
    op.drop_index("ix_skill_rejections_name", table_name="skill_rejections")
    op.drop_table("skill_rejections")
    op.drop_index("ix_run_skills_skill_loaded", table_name="run_skills")
    op.drop_index("ix_run_skills_run_id", table_name="run_skills")
    op.drop_table("run_skills")
    op.drop_table("skill_origins")
    for index in ("stage_id", "agent_id", "skill_id"):
        op.drop_index(f"ix_skill_modes_{index}", table_name="skill_modes")
    op.drop_table("skill_modes")
    op.drop_index("ix_skill_versions_skill_id", table_name="skill_versions")
    op.drop_table("skill_versions")
    for index in (
        "uq_skills_level_name",
        "ix_skills_review",
        "ix_skills_agent_id",
        "ix_skills_project_id",
        "ix_skills_workspace_id",
    ):
        op.drop_index(index, table_name="skills")
    op.drop_table("skills")
    # The skill files in <data_dir>/skills are left alone: the person may want them back.
