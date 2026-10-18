"""The git side of lanes (phase 13): a folder and a branch per lane, merged where they meet.
Real temporary repositories, a fake launcher, and the same Worktrees the app uses."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from gitrepos import make_repo, sh, write
from sqlalchemy import select
from test_lanes import (  # noqa: F401 - fixtures
    db_factory,
    finish_stage,
    launched,
    launcher,
    make_agent,
    scheduler,
    split_pipeline,
    task_row,
)

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.errors import ApiError
from agentic_os.models import (
    Project,
    Run,
    StageLink,
    Task,
    TaskRepo,
    TaskStatus,
    WorkspaceMode,
)
from agentic_os.services import changes, lane_git
from agentic_os.services import lanes as lane_ops
from agentic_os.services import tasks as task_ops
from agentic_os.services.gitx.runner import Repo
from agentic_os.services.worktrees import Worktrees


@pytest.fixture
def web(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "web", files={"shared.txt": "base\n"})


@pytest.fixture
def setup(db_factory, scheduler, web: Path):
    worktrees = Worktrees()
    scheduler.prepare_workspace = worktrees.prepare
    scheduler.release_workspace = worktrees.release
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Bea", "Fran", "Quim")]
        project = Project(
            workspace_id=DEFAULT_WORKSPACE,
            name="Web",
            path=str(web),
            path_key=str(web),
            workspace_mode=WorkspaceMode.WORKTREE,
            base_branch="main",
        )
        db.add(project)
        db.flush()
        ids = split_pipeline(db, project, agents, always=True)
        task_ops.create_task(db, project, "Filtro de pedidos")
        db.commit()
    return ids, web


def cwd_of(db_factory, launcher, code: str) -> Path:
    with db_factory() as db:
        return Path(db.get(Run, launched(launcher, code)).cwd)


def commit_in(folder: Path, name: str, text: str) -> None:
    write(folder, name, text)
    sh(folder, "add", "-A")
    sh(folder, "commit", "-q", "-m", f"work on {name}")


def reach_the_lanes(db_factory, scheduler, launcher) -> Path:
    """Requisitos leaves a loose file in the task's folder; both lanes start."""
    scheduler.step()
    work = cwd_of(db_factory, launcher, "T-1")
    write(work, "req.txt", "requisitos\n")  # not committed
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos")
    return work


def test_each_lane_works_in_a_folder_and_branch_of_its_own_from_the_tasks(
    db_factory, scheduler, launcher, setup
):
    _, web = setup
    work = reach_the_lanes(db_factory, scheduler, launcher)

    back = cwd_of(db_factory, launcher, "T-1·backend")
    front = cwd_of(db_factory, launcher, "T-1·frontend")
    assert back.name == "T-1-backend" and front.name == "T-1-frontend"
    assert back.parent == work.parent and back != work
    assert sh(back, "branch", "--show-current") == "agentic/T-1-backend"
    assert sh(front, "branch", "--show-current") == "agentic/T-1-frontend"
    # what Requisitos left loose was committed, so the lanes start from it
    assert (back / "req.txt").read_text("utf-8").strip() == "requisitos"
    assert sh(web, "rev-parse", "agentic/T-1-backend") == sh(web, "rev-parse", "agentic/T-1")
    with db_factory() as db:
        rows = {
            t.lane_key: db.scalar(select(TaskRepo).where(TaskRepo.task_id == t.id))
            for t in db.scalars(select(Task))
        }
        assert rows["backend"].branch == "agentic/T-1-backend"
        assert rows["backend"].base_commit == sh(web, "rev-parse", "agentic/T-1")
        assert rows[""].worktree_path == str(work)  # the task keeps its own folder meanwhile


def test_the_lanes_are_merged_into_the_task_where_they_meet(db_factory, scheduler, launcher, setup):
    _, web = setup
    work = reach_the_lanes(db_factory, scheduler, launcher)
    write(cwd_of(db_factory, launcher, "T-1·backend"), "api.py", "api\n")  # left loose
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "ui.tsx", "ui\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api lista")
    assert task_row(db_factory).status == "forked"
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "ui lista")

    mother = task_row(db_factory)
    assert mother.status == "running"  # QA, on the task that forked
    assert cwd_of(db_factory, launcher, "T-1") == work  # in its own folder, now up to date
    assert (work / "api.py").exists() and (work / "ui.tsx").exists()
    merges = sh(web, "log", "agentic/T-1", "--merges", "--format=%s").splitlines()
    assert len(merges) == 2 and all("T-1" in m for m in merges)

    finish_stage(db_factory, scheduler, launcher, "T-1", "todo bien")
    assert task_row(db_factory).status == "done"
    # the task's diff (phase 11) holds the work of all its lanes
    with db_factory() as db:
        (diff,) = changes.task_ranges(db, db.scalar(select(Task).where(Task.lane_key == "")))
        assert diff.usable
        names = sh(web, "diff", "--name-only", diff.old or "", diff.new or "").split()
        assert {"api.py", "ui.tsx", "req.txt"} <= set(names)
    # every folder is gone, every branch stays: the lanes' are part of the task's now
    assert not (work.parent / "T-1-backend").exists() and not work.exists()
    branches = sh(web, "branch", "--list", "agentic/*", "--format=%(refname:short)").split()
    assert set(branches) == {"agentic/T-1", "agentic/T-1-backend", "agentic/T-1-frontend"}
    assert (
        sh(web, "branch", "--merged", "agentic/T-1", "--format=%(refname:short)").count("agentic")
        == 3
    )


