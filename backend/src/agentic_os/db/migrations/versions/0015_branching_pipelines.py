"""branching pipelines

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-18 20:00:00.000000

Phase 13: a pipeline is a graph. The stages get a place on the canvas, the links between them
become rows, and the pipeline names who decides the branches of a fork. Every existing pipeline
is a chain, so each stage gets one link to the next by position and nothing changes for the
tasks in flight.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

COLUMN_GAP = 280

OLD_STATUSES = "'backlog', 'queued', 'running', 'waiting_human', 'review', 'done', 'cancelled'"
NEW_STATUSES = OLD_STATUSES + ", 'deciding', 'forked'"
OLD_EVENT_KINDS = (
    "'created', 'queued', 'stage_started', 'stage_completed', 'rejected', 'review_approved', "
    "'review_rejected', 'waiting_human', 'retried', 'completed_manually', 'cancelled', 'done', "
    "'workspace', 'human_request', 'human_answered', 'subtask', 'integrated', 'git'"
)
NEW_EVENT_KINDS = (
    OLD_EVENT_KINDS
    + ", 'decision', 'lane_started', 'lane_finished', 'lane_added', 'lane_cancelled', 'joined'"
)


def upgrade() -> None:
    op.create_table(
        "stage_links",
        sa.Column("pipeline_id", sa.String(length=36), nullable=False),
        sa.Column("from_stage_id", sa.String(length=36), nullable=False),
        sa.Column("to_stage_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("always", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
            name=op.f("fk_stage_links_pipeline_id_pipelines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_stage_id"],
            ["stages.id"],
            name=op.f("fk_stage_links_from_stage_id_stages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_stage_id"],
            ["stages.id"],
            name=op.f("fk_stage_links_to_stage_id_stages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_links")),
        sa.UniqueConstraint(
            "from_stage_id", "to_stage_id", name=op.f("uq_stage_links_from_stage_id")
        ),
    )
    op.create_index(op.f("ix_stage_links_pipeline_id"), "stage_links", ["pipeline_id"])
    op.create_index(op.f("ix_stage_links_from_stage_id"), "stage_links", ["from_stage_id"])

    with op.batch_alter_table("stages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("reject_extra_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("x", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("y", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("confirm_decision", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decider_cli", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("decider_account_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("decider_model", sa.String(length=80), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_pipelines_decider_account_id_cli_accounts"),
            "cli_accounts",
            ["decider_account_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _tasks_and_decisions()
    _chain_existing_pipelines()


def _tasks_and_decisions() -> None:
    op.create_table(
        "branch_decisions",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("fork_stage_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=8), nullable=False),
        sa.Column("proposed", sa.Boolean(), nullable=False),
        sa.Column("chosen", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "decided_by IN ('model', 'user', 'always', 'preset')",
            name=op.f("ck_branch_decisions_decided_by"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_branch_decisions_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fork_stage_id"],
            ["stages.id"],
            name=op.f("fk_branch_decisions_fork_stage_id_stages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_branch_decisions_run_id_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branch_decisions")),
    )
    op.create_index(op.f("ix_branch_decisions_task_id"), "branch_decisions", ["task_id"])

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lane_of_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("lane_link_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("fork_stage_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("lane_key", sa.String(length=80), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("preset_lanes", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.create_foreign_key(
            op.f("fk_tasks_lane_of_id_tasks"), "tasks", ["lane_of_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            op.f("fk_tasks_lane_link_id_stage_links"),
            "stage_links",
            ["lane_link_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            op.f("fk_tasks_fork_stage_id_stages"),
            "stages",
            ["fork_stage_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_tasks_lane_of_id"), ["lane_of_id"])
        batch_op.drop_constraint("uq_tasks_workspace_number", type_="unique")
        batch_op.create_unique_constraint(
            "uq_tasks_workspace_number", ["workspace_id", "number", "lane_key"]
        )
        batch_op.drop_constraint(op.f("ck_tasks_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_tasks_status"), f"status IN ({NEW_STATUSES})")
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({NEW_EVENT_KINDS})"
        )
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reject_to_stage_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("kind", sa.String(length=8), nullable=False, server_default="agent")
        )


def _chain_existing_pipelines() -> None:
    bind = op.get_bind()
    stages = bind.execute(
        sa.text("SELECT id, pipeline_id, position FROM stages ORDER BY pipeline_id, position")
    ).all()
    by_pipeline: dict[str, list[str]] = {}
    for stage_id, pipeline_id, _ in stages:
        by_pipeline.setdefault(pipeline_id, []).append(stage_id)
    for pipeline_id, ids in by_pipeline.items():
        for index, stage_id in enumerate(ids):
            bind.execute(
                sa.text("UPDATE stages SET x = :x, y = 0 WHERE id = :id"),
                {"x": index * COLUMN_GAP, "id": stage_id},
            )
            if index + 1 < len(ids):
                bind.execute(
                    sa.text(
                        "INSERT INTO stage_links (id, pipeline_id, from_stage_id, to_stage_id,"
                        " name, condition, always, position)"
                        " VALUES (:id, :pipeline, :src, :dst, '', '', 0, 0)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "pipeline": pipeline_id,
                        "src": stage_id,
                        "dst": ids[index + 1],
                    },
                )


def downgrade() -> None:
    bind = op.get_bind()
    forks = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT from_stage_id FROM stage_links GROUP BY 1 HAVING COUNT(*) > 1)"
        )
    ).scalar()
    if forks:
        raise RuntimeError("cannot downgrade: a pipeline has a fork (phase 13)")
    lanes = bind.execute(sa.text("SELECT COUNT(*) FROM tasks WHERE lane_key != ''")).scalar()
    if lanes:
        raise RuntimeError("cannot downgrade: there are lanes of forked tasks (phase 13)")
    bind.execute(
        sa.text("UPDATE tasks SET status = 'running' WHERE status IN ('deciding', 'forked')")
    )
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("kind")
        batch_op.drop_column("reject_to_stage_id")
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_task_events_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_task_events_kind"), f"kind IN ({OLD_EVENT_KINDS})"
        )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_tasks_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_tasks_status"), f"status IN ({OLD_STATUSES})")
        batch_op.drop_constraint("uq_tasks_workspace_number", type_="unique")
        batch_op.create_unique_constraint("uq_tasks_workspace_number", ["workspace_id", "number"])
        batch_op.drop_index(op.f("ix_tasks_lane_of_id"))
        batch_op.drop_constraint(op.f("fk_tasks_fork_stage_id_stages"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_tasks_lane_link_id_stage_links"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_tasks_lane_of_id_tasks"), type_="foreignkey")
        batch_op.drop_column("preset_lanes")
        batch_op.drop_column("lane_key")
        batch_op.drop_column("fork_stage_id")
        batch_op.drop_column("lane_link_id")
        batch_op.drop_column("lane_of_id")
    op.drop_index(op.f("ix_branch_decisions_task_id"), table_name="branch_decisions")
    op.drop_table("branch_decisions")
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_pipelines_decider_account_id_cli_accounts"), type_="foreignkey"
        )
        batch_op.drop_column("decider_model")
        batch_op.drop_column("decider_account_id")
        batch_op.drop_column("decider_cli")
    with op.batch_alter_table("stages", schema=None) as batch_op:
        batch_op.drop_column("confirm_decision")
        batch_op.drop_column("reject_extra_ids")
        batch_op.drop_column("y")
        batch_op.drop_column("x")
    op.drop_index(op.f("ix_stage_links_from_stage_id"), table_name="stage_links")
    op.drop_index(op.f("ix_stage_links_pipeline_id"), table_name="stage_links")
    op.drop_table("stage_links")
