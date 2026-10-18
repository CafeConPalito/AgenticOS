"""task integration

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17 23:00:00.000000

Phase 12: how a project brings the branches of its tasks into their bases, what happens when a
task is approved, whether agents may use git freely, and the tasks made to resolve conflicts.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# Alembic does not compare CHECK constraints: the new task event kind is added by hand.
OLD_EVENT_KINDS = (
    "'created', 'queued', 'stage_started', 'stage_completed', 'rejected', 'review_approved', "
    "'review_rejected', 'waiting_human', 'retried', 'completed_manually', 'cancelled', 'done', "
    "'workspace', 'human_request', 'human_answered', 'subtask'"
)
NEW_EVENT_KINDS = OLD_EVENT_KINDS + ", 'integrated'"


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "integration_mode", sa.String(length=8), nullable=False, server_default="merge"
            )
        )
        batch_op.add_column(
            sa.Column("on_approve", sa.String(length=16), nullable=False, server_default="none")
        )
        batch_op.add_column(
            sa.Column(
                "agents_git_authorized", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
        batch_op.create_check_constraint(
            op.f("ck_projects_integration_mode"),
            "integration_mode IN ('merge', 'squash', 'rebase')",
        )
        batch_op.create_check_constraint(
            op.f("ck_projects_on_approve"),
            "on_approve IN ('none', 'integrate', 'integrate_push', 'pull_request')",
        )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolves_task_id", sa.String(length=36), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_tasks_resolves_task_id"), ["resolves_task_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_tasks_resolves_task_id_tasks"),
            "tasks",
            ["resolves_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
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
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_tasks_resolves_task_id_tasks"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_tasks_resolves_task_id"))
        batch_op.drop_column("resolves_task_id")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_projects_on_approve"), type_="check")
        batch_op.drop_constraint(op.f("ck_projects_integration_mode"), type_="check")
        batch_op.drop_column("agents_git_authorized")
        batch_op.drop_column("on_approve")
        batch_op.drop_column("integration_mode")
