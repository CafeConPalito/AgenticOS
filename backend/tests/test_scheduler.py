"""The scheduler's decisions with a fake launcher (no PTY): order, concurrency, the busy folder,
run ends, pause, recovery and launch errors."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    InboxItem,
    InboxKind,
    Priority,
    Project,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.schemas.pipeline import PipelineWrite, StageWrite
from agentic_os.services import inbox, pipelines
from agentic_os.services import tasks as task_ops
from agentic_os.services.scheduler import Scheduler, blocked_reason


class FakeLauncher:
    def __init__(self) -> None:
        self.launched: list[tuple[str, str]] = []  # (task code, run id)
        self.error: ApiError | Exception | None = None

    def launch(self, db, agent, project, prompt, task=None, cwd=None) -> Run:
        if self.error is not None:
            raise self.error
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_id=agent.id,
            project_id=project.id,
            agent_name=agent.name,
            agent_color=agent.color,
            project_name=project.name,
            cli=agent.cli,
            prompt=prompt,
            cwd=cwd or project.path,
            status=RunStatus.RUNNING,
            task_id=task.id if task else None,
            stage_id=task.stage_id if task else None,
        )
        db.add(run)
        db.commit()
        self.launched.append((task.code, run.id))
        return run


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def launcher() -> FakeLauncher:
    return FakeLauncher()


@pytest.fixture
def scheduler(db_factory, launcher) -> Scheduler:
    return Scheduler(db_factory, launcher)  # not started: the tests call step()


def make_agent(db: Session, name: str = "Dev", concurrency: int = 1) -> Agent:
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, name=name, max_concurrency=concurrency)
    db.add(agent)
    db.flush()
    return agent


def make_project(db: Session, name: str, mode: WorkspaceMode = WorkspaceMode.DIRECT) -> Project:
    project = Project(
        workspace_id=DEFAULT_WORKSPACE,
        name=name,
        path=f"D:/{name}",
        path_key=name,
        workspace_mode=mode,
    )
    db.add(project)
    db.flush()
    return project


def add_task(
    db: Session, project: Project, agent: Agent, title: str, priority=Priority.NORMAL
) -> Task:
    return task_ops.create_task(db, project, title, priority=priority, agent_id=agent.id)


def end_run(
    db_factory,
    scheduler: Scheduler,
    run_id: str,
    status: RunStatus,
    summary: str = "hecho",
    verdict: str | None = "approved",
) -> None:
    with db_factory() as db:
        run = db.get(Run, run_id)
        run.status, run.summary = status, summary
        run.verdict = verdict if status == RunStatus.COMPLETED else None
        db.commit()
    scheduler.run_ended(run_id)
    scheduler.step()


def status_of(db_factory, code: str) -> tuple[str, str | None]:
    with db_factory() as db:
        task = db.query(Task).filter(Task.number == int(code[2:])).one()
        return task.status, task.waiting_reason


def test_an_agent_takes_its_queue_in_order_across_projects(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        web, blog = make_project(db, "web"), make_project(db, "blog")
        add_task(db, web, dev, "normal")  # T-1
        add_task(db, blog, dev, "baja", Priority.LOW)  # T-2
        add_task(db, blog, dev, "alta", Priority.HIGH)  # T-3
        db.commit()

    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-3"]  # concurrency 1
    scheduler.step()
    assert len(launcher.launched) == 1

    end_run(db_factory, scheduler, launcher.launched[0][1], RunStatus.COMPLETED)
    assert status_of(db_factory, "T-3") == ("done", None)
    assert [code for code, _ in launcher.launched] == ["T-3", "T-1"]
    end_run(db_factory, scheduler, launcher.launched[1][1], RunStatus.COMPLETED)
    assert [code for code, _ in launcher.launched] == ["T-3", "T-1", "T-2"]


def test_reorder_changes_the_next_task(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        a, b, c = (add_task(db, web, dev, t) for t in ("a", "b", "c"))
        db.commit()
        task_ops.reorder(db, dev.id, [c.id, a.id, b.id])
        db.commit()
        with pytest.raises(ApiError) as error:  # a stale list (the queue changed meanwhile)
            task_ops.reorder(db, dev.id, [a.id, b.id])
        assert error.value.code == "queue_changed"
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-3"]


def test_concurrency_and_the_busy_direct_folder(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db, concurrency=2)
        web, blog = make_project(db, "web"), make_project(db, "blog")
        add_task(db, web, dev, "web 1")  # T-1
        add_task(db, web, dev, "web 2")  # T-2: same direct folder
        add_task(db, blog, dev, "blog 1")  # T-3
        db.commit()

    scheduler.step()
    # T-2 is skipped (folder busy) and the agent takes T-3 instead.
    assert [code for code, _ in launcher.launched] == ["T-1", "T-3"]
    with db_factory() as db:
        t2 = db.query(Task).filter(Task.number == 2).one()
        assert blocked_reason(db, t2, db.get(Project, t2.project_id)) == "folder_busy"

    end_run(db_factory, scheduler, launcher.launched[0][1], RunStatus.COMPLETED)
    assert [code for code, _ in launcher.launched] == ["T-1", "T-3", "T-2"]


def test_a_worktree_project_runs_tasks_in_parallel(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db, concurrency=3)
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        for title in ("a", "b"):
            add_task(db, web, dev, title)
        db.commit()
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2"]


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (RunStatus.EXITED, WaitingReason.RUN_EXITED),
        (RunStatus.FAILED, WaitingReason.RUN_FAILED),
        (RunStatus.STOPPED, WaitingReason.RUN_STOPPED),
    ],
)
def test_a_run_ending_badly_leaves_its_task_waiting(
    db_factory, scheduler, launcher, status, reason
):
    with db_factory() as db:
        dev = make_agent(db)
        web, blog = make_project(db, "web"), make_project(db, "blog")
        add_task(db, web, dev, "falla")
        add_task(db, blog, dev, "siguiente")
        db.commit()
    scheduler.step()
    end_run(db_factory, scheduler, launcher.launched[0][1], status)
    assert status_of(db_factory, "T-1") == ("waiting_human", reason)
    # The agent goes on with its queue.
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2"]


def test_retry_goes_to_the_front_and_manual_completion(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        add_task(db, web, dev, "primera")
        add_task(db, web, dev, "segunda")
        db.commit()
    scheduler.step()
    end_run(db_factory, scheduler, launcher.launched[0][1], RunStatus.EXITED)
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2"]

    with db_factory() as db:
        t1 = db.query(Task).filter(Task.number == 1).one()
        task_ops.retry(db, t1)
        db.commit()
    end_run(db_factory, scheduler, launcher.launched[1][1], RunStatus.COMPLETED)
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2", "T-1"]

    # The user ends the stage while the run is alive: when the run ends (stopped), it counts.
    scheduler.complete_manually(launcher.launched[2][1], "lo cierro yo")
    end_run(db_factory, scheduler, launcher.launched[2][1], RunStatus.STOPPED)
    assert status_of(db_factory, "T-1") == ("done", None)


def test_pause_and_resume(db_factory, scheduler, launcher):
    scheduler.set_paused(True)
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web"), dev, "espera")
        db.commit()
    scheduler.step()
    assert launcher.launched == [] and scheduler.paused
    scheduler.set_paused(False)
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-1"]


def test_recovery_after_a_restart(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web"), dev, "a medias")
        db.commit()
    scheduler.step()
    assert scheduler.recover() == 1
    assert status_of(db_factory, "T-1") == ("waiting_human", WaitingReason.INTERRUPTED)


def test_launch_errors(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web"), dev, "agy ocupado")
        db.commit()
    launcher.error = ApiError(409, "agy_folder_busy", "busy")
    scheduler.step()
    assert status_of(db_factory, "T-1") == ("queued", None)  # retried on the next tick

    launcher.error = ApiError(422, "cli_not_installed", "claude is not installed", "cli")
    scheduler.step()
    assert status_of(db_factory, "T-1") == ("waiting_human", WaitingReason.LAUNCH_FAILED)
    with db_factory() as db:
        assert db.query(Task).one().waiting_detail == "claude is not installed"


def test_drafts_and_cancelled_tasks_are_not_started(db_factory, scheduler, launcher):
    with db_factory() as db:
        draft = make_agent(db, "Borrador")
        draft.status = "draft"
        dev = make_agent(db)
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        add_task(db, web, draft, "del borrador")
        cancelled = add_task(db, web, dev, "cancelada")
        task_ops.finish(db, cancelled, TaskStatus.CANCELLED, task_ops.TaskEventKind.CANCELLED)
        db.commit()
    scheduler.step()
    assert launcher.launched == []


# ---------------------------------------------------------------- pipelines (phase 05 H3)
def web_pipeline(db: Session, project: Project, agents: list[Agent], **options) -> list[str]:
    """Requisitos → Desarrollo → QA (QA rejects to Desarrollo); returns the stage ids."""
    review = options.pop("review", ())
    payload = PipelineWrite(
        name="Desarrollo web",
        stages=[
            StageWrite(name=name, agent_id=agent.id, requires_review=name in review, reject_to=to)
            for (name, to), agent in zip(
                (("Requisitos", None), ("Desarrollo", None), ("QA", 1)), agents, strict=True
            )
        ],
        **options,
    )
    pipeline = pipelines.save(db, project, payload)
    db.flush()
    db.refresh(pipeline)
    return [s.id for s in pipeline.stages]


def current(db_factory, number: int = 1) -> Task:
    with db_factory() as db:
        task = db.query(Task).filter(Task.number == number).one()
        db.expunge(task)
        return task


def last_run(launcher: FakeLauncher) -> str:
    return launcher.launched[-1][1]


def test_a_task_goes_through_the_pipeline_and_back_when_qa_rejects(db_factory, scheduler, launcher):
    with db_factory() as db:
        ana, dev, qa = make_agent(db, "Ana"), make_agent(db, "Dev"), make_agent(db, "QA")
        web = make_project(db, "web")
        req, desarrollo, qa_stage = web_pipeline(db, web, [ana, dev, qa])
        task_ops.create_task(db, web, "Login con Google")
        db.commit()

    scheduler.step()
    assert (current(db_factory).stage_id, current(db_factory).agent_id) == (req, ana.id)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "requisitos claros")
    assert current(db_factory).stage_id == desarrollo
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "login hecho")
    assert current(db_factory).stage_id == qa_stage
    end_run(
        db_factory,
        scheduler,
        last_run(launcher),
        RunStatus.COMPLETED,
        "falta el test del callback",
        verdict="rejected",
    )
    task = current(db_factory)
    assert (task.stage_id, task.rejections, task.status) == (desarrollo, 1, "running")

    with db_factory() as db:  # the new Dev run knows why it came back
        context = task_ops.task_context(db, db.get(Task, task.id))
    assert context.rejection == "falta el test del callback"
    assert context.stage_name == "Desarrollo" and (context.stage_index, context.stage_count) == (
        2,
        3,
    )
    assert [line.split(":")[0] for line in context.history] == [
        "- Requisitos · Ana terminó",
        "- Desarrollo · Dev terminó",
        "- QA · QA rechazó",
    ]

    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "test añadido")
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "todo bien")
    assert current(db_factory).status == "done"
    assert len(launcher.launched) == 5


def test_too_many_rejections_wait_for_the_user(db_factory, scheduler, launcher):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Dev", "QA")]
        web = make_project(db, "web")
        web_pipeline(db, web, agents, max_rejections=1)
        task_ops.create_task(db, web, "bucle")
        db.commit()
    scheduler.step()
    for _ in range(2):  # Requisitos, Desarrollo
        end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "mal", "rejected")
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)  # Dev again
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "peor", "rejected")
    task = current(db_factory)
    assert (task.status, task.waiting_reason, task.waiting_detail, task.rejections) == (
        "waiting_human",
        "max_rejections",
        "peor",
        2,
    )


def test_review_gate(db_factory, scheduler, launcher):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Dev", "QA")]
        web = make_project(db, "web")
        req, desarrollo, qa_stage = web_pipeline(db, web, agents, review=("Desarrollo",))
        task_ops.create_task(db, web, "con revisión")
        db.commit()
    scheduler.step()
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "listo para revisar")
    assert (current(db_factory).status, current(db_factory).stage_id) == ("review", desarrollo)
    scheduler.step()
    assert len(launcher.launched) == 2  # nothing starts while it waits for the review

    with db_factory() as db:
        task = db.get(Task, current(db_factory).id)
        with pytest.raises(ApiError):  # a rejection needs a reason
            task_ops.review(db, task, approve=False)
        task_ops.review(db, task, approve=False, reason="vuelve a requisitos", target_stage_id=req)
        db.commit()
    assert (current(db_factory).status, current(db_factory).stage_id) == ("queued", req)

    scheduler.step()
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    with db_factory() as db:
        task_ops.review(db, db.get(Task, current(db_factory).id), approve=True)
        db.commit()
    assert (current(db_factory).status, current(db_factory).stage_id) == ("queued", qa_stage)


def test_a_stage_without_agent_waits_and_agent_changes_move_the_queue(
    db_factory, scheduler, launcher
):
    scheduler.set_paused(True)
    with db_factory() as db:
        ana, dev, qa = make_agent(db, "Ana"), make_agent(db, "Dev"), make_agent(db, "QA")
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        stages = web_pipeline(db, web, [ana, dev, qa])
        task_ops.create_task(db, web, "en cola de Ana")
        db.commit()
        # The first stage gets another agent: its queued task follows it.
        pipeline = pipelines.save(
            db,
            web,
            PipelineWrite(
                stages=[
                    StageWrite(id=stages[0], name="Requisitos", agent_id=dev.id),
                    StageWrite(id=stages[1], name="Desarrollo", agent_id=None),
                    StageWrite(id=stages[2], name="QA", agent_id=qa.id, reject_to=1),
                ]
            ),
        )
        db.commit()
        assert [s.id for s in pipeline.stages] == stages
    assert current(db_factory).agent_id == dev.id
    scheduler.set_paused(False)
    scheduler.step()
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    task = current(db_factory)
    assert (task.status, task.waiting_reason, task.stage_id) == (
        "waiting_human",
        "no_agent",
        stages[1],
    )


# ---------------------------------------------------------------- code review (phase 05)
def test_a_first_stage_without_agent_waits_instead_of_queueing_on_nobody(
    db_factory, scheduler, launcher
):
    with db_factory() as db:
        ana, dev, qa = make_agent(db, "Ana"), make_agent(db, "Dev"), make_agent(db, "QA")
        web = make_project(db, "web")
        stages = web_pipeline(db, web, [ana, dev, qa])
        pipelines.save(
            db,
            web,
            PipelineWrite(
                stages=[
                    StageWrite(id=stages[0], name="Requisitos", agent_id=None),
                    StageWrite(id=stages[1], name="Desarrollo", agent_id=dev.id),
                    StageWrite(id=stages[2], name="QA", agent_id=qa.id, reject_to=1),
                ]
            ),
        )
        task_ops.create_task(db, web, "sin analista")
        db.commit()
    task = current(db_factory)
    assert (task.status, task.waiting_reason, task.agent_id) == ("waiting_human", "no_agent", None)

    with db_factory() as db:  # the stage gets an agent: retrying uses it
        pipelines.save(
            db,
            db.get(Project, task.project_id),
            PipelineWrite(
                stages=[
                    StageWrite(id=stages[0], name="Requisitos", agent_id=ana.id),
                    StageWrite(id=stages[1], name="Desarrollo", agent_id=dev.id),
                    StageWrite(id=stages[2], name="QA", agent_id=qa.id, reject_to=1),
                ]
            ),
        )
        task_ops.retry(db, db.get(Task, task.id))
        db.commit()
    assert (current(db_factory).status, current(db_factory).agent_id) == ("queued", ana.id)


def test_retry_after_too_many_rejections_goes_back_to_the_fixing_stage(
    db_factory, scheduler, launcher
):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Dev", "QA")]
        web = make_project(db, "web")
        _, desarrollo, _ = web_pipeline(db, web, agents, max_rejections=1)
        task_ops.create_task(db, web, "bucle")
        db.commit()
    scheduler.step()
    for _ in range(2):
        end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "mal", "rejected")
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED)
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.COMPLETED, "peor", "rejected")
    assert current(db_factory).waiting_reason == "max_rejections"

    with db_factory() as db:
        task_ops.retry(db, db.get(Task, current(db_factory).id))
        db.commit()
    task = current(db_factory)
    assert (task.status, task.stage_id, task.rejections) == ("queued", desarrollo, 0)


def test_a_failed_launch_keeps_the_prepared_worktree(db_factory, scheduler, launcher):
    def prepare(db, task, project):
        task.worktree_path, task.branch = "D:/web.wt/T-1", "agentic/T-1"
        return task.worktree_path

    scheduler.prepare_workspace = prepare
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web", WorkspaceMode.WORKTREE), dev, "sin CLI")
        db.commit()
    launcher.error = ApiError(422, "cli_not_installed", "claude is not installed", "cli")
    scheduler.step()
    task = current(db_factory)
    assert (task.status, task.waiting_reason) == ("waiting_human", "launch_failed")
    assert (task.worktree_path, task.branch) == ("D:/web.wt/T-1", "agentic/T-1")


def test_a_manual_summary_only_applies_to_its_own_run(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web"), dev, "carrera")
        db.commit()
    scheduler.step()
    scheduler.complete_manually("another-run", "no es para esta")
    end_run(db_factory, scheduler, last_run(launcher), RunStatus.EXITED)
    assert status_of(db_factory, "T-1") == ("waiting_human", WaitingReason.RUN_EXITED)


def test_a_run_idle_for_too_long_is_reported_as_stalled(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web"), dev, "sin terminar")
        db.commit()
    scheduler.step()
    run_id = last_run(launcher)
    with db_factory() as db:
        db.get(Run, run_id).idle_since = utcnow() - timedelta(minutes=11)
        db.commit()
    assert scheduler.check_stalled() == 1
    assert scheduler.check_stalled() == 0  # one notice per run
    with db_factory() as db:
        [item] = db.query(InboxItem).all()
        assert (item.kind, item.status, item.run_id) == ("stalled", "pending", run_id)

    end_run(db_factory, scheduler, run_id, RunStatus.COMPLETED)  # it ends: no longer stalled
    with db_factory() as db:
        assert db.query(InboxItem).filter_by(kind="stalled").one().status == "resolved"


# ---------------------------------------------------------------- code review (phase 06)
def test_live_waits_hold_the_agent_until_their_cli_is_gone(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db)
        web, blog = make_project(db, "web"), make_project(db, "blog")
        add_task(db, web, dev, "pregunta")
        add_task(db, blog, dev, "siguiente")
        db.commit()
    scheduler.step()
    with db_factory() as db:
        task = db.query(Task).filter(Task.number == 1).one()
        task_ops.wait_for_human(db, task, WaitingReason.HUMAN_REQUEST, "¿A o B?")
        db.commit()
        with pytest.raises(ApiError) as error:  # a second run would duplicate the first
            task_ops.retry(db, db.get(Task, task.id))
        assert error.value.code == "task_live"
    scheduler.step()
    assert len(launcher.launched) == 1  # the waiting task still holds the agent (concurrency 1)

    end_run(db_factory, scheduler, last_run(launcher), RunStatus.EXITED)
    assert status_of(db_factory, "T-1") == ("waiting_human", "question_pending")
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2"]  # the agent is free


def test_recovery_turns_live_waits_into_offline_ones(db_factory, scheduler, launcher):
    with db_factory() as db:
        dev = make_agent(db, concurrency=2)
        web = make_project(db, "web", WorkspaceMode.WORKTREE)
        add_task(db, web, dev, "pregunta")
        add_task(db, web, dev, "permiso")
        db.commit()
    scheduler.step()
    with db_factory() as db:
        first, second = db.query(Task).order_by(Task.number).all()
        task_ops.wait_for_human(db, first, WaitingReason.HUMAN_REQUEST)
        task_ops.wait_for_human(db, second, WaitingReason.PERMISSION)
        db.commit()
    assert scheduler.recover() == 2
    assert status_of(db_factory, "T-1") == ("waiting_human", "question_pending")
    assert status_of(db_factory, "T-2") == ("waiting_human", "interrupted")


def test_a_subagent_ending_frees_its_permission_wait_and_releases_last(
    db_factory, scheduler, launcher
):
    released: list[str] = []
    scheduler.release_workspace = lambda db, task, project: released.append(task.code)
    with db_factory() as db:
        dev = make_agent(db)
        add_task(db, make_project(db, "web", WorkspaceMode.WORKTREE), dev, "con hija")
        db.commit()
    scheduler.step()
    parent_id = last_run(launcher)
    with db_factory() as db:
        parent = db.get(Run, parent_id)
        child = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_name="Dev",
            agent_color="#fff",
            project_name="web",
            cli="claude",
            prompt="hija",
            cwd=parent.cwd,
            status=RunStatus.RUNNING,
            task_id=parent.task_id,
            parent_run_id=parent_id,
        )
        db.add(child)
        db.flush()
        task = db.get(Task, parent.task_id)
        inbox.create(db, InboxKind.APPROVAL, "¿Puedo?", task=task, run=child, command="rm x")
        task_ops.wait_for_human(db, task, WaitingReason.PERMISSION, "rm x")
        db.commit()
        child_id = child.id
    end_run(db_factory, scheduler, child_id, RunStatus.STOPPED)
    with db_factory() as db:
        assert db.query(InboxItem).one().status == "resolved"
    assert status_of(db_factory, "T-1") == ("running", None)

    # The parent ends while another subagent is alive: the worktree waits for it.
    with db_factory() as db:
        other = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_name="Dev",
            agent_color="#fff",
            project_name="web",
            cli="claude",
            prompt="otra",
            cwd="x",
            status=RunStatus.RUNNING,
            task_id=db.get(Run, parent_id).task_id,
            parent_run_id=parent_id,
        )
        db.add(other)
        db.commit()
        other_id = other.id
    end_run(db_factory, scheduler, parent_id, RunStatus.COMPLETED)
    assert status_of(db_factory, "T-1") == ("done", None)
    assert released == []
    end_run(db_factory, scheduler, other_id, RunStatus.STOPPED)
    assert released == ["T-1"]
