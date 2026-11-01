"""pipeline exits and SDD mode

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-01 20:00:00.000000

Phase 24 (ADR 0030): a stage can end the task early («Terminar aquí», `exit_condition`, decided
by the branch decider), with the place of its «Fin» node on the editor's canvas; a task keeps
the stage it ended at, and the working mode its requirements stage chose (SDD or direct) with
the folder of its spec.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

OLD_EVENT_KINDS = (
    "'created', 'queued', 'stage_started', 'stage_completed', 'rejected', 'review_approved', "
    "'review_rejected', 'waiting_human', 'retried', 'completed_manually', 'cancelled', 'done', "
    "'workspace', 'human_request', 'human_answered', 'subtask', 'integrated', 'git', "
    "'decision', 'lane_started', 'lane_finished', 'lane_added', 'lane_cancelled', 'joined'"
)
# The task ended at a stage's exit; its requirements stage chose (or the person changed) its mode.
NEW_EVENT_KINDS = OLD_EVENT_KINDS + ", 'exited', 'work_mode'"


def upgrade() -> None:
    with op.batch_alter_table("stages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exit_condition", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("exit_x", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("exit_y", sa.Integer(), nullable=True))
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exit_stage_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("work_mode", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("work_mode_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("spec_path", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_exit_stage_id_stages",
            "stages",
            ["exit_stage_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({NEW_EVENT_KINDS})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM task_events WHERE kind IN ('exited', 'work_mode')")
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({OLD_EVENT_KINDS})"
        )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint("fk_tasks_exit_stage_id_stages", type_="foreignkey")
        batch_op.drop_column("spec_path")
        batch_op.drop_column("work_mode_reason")
        batch_op.drop_column("work_mode")
        batch_op.drop_column("exit_stage_id")
    with op.batch_alter_table("stages", schema=None) as batch_op:
        batch_op.drop_column("exit_y")
        batch_op.drop_column("exit_x")
        batch_op.drop_column("exit_condition")