def test_lanes_that_touch_the_same_lines_wait_and_nothing_is_lost(
    db_factory, scheduler, launcher, setup
):
    work = reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "shared.txt", "versión backend\n")
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "shared.txt", "versión frontend\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")

    mother = task_row(db_factory)
    assert (mother.status, mother.waiting_reason) == ("waiting_human", "join_conflict")
    assert "shared.txt" in (mother.waiting_detail or "") and "frontend" in mother.waiting_detail
    assert sh(work, "status", "--porcelain") == ""  # the task's folder was left clean
    # the first lane did merge; the second is the one that clashes
    assert "versión backend" in (work / "shared.txt").read_text("utf-8")
    with db_factory() as db:
        task = db.get(Task, mother.id)
        found = lane_git.clashes(db, task, lane_ops.lanes_of(db, task, task.stage_id))
        assert [(c.name, c.lane, c.files) for c in found] == [("web", "frontend", ["shared.txt"])]


def test_the_conflict_can_be_resolved_in_a_scratch_worktree_and_the_join_goes_on(
    db_factory, scheduler, launcher, setup
):
    ids, web = setup
    reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "shared.txt", "versión backend\n")
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "shared.txt", "versión frontend\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")

    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        project = db.get(Project, mother.project_id)
        scheduler.release_workspace(db, mother, project)  # the branch is free for the editor
        resolutions = lane_git.prepare_editor(db, mother, project)
        db.commit()
        (resolution,) = resolutions
        assert resolution.name == "web" and resolution.conflicts == ["shared.txt"]
        folder = Path(resolution.path)
        write(folder, "shared.txt", "las dos versiones\n")
        sh(folder, "add", "shared.txt")
        assert lane_git.finish_editor(db, mother, project, resolution.repo_id) == []
        assert not folder.exists()
        task_ops.retry(db, mother)
        db.commit()

    after = task_row(db_factory)
    assert (after.status, after.stage_id) == ("queued", ids["stages"]["QA"])
    assert sh(web, "show", "agentic/T-1:shared.txt") == "las dos versiones"


def test_an_agent_can_resolve_the_join_on_the_tasks_branch(db_factory, scheduler, launcher, setup):
    ids, web = setup
    reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "shared.txt", "versión backend\n")
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "shared.txt", "versión frontend\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")

    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        project = db.get(Project, mother.project_id)
        agent = make_agent(db, "Resolutor")
        found = lane_git.clashes(db, mother, lane_ops.lanes_of(db, mother, mother.stage_id))
        scheduler.release_workspace(db, mother, project)
        resolver = lane_git.resolution_task(db, mother, project, agent.id, found)
        db.commit()
        assert resolver.resolves_task_id == mother.id
        assert "agentic/T-1-frontend" in resolver.description
    scheduler.step()
    folder = cwd_of(db_factory, launcher, "T-2")
    assert sh(folder, "branch", "--show-current") == "agentic/T-1"  # the task's own branch
    sh(folder, "merge", "agentic/T-1-frontend", check=False)  # what the agent does
    write(folder, "shared.txt", "mezcla del agente\n")
    sh(folder, "add", "-A")
    sh(folder, "commit", "-q", "-m", "resolve the join")
    finish_stage(db_factory, scheduler, launcher, "T-2", "resuelto")

    deadline = time.monotonic() + 15  # approving it joins the lanes on a background thread
    while time.monotonic() < deadline and task_row(db_factory).stage_id != ids["stages"]["QA"]:
        time.sleep(0.1)
    after = task_row(db_factory)
    assert after.stage_id == ids["stages"]["QA"] and after.status in ("queued", "running")
    assert sh(web, "show", "agentic/T-1:shared.txt") == "mezcla del agente"


