"""commit attributions

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-18 10:00:00.000000

Phase 12: which run, task and agent made each commit, and the task event «git» that says a run
did something with git.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OLD_EVENT_KINDS = (
    "'created', 'queued', 'stage_started', 'stage_completed', 'rejected', 'review_approved', "
    "'review_rejected', 'waiting_human', 'retried', 'completed_manually', 'cancelled', 'done', "
    "'workspace', 'human_request', 'human_answered', 'subtask', 'integrated'"
)
NEW_EVENT_KINDS = OLD_EVENT_KINDS + ", 'git'"


def upgrade() -> None:
    op.create_table(
        "commit_attributions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repo_id", sa.String(length=36), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("agent_name", sa.String(length=80), nullable=False),
        sa.Column("task_code", sa.String(length=24), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["project_repos.id"],
            name="fk_commit_attributions_repo_id_project_repos",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_commit_attributions"),
        sa.UniqueConstraint("repo_id", "sha", name="uq_commit_attributions_repo_sha"),
    )
    op.create_index("ix_commit_attributions_repo_id", "commit_attributions", ["repo_id"])
    op.create_index("ix_commit_attributions_run_id", "commit_attributions", ["run_id"])
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({NEW_EVENT_KINDS})"
        )


def downgrade() -> None:
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({OLD_EVENT_KINDS})"
        )
    op.drop_index("ix_commit_attributions_run_id", table_name="commit_attributions")
    op.drop_index("ix_commit_attributions_repo_id", table_name="commit_attributions")
    op.drop_table("commit_attributions")
