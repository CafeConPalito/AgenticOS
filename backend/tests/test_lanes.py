"""Forks, lanes and joins (phase 13) with the scheduler and a fake launcher: no PTY, no LLM."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_scheduler import (  # noqa: F401 - fixtures
    FakeLauncher,
    db_factory,
    end_run,
    launcher,
    make_agent,
    make_project,
    scheduler,
)

from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    BranchDecision,
    DecisionBy,
    InboxItem,
    InboxKind,
    Project,
    Run,
    Stage,
    StageLink,
    Task,
    TaskEvent,
    TaskEventKind,
    TaskStatus,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.schemas.pipeline import LinkWrite, PipelineWrite, StageWrite
from agentic_os.services import context as ctx_module
from agentic_os.services import lanes, pipelines
from agentic_os.services import tasks as task_ops
from agentic_os.services.runs.manager import RunManager

COND_BACK = "La tarea toca el backend"
COND_FRONT = "La tarea toca el frontend"


def split_pipeline(
    db: Session, project: Project, agents: list[Agent], always: bool = False, **options
) -> dict:
    """Requisitos → (Backend | Frontend) → QA; QA rejects to Backend or to Frontend."""
    names = ("Requisitos", "Backend", "Frontend", "QA")
    review = options.pop("review", ())
    # Phase 21: without conditions the branches are always taken, as if marked «always».
    back, front = (COND_BACK, COND_FRONT) if options.pop("conditions", True) else ("", "")
    payload = PipelineWrite(
        name="Split",
        stages=[
            StageWrite(
                name=name,
                agent_id=agent.id,
                reject_to=1 if name == "QA" else None,
                reject_also=[2] if name == "QA" else [],
                requires_review=name in review,
            )
            for name, agent in zip(names, agents, strict=True)
        ],
        links=[
            LinkWrite(source=0, target=1, name="Backend", condition=back, always=always),
            LinkWrite(source=0, target=2, name="Frontend", condition=front, always=always),
            LinkWrite(source=1, target=3),
            LinkWrite(source=2, target=3),
        ],
        **options,
    )
    pipeline = pipelines.save(db, project, payload)
    db.flush()
    db.refresh(pipeline)
    stages = {s.name: s.id for s in pipeline.stages}
    links = {x.name: x.id for x in pipeline.links if x.from_stage_id == stages["Requisitos"]}
    return {"stages": stages, "links": links}


def setup_split(db_factory, mode=WorkspaceMode.DIRECT, always=False, **options):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Bea", "Fran", "Quim")]
        project = make_project(db, "web", mode)
        ids = split_pipeline(db, project, agents, always=always, **options)
        db.commit()
        return ids, {a.name: a.id for a in agents}


def task_row(db_factory, number: int = 1, key: str = "") -> Task:
    with db_factory() as db:
        task = db.scalar(select(Task).where(Task.number == number, Task.lane_key == key))
        assert task is not None, (number, key)
        db.expunge(task)
        return task


def launched(launcher: FakeLauncher, code: str) -> str:
    return next(run for c, run in reversed(launcher.launched) if c == code)


def finish_stage(db_factory, scheduler, launcher, code: str, summary: str = "hecho", **kw) -> None:
    end_run(db_factory, scheduler, launched(launcher, code), "completed", summary, **kw)


def new_task(db_factory, **kwargs) -> None:
    with db_factory() as db:
        project = db.scalar(select(Project))
        task_ops.create_task(db, project, "Filtro de pedidos", **kwargs)
        db.commit()


def test_branches_marked_always_are_taken_without_asking_and_go_one_after_the_other(
    db_factory, scheduler, launcher
):
    ids, _ = setup_split(db_factory, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos")

    mother = task_row(db_factory)
    assert (mother.status, mother.stage_id, mother.agent_id) == (
        "forked",
        ids["stages"]["Requisitos"],
        None,
    )
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert (decision.decided_by, sorted(decision.chosen)) == (
            "always",
            sorted(ids["links"].values()),
        )
        assert {
            t.lane_key for t in db.scalars(select(Task).where(Task.lane_of_id.is_not(None)))
        } == {
            "backend",
            "frontend",
        }
    # a direct folder runs one task at a time: the second lane waits for the first
    assert task_row(db_factory, key="backend").status == "running"
    assert task_row(db_factory, key="frontend").status == "backlog"
    assert [c for c, _ in launcher.launched] == ["T-1", "T-1·backend"]

    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api lista")
    assert task_row(db_factory, key="backend").status == "done"
    assert task_row(db_factory, key="frontend").status == "running"
    assert task_row(db_factory).status == "forked"  # still waiting for the frontend

    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "ui lista")
    mother = task_row(db_factory)
    assert (mother.status, mother.stage_id) == ("running", ids["stages"]["QA"])
    assert launcher.launched[-1][0] == "T-1"  # QA runs on the task that forked
    finish_stage(db_factory, scheduler, launcher, "T-1", "todo bien")
    assert task_row(db_factory).status == "done"

    with db_factory() as db:  # the join recorded what each lane said
        joined = db.scalar(select(TaskEvent).where(TaskEvent.kind == TaskEventKind.JOINED))
        assert "backend: api lista" in joined.detail and "frontend: ui lista" in joined.detail


def test_branches_without_a_condition_are_taken_without_asking(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory, conditions=False)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos")
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert (decision.decided_by, sorted(decision.chosen)) == (
            "always",
            sorted(ids["links"].values()),
        )
    assert task_row(db_factory, key="backend").status == "running"


def test_only_the_branches_with_a_condition_go_to_the_decider(db_factory):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Bea", "Fran", "Quim")]
        project = make_project(db, "web", WorkspaceMode.DIRECT)
        ids = split_pipeline(db, project, agents)
        front = db.get(StageLink, ids["links"]["Frontend"])
        front.condition = ""
        fork = db.get(Stage, ids["stages"]["Requisitos"])
        undecided, always = lanes.open_links(db, fork)
        assert [x.id for x in undecided] == [ids["links"]["Backend"]]
        assert always == [ids["links"]["Frontend"]]


def test_without_a_decider_the_person_chooses_and_the_join_waits_only_for_those_taken(
    db_factory, scheduler, launcher
):
    ids, _ = setup_split(db_factory)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")

    waiting = task_row(db_factory)
    assert (waiting.status, waiting.waiting_reason) == ("waiting_human", "choose_branch")
    assert waiting.stage_id == ids["stages"]["Requisitos"]
    assert len(launcher.launched) == 1

    with db_factory() as db:
        task = db.get(Task, waiting.id)
        with pytest.raises(ApiError):
            lanes.decide(db, task, ["nope"])
        lanes.decide(db, task, [ids["links"]["Frontend"]])
        db.commit()
    scheduler.step()
    mother = task_row(db_factory)
    assert mother.status == "forked"
    assert mother.waiting_reason is None  # what it waited for is over
    with db_factory() as db:  # and so is the request that said so
        pending = db.scalars(
            select(InboxItem).where(InboxItem.task_id == mother.id, InboxItem.status == "pending")
        )
        assert list(pending) == []
    assert task_row(db_factory, key="frontend").status == "running"
    with db_factory() as db:
        assert db.scalar(select(Task).where(Task.lane_key == "backend")) is None
        decision = db.scalar(select(BranchDecision))
        assert decision.decided_by == "user"

    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]


def test_branches_fixed_when_the_task_is_created_are_not_asked(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory)
    new_task(
        db_factory,
        preset_lanes={ids["stages"]["Requisitos"]: [ids["links"]["Backend"]]},
    )
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    assert task_row(db_factory).status == "forked"
    assert task_row(db_factory, key="backend").status == "running"
    with db_factory() as db:
        assert db.scalar(select(BranchDecision)).decided_by == "preset"
        with pytest.raises(ApiError):  # a branch that is not part of that fork
            task_ops.create_task(
                db,
                db.scalar(select(Project)),
                "otra",
                preset_lanes={ids["stages"]["Backend"]: [ids["links"]["Backend"]]},
            )


def test_in_a_worktree_project_the_lanes_run_in_parallel(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    assert {c for c, _ in launcher.launched[1:]} == {"T-1·backend", "T-1·frontend"}
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")
    assert task_row(db_factory).status == "forked"
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    assert task_row(db_factory).status == "running"  # QA


def test_qa_sends_the_task_back_only_to_the_branch_that_failed(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "ui")
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]

    # QA rejects the frontend (the stage's second reject target)
    run_id = launched(launcher, "T-1")
    with db_factory() as db:
        db.get(Run, run_id).reject_to_stage_id = ids["stages"]["Frontend"]
        db.commit()
    end_run(db_factory, scheduler, run_id, "completed", "el botón no se ve", verdict="rejected")

    mother = task_row(db_factory)
    assert (mother.status, mother.rejections) == ("forked", 1)
    assert task_row(db_factory, key="backend").status == "done"  # untouched
    front = task_row(db_factory, key="frontend")
    assert (front.status, front.stage_id) == ("running", ids["stages"]["Frontend"])
    with db_factory() as db:
        context = task_ops.task_context(db, db.get(Task, front.id))
    assert context.rejection == "el botón no se ve"

    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "botón arreglado")
    back = task_row(db_factory)
    assert (back.status, back.stage_id) == ("running", ids["stages"]["QA"])
    finish_stage(db_factory, scheduler, launcher, "T-1", "ahora sí")
    assert task_row(db_factory).status == "done"


def test_a_rejection_without_a_chosen_target_goes_to_the_default_one(
    db_factory, scheduler, launcher
):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    for code in ("T-1", "T-1·backend", "T-1·frontend"):
        finish_stage(db_factory, scheduler, launcher, code)
    finish_stage(db_factory, scheduler, launcher, "T-1", "mal", verdict="rejected")
    assert task_row(db_factory, key="backend").stage_id == ids["stages"]["Backend"]
    assert task_row(db_factory, key="backend").status == "running"
    assert task_row(db_factory, key="frontend").status == "done"


def test_too_many_rejections_across_lanes_wait_for_the_user(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True, max_rejections=1)
    new_task(db_factory)
    scheduler.step()
    for code in ("T-1", "T-1·backend", "T-1·frontend"):
        finish_stage(db_factory, scheduler, launcher, code)
    finish_stage(db_factory, scheduler, launcher, "T-1", "1", verdict="rejected")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    finish_stage(db_factory, scheduler, launcher, "T-1", "2", verdict="rejected")
    mother = task_row(db_factory)
    assert (mother.status, mother.waiting_reason) == ("waiting_human", "max_rejections")

    with db_factory() as db:  # retrying restarts the loop
        task_ops.retry(db, db.get(Task, mother.id))
        db.commit()
    assert task_row(db_factory).rejections == 0
    assert task_row(db_factory, key="backend").status in ("queued", "running")


def test_cancelling_a_lane_makes_the_join_stop_waiting_for_it(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    with db_factory() as db:
        frontend = db.scalar(select(Task).where(Task.lane_key == "frontend"))
        cancelled = lanes.cancel_lane(db, frontend)
        db.commit()
        assert [t.lane_key for t in cancelled] == ["frontend"]
    assert task_row(db_factory, key="frontend").status == "cancelled"
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]  # joined with what was left


def test_cancelling_every_lane_leaves_the_task_waiting(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    with db_factory() as db:
        for lane in db.scalars(select(Task).where(Task.lane_of_id.is_not(None))).all():
            lanes.cancel_lane(db, lane)
        db.commit()
    mother = task_row(db_factory)
    assert (mother.status, mother.waiting_reason) == ("waiting_human", "lanes_cancelled")


def test_cancelling_the_task_cancels_its_lanes(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        cancelled = lanes.cancel_tree(db, mother)
        db.commit()
        assert {t.code for t in cancelled} == {"T-1", "T-1·backend", "T-1·frontend"}
    for key in ("", "backend", "frontend"):
        assert task_row(db_factory, key=key).status == "cancelled"


def test_a_branch_can_be_added_to_a_fork_in_progress(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE)
    new_task(
        db_factory,
        preset_lanes={ids["stages"]["Requisitos"]: [ids["links"]["Backend"]]},
    )
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        added = lanes.add_lane(db, mother, ids["links"]["Frontend"])
        db.commit()
        assert added.lane_key == "frontend"
        with pytest.raises(ApiError):  # already running
            lanes.add_lane(db, mother, ids["links"]["Frontend"])
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    assert task_row(db_factory).status == "forked"  # the added branch is awaited too
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend")
    assert task_row(db_factory).stage_id == ids["stages"]["QA"]


def test_a_forked_task_shows_its_most_pressing_lane(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        assert lanes.view_status(db, mother) == ("running", "forked")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        assert lanes.view_status(db, mother) == ("running", "forked")
        front = db.scalar(select(Task).where(Task.lane_key == "frontend"))
        task_ops.wait_for_human(db, front, WaitingReason.RUN_FAILED, "boom")
        assert lanes.view_status(db, mother) == ("waiting_human", "forked")


def test_a_lane_with_a_review_gate_waits_in_review_and_the_mother_shows_it(
    db_factory, scheduler, launcher
):
    setup_split(db_factory, always=True, review=("Backend",))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api")
    lane = task_row(db_factory, key="backend")
    assert lane.status == TaskStatus.REVIEW
    with db_factory() as db:
        assert lanes.view_status(db, db.get(Task, task_row(db_factory).id))[0] == "review"
        task_ops.review(db, db.get(Task, lane.id), approve=True)
        db.commit()
    assert task_row(db_factory, key="backend").status == "done"
    scheduler.step()
    assert task_row(db_factory, key="frontend").status == "running"


def test_a_link_a_lane_is_using_cannot_be_removed(db_factory, scheduler, launcher):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")  # both lanes are running
    with db_factory() as db:
        project = db.scalar(select(Project))
        pipeline = task_ops.pipeline_of(db, project.id)
        stages = [StageWrite(id=s.id, name=s.name, agent_id=s.agent_id) for s in pipeline.stages]
        # Requisitos → Backend → Frontend → QA: the Requisitos → Frontend link disappears
        chain = [
            LinkWrite(source=0, target=1),
            LinkWrite(source=1, target=2),
            LinkWrite(source=2, target=3),
        ]
        with pytest.raises(ApiError) as caught:
            pipelines.save(db, project, PipelineWrite(stages=stages, links=chain))
        assert caught.value.code == "link_in_use"
        db.rollback()


# ------------------------------------------------------------------- what the agents are told
def test_a_lane_knows_its_branch_why_it_was_taken_and_what_the_others_do(
    db_factory, scheduler, launcher
):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos claros")
    with db_factory() as db:  # the person chooses, with their reasons
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        fork = db.get(Stage, mother.stage_id)
        lanes.take(
            db,
            mother,
            fork,
            list(ids["links"].values()),
            DecisionBy.MODEL,
            {ids["links"]["Backend"]: "toca la API"},
        )
        db.commit()
    scheduler.step()
    with db_factory() as db:
        lane = db.scalar(select(Task).where(Task.lane_key == "backend"))
        context = task_ops.task_context(db, lane)
        assert context.lane == "Backend" and context.lane_reason == "toca la API"
        assert context.siblings == ("frontend · Frontend · Fran (en ejecución)",)
        assert any("Requisitos · Ana terminó: requisitos claros" in h for h in context.history)
        text = ctx_module.task_section(context)
        assert "## Rama: Backend" in text and "toca la API" in text and "frontend" in text
        rendered = ctx_module.build_instructions(
            None, db.get(Project, lane.project_id), "D:/w", task=context
        )
        assert "## Rama: Backend" in rendered
        assert ctx_module.substitute("rama: $RAMA", {"$RAMA": context.lane}) == "rama: Backend"


def test_after_the_join_the_task_sees_what_each_branch_did_and_where_it_can_send_it_back(
    db_factory, scheduler, launcher
):
    setup_split(db_factory, mode=WorkspaceMode.WORKTREE, always=True)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api lista")
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "ui lista")
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        context = task_ops.task_context(db, mother)
    assert context.stage_name == "QA" and context.lane is None
    assert "backend: api lista" in (context.joined or "")
    assert "frontend: ui lista" in (context.joined or "")
    lines = "\n".join(context.history)
    assert "Backend · Bea terminó: api lista" in lines and "Frontend · Fran terminó" in lines
    assert context.can_reject and context.reject_targets == ("Backend", "Frontend")
    rendered = ctx_module.build_instructions(None, None, "D:/w", task=context)
    assert "## Ramas unidas" in rendered and "reject_to" in rendered and "«Frontend»" in rendered


def test_a_rejection_names_the_stage_when_there_are_several(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory)
    with db_factory() as db:
        qa = db.get(Stage, ids["stages"]["QA"])
        pick = RunManager._reject_target
        assert pick(db, qa, "") == (None, pick(db, qa, "")[1])
        assert "reject_to" in pick(db, qa, "")[1]  # asks which one
        assert pick(db, qa, "backend") == (None, None)  # the default
        assert pick(db, qa, "FRONTEND") == (ids["stages"]["Frontend"], None)
        target, problem = pick(db, qa, "Despliegue")
        assert target is None and "«Backend», «Frontend»" in problem
        backend = db.get(Stage, ids["stages"]["Backend"])
        assert pick(db, backend, "") == (None, None)  # nothing to choose


def test_branches_that_never_meet_finish_the_task_when_the_last_one_ends(
    db_factory, scheduler, launcher
):
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Bea", "Fran")]
        project = make_project(db, "web", WorkspaceMode.WORKTREE)
        payload = PipelineWrite(
            stages=[
                StageWrite(name=n, agent_id=a.id)
                for n, a in zip(("Req", "Back", "Front"), agents, strict=True)
            ],
            links=[
                LinkWrite(source=0, target=1, name="Backend", always=True),
                LinkWrite(source=0, target=2, name="Frontend", always=True),
            ],
        )
        pipelines.save(db, project, payload)
        task_ops.create_task(db, project, "Dos entregas")
        db.commit()
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    finish_stage(db_factory, scheduler, launcher, "T-1·backend", "api")
    assert task_row(db_factory).status == "forked"
    finish_stage(db_factory, scheduler, launcher, "T-1·frontend", "ui")

    mother = task_row(db_factory)
    assert (mother.status, mother.finished_at is not None) == ("done", True)
    with db_factory() as db:
        delivery = db.scalar(select(InboxItem).where(InboxItem.task_id == mother.id))
        assert delivery is not None and delivery.kind == InboxKind.DELIVERY