def test_a_lane_reopened_by_qa_starts_from_what_the_task_has_now(
    db_factory, scheduler, launcher, setup
):
    ids, web = setup
    reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "api.py", "api v1\n")
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "ui.tsx", "ui v1\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")
    qa_folder = cwd_of(db_factory, launcher, "T-1")
    commit_in(qa_folder, "qa-notes.txt", "falla el backend\n")  # QA's own commit
    with db_factory() as db:
        db.get(Run, launched(launcher, "T-1")).reject_to_stage_id = ids["stages"]["Backend"]
        db.commit()
    finish_stage(db_factory, scheduler, launcher, "T-1", "el backend falla", verdict="rejected")

    lane = cwd_of(db_factory, launcher, "T-1·backend")
    assert sh(lane, "branch", "--show-current") == "agentic/T-1-backend"
    for name in ("api.py", "ui.tsx", "qa-notes.txt"):  # the lane sees everything merged
        assert (lane / name).exists(), name
    with db_factory() as db:
        lane_task = db.scalar(select(Task).where(Task.lane_key == "backend"))
        row = db.scalar(select(TaskRepo).where(TaskRepo.task_id == lane_task.id))
        assert row.base_commit == sh(web, "rev-parse", "agentic/T-1")  # its diff starts here

    commit_in(lane, "api.py", "api v2\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "arreglado")
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]
    assert (qa_folder / "api.py").read_text("utf-8").strip() == "api v2"


def test_cancelling_a_lane_removes_its_folder_and_the_join_goes_on(
    db_factory, scheduler, launcher, setup
):
    ids, _ = setup
    reach_the_lanes(db_factory, scheduler, launcher)
    front = cwd_of(db_factory, launcher, "T-1·frontend")
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "api.py", "api\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    assert front.is_dir()
    with db_factory() as db:
        lane = db.scalar(select(Task).where(Task.lane_key == "frontend"))
        lane_ops.cancel_lane(db, lane)
        db.flush()
        scheduler.release_finished(db, lane)
        db.commit()
    assert not front.exists()
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]
    assert task_row(db_factory, key="frontend").status == TaskStatus.CANCELLED


def test_a_lane_with_no_commits_leaves_nothing_to_merge(db_factory, scheduler, launcher, setup):
    _, web = setup
    reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "api.py", "api\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")  # did nothing at all
    merges = sh(web, "log", "agentic/T-1", "--merges", "--format=%s").splitlines()
    assert len(merges) == 1 and "backend" in merges[0]
    assert task_row(db_factory).stage_id is not None


def test_the_task_branch_naming_has_no_dots_or_middle_dots(db_factory):
    with db_factory() as db:
        project = Project(workspace_id=DEFAULT_WORKSPACE, name="x", path="D:/x", path_key="x")
        db.add(project)
        db.flush()
        mother = task_ops.create_task(db, project, "t", agent_id=make_agent(db).id)
        mother.number = 7
        lane = Task(
            workspace_id=DEFAULT_WORKSPACE, number=7, project_id=project.id, title="t",
            lane_key="backend.api-2",
        )  # fmt: skip
        assert lane.code == "T-7·backend.api-2" and lane.ref_name == "T-7-backend-api-2"
        from agentic_os.services.worktrees import branch_for

        assert (
            branch_for(lane) == "agentic/T-7-backend-api-2" and branch_for(mother) == "agentic/T-7"
        )
        _ = (Repo, StageLink)


def test_only_one_agent_resolves_a_join_at_a_time(db_factory, scheduler, launcher, setup):
    reach_the_lanes(db_factory, scheduler, launcher)
    commit_in(cwd_of(db_factory, launcher, "T-1·backend"), "shared.txt", "versión backend\n")
    commit_in(cwd_of(db_factory, launcher, "T-1·frontend"), "shared.txt", "versión frontend\n")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        project = db.get(Project, mother.project_id)
        agent = make_agent(db, "Resolutor")
        found = lane_git.clashes(db, mother, lane_ops.lanes_of(db, mother, mother.stage_id))
        lane_git.resolution_task(db, mother, project, agent.id, found)
        with pytest.raises(ApiError) as caught:
            lane_git.resolution_task(db, mother, project, agent.id, found)
        assert caught.value.code == "resolution_exists"


def test_a_finished_task_that_nobody_released_gets_its_folder_back(
    db_factory, scheduler, launcher, setup
):
    """A join resolved after the lanes ended can finish the task outside any run end."""
    scheduler.step()
    work = cwd_of(db_factory, launcher, "T-1")
    assert work.is_dir()
    with db_factory() as db:
        run = db.get(Run, launched(launcher, "T-1"))
        run.status = "completed"
        task = db.get(Task, run.task_id)
        task.status = TaskStatus.DONE
        db.commit()
    assert scheduler.release_orphans() == 1
    assert not work.exists()
    assert task_row(db_factory).worktree_path is None
    assert scheduler.release_orphans() == 0
