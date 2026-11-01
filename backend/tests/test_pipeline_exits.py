"""«Terminar aquí» exits in the engine (phase 24, block 3; CA2, ADR 0030): the decider (or the
person) says whether a task ends at a stage, ending is exclusive with the branches, the final
review is not skipped, and a task that ended can go on with the pipeline."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

import pytest
from sqlalchemy import select
from test_decider import OVERRIDES, claude_output, fake_runner, until
from test_lanes import (  # noqa: F401 - fixtures
    db_factory,
    finish_stage,
    launcher,
    new_task,
    scheduler,
    task_row,
)
from test_scheduler import make_agent, make_project

from agentic_os.api.tasks import read_task
from agentic_os.errors import ApiError
from agentic_os.models import (
    BranchDecision,
    InboxItem,
    InboxKind,
    Pipeline,
    Run,
    Stage,
    Task,
    TaskEvent,
    TaskEventKind,
    TaskStatus,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.models.agent import Cli
from agentic_os.schemas.pipeline import LinkWrite, PipelineWrite, StageWrite
from agentic_os.services import decider, lanes, pipelines
from agentic_os.services import tasks as task_ops
from agentic_os.services.decider import BranchView, DecisionRequest, DecisionService

EXIT_REQ = "La tarea solo pide definir requisitos"
EXIT_DESIGN = "La tarea solo pide el diseño"
EXIT_QA = "La tarea no necesita despliegue"
COND_BACK = "La tarea toca el backend"
COND_FRONT = "La tarea toca el frontend"


def setup(
    db_factory,
    review: tuple[str, ...] = ("Despliegue",),
    confirm: bool = False,
    mode: WorkspaceMode = WorkspaceMode.DIRECT,
) -> dict:
    """Requisitos (exit) → Diseño (exit + fork) → (Backend | Frontend) → QA (exit) → Despliegue."""
    names = ("Requisitos", "Diseño", "Backend", "Frontend", "QA", "Despliegue")
    exits = {"Requisitos": EXIT_REQ, "Diseño": EXIT_DESIGN, "QA": EXIT_QA}
    with db_factory() as db:
        agents = [make_agent(db, n) for n in ("Ana", "Dani", "Bea", "Fran", "Quim", "Ivo")]
        project = make_project(db, "web", mode)
        payload = PipelineWrite(
            stages=[
                StageWrite(
                    name=name,
                    agent_id=agent.id,
                    requires_review=name in review,
                    exit_condition=exits.get(name),
                    confirm_decision=confirm and name in exits,
                    reject_to=2 if name == "QA" else None,
                    reject_also=[3] if name == "QA" else [],
                )
                for name, agent in zip(names, agents, strict=True)
            ],
            links=[
                LinkWrite(source=0, target=1),
                LinkWrite(source=1, target=2, name="Backend", condition=COND_BACK),
                LinkWrite(source=1, target=3, name="Frontend", condition=COND_FRONT),
                LinkWrite(source=2, target=4),
                LinkWrite(source=3, target=4),
                LinkWrite(source=4, target=5),
            ],
        )
        pipeline = pipelines.save(db, project, payload)
        db.commit()
        db.refresh(pipeline)
        stages = {s.name: s.id for s in pipeline.stages}
        links = {x.name: x.id for x in pipeline.links}
        return {"stages": stages, "links": links}


def events(db_factory, kind: TaskEventKind) -> list[str]:
    with db_factory() as db:
        return list(db.scalars(select(TaskEvent.detail).where(TaskEvent.kind == kind)))


def decide(db_factory, chosen: list[str]) -> None:
    with db_factory() as db:
        task = db.scalar(select(Task).where(Task.lane_key == ""))
        lanes.decide(db, task, chosen)
        db.commit()


def deciding_runner(answers: dict[str, tuple[bool, tuple[str, ...]]], ids: dict) -> Callable:
    """A fake decider: per stage name (in the prompt), whether the task ends and its branches."""

    def runner(argv, timeout, cwd=None, env=None, input=None):
        prompt = argv[2]
        stage = next(name for name in answers if f"«{name}»" in prompt)
        ends, taken = answers[stage]
        rows = [
            {"id": link_id, "take": name in taken, "reason": f"motivo de {name}"}
            for name, link_id in ids["links"].items()
            if f"{link_id} · {name}" in prompt
        ]
        out = json.loads(claude_output(rows))
        out["structured_output"]["exit"] = {"take": ends, "reason": f"{stage}: termina={ends}"}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(out), stderr="")

    return runner


def wire(scheduler, runner) -> DecisionService:
    service = DecisionService(OVERRIDES, runner)
    service.on_result = scheduler.decision_ready
    scheduler.deciders = service
    return service


# ------------------------------------------------------------------------------ by hand
def test_without_a_decider_the_person_ends_the_task_and_the_final_review_is_kept(
    db_factory, scheduler, launcher
):
    ids = setup(db_factory)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos escritos")

    waiting = task_row(db_factory)
    assert (waiting.status, waiting.waiting_reason) == ("waiting_human", "choose_branch")
    assert waiting.stage_id == ids["stages"]["Requisitos"]
    with db_factory() as db:
        shown = read_task(db, db.get(Task, waiting.id))
        assert shown.stage_exit_condition == EXIT_REQ

    decide(db_factory, [lanes.EXIT])
    # Requisitos has no review of its own but the pipeline ends with one: it is not skipped.
    in_review = task_row(db_factory)
    assert in_review.status == TaskStatus.REVIEW
    assert in_review.exit_stage_id == ids["stages"]["Requisitos"]
    with db_factory() as db:
        item = db.scalar(select(InboxItem).where(InboxItem.kind == InboxKind.REVIEW))
        assert "Revisión final" in item.detail and "Requisitos" in item.detail
        task_ops.review(db, db.get(Task, in_review.id), approve=True)
        db.commit()

    done = task_row(db_factory)
    assert done.status == TaskStatus.DONE and done.exit_stage_id == ids["stages"]["Requisitos"]
    assert events(db_factory, TaskEventKind.EXITED) == [f"Requisitos: {EXIT_REQ}"]
    assert len(launcher.launched) == 1  # nobody else worked on it
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert (decision.chosen, decision.decided_by) == ([lanes.EXIT], "user")
        shown = read_task(db, db.get(Task, done.id))
        assert (shown.exit_stage_id, shown.exit_stage_name) == (
            ids["stages"]["Requisitos"],
            "Requisitos",
        )


def test_without_a_final_review_ending_is_done_at_once_and_going_on_moves_to_the_next_stage(
    db_factory, scheduler, launcher
):
    ids = setup(db_factory, review=(), mode=WorkspaceMode.WORKTREE)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    decide(db_factory, [_first_link(db_factory)])
    scheduler.step()
    moved = task_row(db_factory)
    assert moved.status == TaskStatus.RUNNING and moved.stage_id == ids["stages"]["Diseño"]

    new_task(db_factory)  # T-2 ends at Requisitos: no review anywhere, done at once
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-2")
    with db_factory() as db:
        task = db.scalar(select(Task).where(Task.number == 2))
        lanes.decide(db, task, [lanes.EXIT])
        db.commit()
    assert task_row(db_factory, 2).status == TaskStatus.DONE


def _first_link(db_factory) -> str:
    with db_factory() as db:
        stage = db.scalar(select(Stage).where(Stage.name == "Requisitos"))
        return lanes.open_links(db, stage)[1][0]


def test_ending_goes_alone_and_only_where_there_is_an_exit(db_factory, scheduler, launcher):
    ids = setup(db_factory)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    decide(db_factory, [_first_link(db_factory)])
    finish_stage(db_factory, scheduler, launcher, "T-1", "diseño")
    with db_factory() as db:
        task = db.scalar(select(Task).where(Task.lane_key == ""))
        with pytest.raises(ApiError):
            lanes.decide(db, task, [lanes.EXIT, ids["links"]["Backend"]])
        stage = db.get(Stage, ids["stages"]["Backend"])
        with pytest.raises(ApiError):  # Backend has no exit
            lanes.take(db, task, stage, [lanes.EXIT], "user")


def test_a_stage_with_its_own_review_asks_after_it_and_ends_without_a_second_one(
    db_factory, scheduler, launcher
):
    setup(db_factory, review=("Requisitos", "Despliegue"))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    assert task_row(db_factory).status == TaskStatus.REVIEW  # its own review first
    with db_factory() as db:
        task_ops.review(db, db.get(Task, task_row(db_factory).id), approve=True)
        db.commit()
    scheduler.step()
    assert task_row(db_factory).waiting_reason == WaitingReason.CHOOSE_BRANCH
    decide(db_factory, [lanes.EXIT])
    assert task_row(db_factory).status == TaskStatus.DONE  # no second review


def test_a_rejected_final_review_undoes_the_exit_and_asks_again(db_factory, scheduler, launcher):
    setup(db_factory)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    decide(db_factory, [lanes.EXIT])
    with db_factory() as db:
        task = db.get(Task, task_row(db_factory).id)
        task_ops.review(db, task, approve=False, reason="faltan los casos de error")
        db.commit()
    scheduler.step()
    back = task_row(db_factory)
    assert back.exit_stage_id is None and back.status == TaskStatus.RUNNING
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos completos")
    assert task_row(db_factory).waiting_reason == WaitingReason.CHOOSE_BRANCH  # asked again


def test_a_task_that_ended_goes_on_with_the_pipeline(db_factory, scheduler, launcher):
    ids = setup(db_factory, review=())
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    decide(db_factory, [lanes.EXIT])
    assert task_row(db_factory).status == TaskStatus.DONE

    with db_factory() as db:
        task = db.get(Task, task_row(db_factory).id)
        lanes.continue_after_exit(db, task)
        db.commit()
        with pytest.raises(ApiError):  # it no longer ended at an exit
            lanes.continue_after_exit(db, task)
    scheduler.step()
    going = task_row(db_factory)
    assert going.status == TaskStatus.RUNNING and going.stage_id == ids["stages"]["Diseño"]
    assert going.exit_stage_id is None and going.finished_at is None
    with db_factory() as db:  # it is not delivered any more
        pending = db.scalars(
            select(InboxItem).where(
                InboxItem.task_id == going.id,
                InboxItem.kind == InboxKind.DELIVERY,
                InboxItem.status == "pending",
            )
        )
        assert list(pending) == []

    # At a stage that forks, going on asks the person for the branches.
    finish_stage(db_factory, scheduler, launcher, "T-1", "diseño")
    decide(db_factory, [lanes.EXIT])
    with db_factory() as db:
        lanes.continue_after_exit(db, db.get(Task, task_row(db_factory).id))
        db.commit()
    waiting = task_row(db_factory)
    assert (waiting.status, waiting.waiting_reason) == ("waiting_human", "choose_branch")
    decide(db_factory, [ids["links"]["Frontend"]])
    assert task_row(db_factory).status == "forked"


# ----------------------------------------------------------------------------- the decider
def test_the_decider_ends_the_task_at_a_stage_that_does_not_fork(db_factory, scheduler, launcher):
    ids = setup(db_factory, review=())
    service = wire(scheduler, deciding_runner({"Requisitos": (True, ())}, ids))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    until(scheduler, db_factory, lambda: task_row(db_factory).status == TaskStatus.DONE)
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert (decision.chosen, decision.decided_by) == ([lanes.EXIT], "model")
        assert decision.reasons[lanes.EXIT] == "Requisitos: termina=True"
        run = db.get(Run, decision.run_id)
        assert run.summary == lanes.EXIT_LABEL
        assert EXIT_REQ in run.prompt and "«Requisitos»" in run.prompt
    service.stop()


def test_the_decider_goes_on_and_picks_the_branches_or_ends_at_the_fork(
    db_factory, scheduler, launcher
):
    ids = setup(db_factory, review=(), mode=WorkspaceMode.WORKTREE)
    answers = {"Requisitos": (False, ()), "Diseño": (False, ("Frontend",))}
    service = wire(scheduler, deciding_runner(answers, ids))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    until(scheduler, db_factory, lambda: task_row(db_factory).stage_id == ids["stages"]["Diseño"])
    finish_stage(db_factory, scheduler, launcher, "T-1", "diseño")
    until(scheduler, db_factory, lambda: task_row(db_factory).status == "forked")
    assert {c for c, _ in launcher.launched[2:]} == {"T-1·frontend"}
    with db_factory() as db:
        fork = db.scalar(
            select(BranchDecision).where(BranchDecision.fork_stage_id == ids["stages"]["Diseño"])
        )
        assert fork.chosen == [ids["links"]["Frontend"]]
        assert fork.reasons[lanes.EXIT] == "Diseño: termina=False"  # why it did not end
    detail = events(db_factory, TaskEventKind.DECISION)[-1]
    assert "✗ Terminar aquí" in detail and "✓ Frontend" in detail
    service.stop()

    answers["Diseño"] = (True, ("Frontend",))  # a second task ends at the fork: no lanes
    service = wire(scheduler, deciding_runner(answers, ids))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-2")
    until(
        scheduler, db_factory, lambda: task_row(db_factory, 2).stage_id == ids["stages"]["Diseño"]
    )
    finish_stage(db_factory, scheduler, launcher, "T-2", "diseño")
    until(scheduler, db_factory, lambda: task_row(db_factory, 2).status == TaskStatus.DONE)
    with db_factory() as db:
        assert db.scalar(select(Task).where(Task.number == 2, Task.lane_key != "")) is None
    service.stop()


def test_an_exit_that_asks_for_confirmation_waits_in_review(db_factory, scheduler, launcher):
    ids = setup(db_factory, review=(), confirm=True)
    service = wire(scheduler, deciding_runner({"Requisitos": (True, ())}, ids))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    until(scheduler, db_factory, lambda: task_row(db_factory).status == TaskStatus.REVIEW)
    with db_factory() as db:
        proposal = db.scalar(select(BranchDecision))
        assert proposal.proposed and proposal.chosen == [lanes.EXIT]
        item = db.scalar(select(InboxItem).where(InboxItem.kind == InboxKind.REVIEW))
        assert "✓ Terminar aquí" in item.detail
        task_ops.review(db, db.get(Task, task_row(db_factory).id), approve=True)
        db.commit()
    assert task_row(db_factory).status == TaskStatus.DONE
    service.stop()


# ----------------------------------------------------------------------- prompt and answer
def exit_request(branches: tuple[BranchView, ...] = ()) -> DecisionRequest:
    return DecisionRequest(
        task_id="t",
        fork_stage_id="f",
        title="Requisitos del login",
        description="Solo los requisitos",
        history=(),
        branches=branches,
        always=(),
        cli=Cli.CLAUDE,
        account_id="a",
        model="haiku",
        prefix=("fake",),
        env={},
        exit=BranchView(lanes.EXIT, lanes.EXIT_LABEL, EXIT_REQ),
        stage_name="Validación",
    )


def test_the_exit_prompt_asks_first_whether_the_task_ends_and_then_the_branches():
    alone = decider.build_prompt(exit_request())
    assert "«Validación»" in alone and EXIT_REQ in alone and "`branches` vacío" in alone
    forked = decider.build_prompt(exit_request((BranchView("b1", "Backend", COND_BACK),)))
    assert "b1 · Backend" in forked and "Si termina, no tomes ninguna rama" in forked


def test_the_exit_answer_is_read_and_ending_needs_no_branch():
    calls: list = []
    out = json.loads(claude_output([]))
    out["structured_output"]["exit"] = {"take": True, "reason": "solo requisitos"}
    result = decider.call(exit_request(), fake_runner(json.dumps(out), calls))
    assert result.error is None and result.exit_taken and result.exit_reason == "solo requisitos"
    schema = json.loads(calls[0]["argv"][calls[0]["argv"].index("--json-schema") + 1])
    assert "exit" in schema["required"]

    out["structured_output"]["exit"] = {"take": False, "reason": "pide programar"}
    request = exit_request((BranchView("b1", "Backend", COND_BACK),))
    result = decider.call(request, fake_runner(json.dumps(out)))
    assert result.error == "no eligió ninguna rama"  # going on still needs a branch


def test_trying_an_exit_in_the_editor_asks_the_decider_whether_the_task_would_end(db_factory):
    out = json.loads(claude_output([]))
    out["structured_output"]["exit"] = {"take": True, "reason": "solo pide requisitos"}
    with db_factory() as db:
        project = make_project(db, "web")
        result, asked = decider.preview(
            db,
            project,
            Pipeline(),
            [],
            "Requisitos del login",
            "",
            OVERRIDES,
            runner=fake_runner(json.dumps(out)),
            exit_condition=EXIT_REQ,
            stage_name="Validación",
        )
        assert asked is not None and asked.exit is not None
        assert result.error is None and result.exit_taken
        assert result.exit_reason == "solo pide requisitos"


def test_the_preview_request_needs_a_fork_or_an_exit():
    from pydantic import ValidationError

    from agentic_os.schemas.pipeline import PreviewRequest

    with pytest.raises(ValidationError):
        PreviewRequest(title="x", branches=[{"name": "A", "condition": "a"}])
    assert PreviewRequest(title="x", exit_condition=EXIT_REQ).branches == []
