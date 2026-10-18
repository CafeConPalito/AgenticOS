"""project repositories

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 18:00:00.000000

Phase 12: a project has a list of git repositories (found in its folder or linked from outside),
and tasks and runs keep what they did per repository.

The migration never touches the disk. Projects that already show git use (worktree mode, or tasks
and runs with a branch or snapshots) get their folder as the repository they used until now; the
others are looked at when the backend starts (services.repos.sync).
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_repos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("path_key", sa.Text(), nullable=False),
        sa.Column("rel_path", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("base_branch", sa.String(length=120), nullable=True),
        sa.Column("participates", sa.Boolean(), nullable=False),
        sa.Column("linked", sa.Boolean(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("pull_mode", sa.String(length=8), nullable=False),
        sa.Column("forge", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pull_mode IN ('ff_only', 'merge', 'rebase')", name="ck_project_repos_pull_mode"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_repos_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_repos"),
        sa.UniqueConstraint("project_id", "path_key", name="uq_project_repos_project_path"),
    )
    op.create_index("ix_project_repos_project_id", "project_repos", ["project_id"])
    op.create_index("ix_project_repos_workspace_id", "project_repos", ["workspace_id"])

    op.create_table(
        "task_repos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("repo_id", sa.String(length=36), nullable=False),
        sa.Column("branch", sa.String(length=120), nullable=False),
        sa.Column("worktree_path", sa.Text(), nullable=True),
        sa.Column("base_commit", sa.String(length=40), nullable=True),
        sa.Column("integrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("integrated_sha", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_task_repos_task_id_tasks", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["project_repos.id"],
            name="fk_task_repos_repo_id_project_repos",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_repos"),
        sa.UniqueConstraint("task_id", "repo_id", name="uq_task_repos_task_repo"),
    )
    op.create_index("ix_task_repos_task_id", "task_repos", ["task_id"])
    op.create_index("ix_task_repos_repo_id", "task_repos", ["repo_id"])

    op.create_table(
        "run_repos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("repo_id", sa.String(length=36), nullable=True),
        sa.Column("repo_name", sa.String(length=80), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("snapshot_start", sa.String(length=40), nullable=True),
        sa.Column("snapshot_end", sa.String(length=40), nullable=True),
        sa.Column("snapshot_skipped", sa.Integer(), nullable=False),
        sa.Column("changes_files", sa.Integer(), nullable=True),
        sa.Column("changes_added", sa.Integer(), nullable=True),
        sa.Column("changes_deleted", sa.Integer(), nullable=True),
        sa.Column("refs_start", sa.JSON(), nullable=True),
        sa.Column("activity", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_run_repos_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["project_repos.id"],
            name="fk_run_repos_repo_id_project_repos",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_repos"),
    )
    op.create_index("ix_run_repos_run_id", "run_repos", ["run_id"])
    op.create_index("ix_run_repos_repo_id", "run_repos", ["repo_id"])

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("repo_scan_depth", sa.Integer(), nullable=False, server_default="3")
        )

    _backfill(op.get_bind())

    # Their data now lives in task_repos and run_repos (one row per repository).
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("snapshot_start")
        batch_op.drop_column("snapshot_end")
        batch_op.drop_column("snapshot_skipped")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("base_commit")


def _backfill(conn: sa.Connection) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
    projects = conn.execute(
        sa.text(
            "SELECT p.id, p.workspace_id, p.name, p.path, p.path_key, p.base_branch FROM projects p"
            " WHERE p.workspace_mode = 'worktree'"
            " OR EXISTS (SELECT 1 FROM tasks t WHERE t.project_id = p.id AND t.branch IS NOT NULL)"
            " OR EXISTS (SELECT 1 FROM runs r WHERE r.project_id = p.id"
            "            AND (r.snapshot_start IS NOT NULL OR r.snapshot_end IS NOT NULL))"
        )
    ).all()
    for project in projects:
        repo_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO project_repos (id, workspace_id, project_id, path, path_key, rel_path,"
                " name, base_branch, participates, linked, missing, position, pull_mode,"
                " created_at, updated_at) VALUES (:id, :workspace_id, :project_id, :path,"
                " :path_key, '', :name, :base_branch, 1, 0, 0, 0, 'ff_only', :now, :now)"
            ),
            {
                "id": repo_id,
                "workspace_id": project.workspace_id,
                "project_id": project.id,
                "path": project.path,
                "path_key": project.path_key,
                "name": project.name[:80],
                "base_branch": project.base_branch,
                "now": now,
            },
        )
        for task in conn.execute(
            sa.text(
                "SELECT id, branch, worktree_path, base_commit FROM tasks"
                " WHERE project_id = :p AND branch IS NOT NULL"
            ),
            {"p": project.id},
        ).all():
            conn.execute(
                sa.text(
                    "INSERT INTO task_repos (id, task_id, repo_id, branch, worktree_path, base_commit)"
                    " VALUES (:id, :task, :repo, :branch, :worktree, :base)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "task": task.id,
                    "repo": repo_id,
                    "branch": task.branch,
                    "worktree": task.worktree_path,
                    "base": task.base_commit,
                },
            )
        for run in conn.execute(
            sa.text(
                "SELECT id, cwd, snapshot_start, snapshot_end, snapshot_skipped, changes_files,"
                " changes_added, changes_deleted FROM runs WHERE project_id = :p"
                " AND (snapshot_start IS NOT NULL OR snapshot_end IS NOT NULL)"
            ),
            {"p": project.id},
        ).all():
            conn.execute(
                sa.text(
                    "INSERT INTO run_repos (id, run_id, repo_id, repo_name, path, snapshot_start,"
                    " snapshot_end, snapshot_skipped, changes_files, changes_added, changes_deleted)"
                    " VALUES (:id, :run, :repo, :name, :path, :start, :end, :skipped, :files,"
                    " :added, :deleted)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "run": run.id,
                    "repo": repo_id,
                    "name": project.name[:80],
                    "path": run.cwd,
                    "start": run.snapshot_start,
                    "end": run.snapshot_end,
                    "skipped": run.snapshot_skipped,
                    "files": run.changes_files,
                    "added": run.changes_added,
                    "deleted": run.changes_deleted,
                },
            )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("base_commit", sa.String(length=40), nullable=True))
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("snapshot_start", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("snapshot_end", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("snapshot_skipped", sa.Integer(), nullable=False, server_default="0")
        )
    # One repository per task and run was all there was: the first row of each goes back.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE tasks SET base_commit = (SELECT base_commit FROM task_repos t"
            " WHERE t.task_id = tasks.id ORDER BY t.id LIMIT 1)"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE runs SET snapshot_start = (SELECT snapshot_start FROM run_repos r"
            " WHERE r.run_id = runs.id ORDER BY r.id LIMIT 1),"
            " snapshot_end = (SELECT snapshot_end FROM run_repos r"
            " WHERE r.run_id = runs.id ORDER BY r.id LIMIT 1),"
            " snapshot_skipped = COALESCE((SELECT snapshot_skipped FROM run_repos r"
            " WHERE r.run_id = runs.id ORDER BY r.id LIMIT 1), 0)"
        )
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("repo_scan_depth")
    op.drop_index("ix_run_repos_repo_id", table_name="run_repos")
    op.drop_index("ix_run_repos_run_id", table_name="run_repos")
    op.drop_table("run_repos")
    op.drop_index("ix_task_repos_repo_id", table_name="task_repos")
    op.drop_index("ix_task_repos_task_id", table_name="task_repos")
    op.drop_table("task_repos")
    op.drop_index("ix_project_repos_workspace_id", table_name="project_repos")
    op.drop_index("ix_project_repos_project_id", table_name="project_repos")
    op.drop_table("project_repos")
