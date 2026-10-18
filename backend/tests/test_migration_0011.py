"""Migration 0011 (phase 12): projects with git use get their folder as a repository, and their
tasks and runs get the per-repository rows; the rest is left for the first startup."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from agentic_os.config import Settings
from agentic_os.db.migrate import alembic_config
from agentic_os.db.session import create_db_engine, database_url

NOW = "2026-10-17 12:00:00.000000"


def _project(conn, pid: str, name: str, mode: str, base: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO projects (id, workspace_id, name, color, description, path, path_key,"
            " workspace_mode, base_branch, created_at, updated_at)"
            " VALUES (:id, 'default', :name, '#fff', '', :path, :key, :mode, :base, :now, :now)"
        ),
        {
            "id": pid,
            "name": name,
            "path": f"C:/p/{name}",
            "key": f"c:/p/{name}",
            "mode": mode,
            "base": base,
            "now": NOW,
        },
    )


def _task(conn, tid: str, number: int, pid: str, branch: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO tasks (id, workspace_id, number, project_id, title, description,"
            " priority, status, queue_position, rejections, worktree_path, branch, base_commit,"
            " created_at, updated_at) VALUES (:id, 'default', :n, :p, 't', '', 'normal', 'done',"
            " 0, 0, :wt, :branch, :base, :now, :now)"
        ),
        {
            "id": tid,
            "n": number,
            "p": pid,
            "wt": None,
            "branch": branch,
            "base": "a" * 40 if branch else None,
            "now": NOW,
        },
    )


def _run(conn, rid: str, pid: str, start: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO runs (id, workspace_id, project_id, agent_name, agent_color,"
            " project_name, cli, model, prompt, cwd, status, activity, cols, rows, log_path,"
            " extra_transcripts, input_tokens, output_tokens, thinking_tokens, cache_read_tokens,"
            " cache_creation_tokens, usage_models, usage_status, log_purged, account_label,"
            " snapshot_start, snapshot_end, snapshot_skipped, changes_files, changes_added,"
            " changes_deleted, created_at, updated_at)"
            " VALUES (:id, 'default', :p, 'Dev', '#fff', 'Web', 'claude', '', 'p', 'C:/wt/T-1',"
            " 'exited', 'idle', 120, 32, '', '[]', 0, 0, 0, 0, 0, '{}', 'pending', 0, '',"
            " :start, :end, 0, 3, 10, 2, :now, :now)"
        ),
        {"id": rid, "p": pid, "start": start, "end": start and "b" * 40, "now": NOW},
    )


def test_git_projects_get_a_repository_and_the_rest_wait_for_startup(settings: Settings):
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    config = alembic_config(engine)
    command.upgrade(config, "0010")
    with engine.begin() as conn:
        _project(conn, "p-wt", "Web", "worktree", "main")
        _task(conn, "t-wt", 1, "p-wt", "agentic/T-1")
        _run(conn, "r-wt", "p-wt", "c" * 40)
        _project(conn, "p-direct-git", "Api", "direct", None)
        _task(conn, "t-direct", 1 + 1, "p-direct-git", None)
        _run(conn, "r-direct", "p-direct-git", "d" * 40)
        _project(conn, "p-plain", "Notes", "direct", None)
        _task(conn, "t-plain", 3, "p-plain", None)
        _run(conn, "r-plain", "p-plain", None)

    command.upgrade(config, "0011")

    with engine.begin() as conn:
        repos = {
            r.project_id: r
            for r in conn.execute(
                text(
                    "SELECT project_id, id, rel_path, name, base_branch, participates, linked,"
                    " missing, pull_mode FROM project_repos"
                )
            )
        }
        # Worktree mode and snapshots in a direct folder: they used git. The plain one did not.
        assert set(repos) == {"p-wt", "p-direct-git"}
        web = repos["p-wt"]
        assert (web.rel_path, web.name, web.base_branch) == ("", "Web", "main")
        assert (web.participates, web.linked, web.missing, web.pull_mode) == (1, 0, 0, "ff_only")

        task_repo = conn.execute(
            text("SELECT repo_id, branch, base_commit FROM task_repos WHERE task_id = 't-wt'")
        ).one()
        assert (task_repo.repo_id, task_repo.branch, task_repo.base_commit) == (
            web.id,
            "agentic/T-1",
            "a" * 40,
        )
        # Tasks without a branch have nothing to move.
        assert conn.execute(text("SELECT count(*) FROM task_repos")).scalar() == 1

        run_repo = conn.execute(
            text(
                "SELECT repo_id, path, snapshot_start, snapshot_end, changes_files, changes_added,"
                " changes_deleted FROM run_repos WHERE run_id = 'r-wt'"
            )
        ).one()
        assert tuple(run_repo) == (web.id, "C:/wt/T-1", "c" * 40, "b" * 40, 3, 10, 2)
        assert conn.execute(text("SELECT count(*) FROM run_repos")).scalar() == 2
        depth = conn.execute(text("SELECT repo_scan_depth FROM projects WHERE id = 'p-plain'"))
        assert depth.scalar() == 3

    command.downgrade(config, "0010")
    with engine.begin() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master"))}
        assert not {"project_repos", "task_repos", "run_repos"} & tables
        assert conn.execute(text("SELECT count(*) FROM projects")).scalar() == 3
    engine.dispose()
