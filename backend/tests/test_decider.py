"""The branch decider (phase 13): parsing the CLIs' answers, picking the account, and the whole
flow through the scheduler with a fake runner instead of the real CLIs."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable

from sqlalchemy import select
from test_lanes import (  # noqa: F401 - fixtures
    COND_BACK,
    db_factory,
    finish_stage,
    launcher,
    new_task,
    scheduler,
    setup_split,
    task_row,
)
from test_scheduler import make_project

from agentic_os.models import (
    BranchDecision,
    CliAccount,
    InboxItem,
    InboxKind,
    Pipeline,
    Run,
    RunKind,
    RunStatus,
    SessionState,
    Stage,
    StageLink,
    Task,
    TaskStatus,
    WorkspaceMode,
)
from agentic_os.models.agent import Cli
from agentic_os.services import decider
from agentic_os.services import tasks as task_ops
from agentic_os.services.decider import BranchView, DecisionRequest, DecisionService
from agentic_os.services.usage.stats import task_usage

OVERRIDES = {"claude": ["fake-claude"], "agy": ["fake-agy"]}


def request(cli: Cli = Cli.CLAUDE, always: tuple[str, ...] = ()) -> DecisionRequest:
    return DecisionRequest(
        task_id="t",
        fork_stage_id="f",
        title="Filtro de pedidos",
        description="API y pantalla",
        history=("- Requisitos · Ana terminó: hecho",),
        branches=(BranchView("b1", "Backend", COND_BACK), BranchView("f1", "Frontend", "UI")),
        always=always,
        cli=cli,
        account_id="a",
        model="haiku",
        prefix=("fake",),
        env={},
    )


def claude_output(branches: list[dict], **extra) -> str:
    return json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": "",
            "structured_output": {"branches": branches},
            "total_cost_usd": 0.0004,
            "usage": {
                "input_tokens": 2,
                "output_tokens": 190,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            },
            "modelUsage": {"claude-haiku-5-5": {}},
            **extra,
        }
    )


def agy_output(branches: list[dict], status: str = "SUCCESS") -> str:
    return json.dumps(
        {
            "result": {
                "status": status,
                "response": "Claro:\n" + json.dumps({"branches": branches}),
                "usage": {"input_tokens": 11800, "output_tokens": 110, "thinking_tokens": 7},
            }
        }
    )


def take(*ids: str, reason: str = "porque sí") -> list[dict]:
    return [{"id": i, "take": i in ids, "reason": reason} for i in ("b1", "f1")]


# ------------------------------------------------------------------------------ parsing
def test_claude_answers_come_from_the_structured_output_with_usage_and_cost():
    result = decider.parse_claude(claude_output(take("f1")), request())
    assert result.error is None
    assert result.chosen == ["f1"] and result.taken == {"b1": False, "f1": True}
    assert result.reasons["f1"] == "porque sí"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (2, 190)
    assert (result.usage.cache_read_tokens, result.usage.cache_creation_tokens) == (10, 5)
    assert result.usage.cost_usd == 0.0004 and result.model == "claude-haiku-5-5"


def test_claude_falls_back_to_json_in_the_text_and_reports_errors():
    text = json.dumps(
        {"is_error": False, "result": "Aquí: " + json.dumps({"branches": take("b1")})}
    )
    assert decider.parse_claude(text, request()).chosen == ["b1"]
    failed = json.dumps({"is_error": True, "result": "Credit balance is too low"})
    assert "Credit" in (decider.parse_claude(failed, request()).error or "")
    assert decider.parse_claude("not json", request()).error
    assert decider.parse_claude(claude_output([]), request()).chosen == []  # nothing, no error yet
    bad = json.dumps({"is_error": False, "result": "no sé", "structured_output": None})
    assert decider.parse_claude(bad, request()).error


def test_unknown_branch_ids_are_ignored_and_missing_ones_are_not_taken():
    answer = [{"id": "zzz", "take": True, "reason": ""}, {"id": "f1", "take": True, "reason": "ui"}]
    result = decider.parse_claude(claude_output(answer), request())
    assert result.taken == {"b1": False, "f1": True}


def test_agy_answers_come_from_the_text_with_tokens_and_no_cost():
    result = decider.parse_agy(agy_output(take("b1", "f1")), request(Cli.AGY))
    assert result.chosen == ["b1", "f1"] and result.usage.cost_usd is None
    assert (result.usage.input_tokens, result.usage.thinking_tokens) == (11800, 7)
    assert decider.parse_agy(agy_output(take("b1"), "ERROR"), request(Cli.AGY)).error
    assert decider.parse_agy("{}", request(Cli.AGY)).error  # no response text


# ------------------------------------------------------------------------------- calling
def fake_runner(output: str, calls: list | None = None, code: int = 0) -> Callable:
    def runner(argv, timeout, cwd=None, env=None, input=None):
        if calls is not None:
            calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        return subprocess.CompletedProcess(argv, code, stdout=output, stderr="")

    return runner


def test_the_call_to_claude_has_no_tools_no_session_and_a_budget():
    calls: list = []
    result = decider.call(request(), fake_runner(claude_output(take("b1")), calls))
    argv = calls[0]["argv"]
    assert result.chosen == ["b1"] and result.error is None
    assert argv[:2] == ["fake", "-p"] and "--no-session-persistence" in argv
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "0.05"
    assert argv[argv.index("--model") + 1] == "haiku"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["required"] == ["branches"]
    assert "Backend" in argv[2] and "Requisitos" in argv[2]  # the task and the work done
    assert calls[0]["cwd"] and "agentic-decider" in calls[0]["cwd"]  # an empty temp folder


def test_the_call_to_agy_is_headless_json():
    calls: list = []
    decider.call(request(Cli.AGY), fake_runner(agy_output(take("f1")), calls))
    argv = calls[0]["argv"]
    assert argv[:2] == ["fake", "-p"] and argv[argv.index("--output-format") + 1] == "json"
    assert "--tools" not in argv


def test_choosing_nothing_is_an_error_unless_a_branch_is_always_taken():
    nothing = fake_runner(claude_output(take()))
    assert decider.call(request(), nothing).error == "no eligió ninguna rama"
    assert decider.call(request(always=("x",)), nothing).error is None


def test_a_cli_that_fails_or_times_out_is_an_error_not_an_exception():
    assert decider.call(request(), fake_runner("", code=1)).error

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("claude", 90)

    assert "90" in (decider.call(request(), slow).error or "")

    def missing(*args, **kwargs):
        raise FileNotFoundError("claude")

    assert decider.call(request(), missing).error


# ---------------------------------------------------------------------------- the config
def test_the_decider_uses_the_first_cli_with_a_usable_account(db_factory, monkeypatch):
    with db_factory() as db:
        pipeline = Pipeline()
        config = decider.resolve_config(db, pipeline, OVERRIDES)
        assert (config.cli, config.model) == (Cli.CLAUDE, "haiku")

        claude = db.scalar(select(CliAccount).where(CliAccount.cli == "claude"))
        claude.session_state = SessionState.DOWN  # logged out: the next CLI is used
        config = decider.resolve_config(db, pipeline, OVERRIDES)
        assert (config.cli, config.model) == (Cli.AGY, "gemini-3.8-flash-low")

        pipeline.decider_cli = "claude"  # asked for explicitly: no silent change
        assert "no está disponible" in decider.resolve_config(db, pipeline, OVERRIDES)
        agy = db.scalar(select(CliAccount).where(CliAccount.cli == "agy"))
        agy.session_state = SessionState.DOWN
        pipeline.decider_cli = None
        assert isinstance(decider.resolve_config(db, pipeline, OVERRIDES), str)

        agy.session_state = SessionState.OK
        pipeline.decider_model = "gemini-pro"
        assert decider.resolve_config(db, pipeline, OVERRIDES).model == "gemini-pro"
        monkeypatch.setattr("agentic_os.services.runs.launcher.shutil.which", lambda name: None)
        missing = decider.resolve_config(db, Pipeline(decider_cli="agy"), {})
        assert "no está instalado" in missing


# -------------------------------------------------------------------- through the scheduler
def wire(scheduler, runner, **kwargs) -> DecisionService:
    service = DecisionService(OVERRIDES, runner, **kwargs)
    service.on_result = scheduler.decision_ready
    scheduler.deciders = service
    return service


def until(scheduler, db_factory, done: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scheduler.step()
        if done():
            return
        time.sleep(0.05)
    raise AssertionError("the decision did not arrive")


def answering(ids: dict, *names: str, calls: list | None = None) -> Callable:
    """A runner that takes the links with these names (the prompt lists `id · name`)."""

    def runner(argv, timeout, cwd=None, env=None, input=None):
        if calls is not None:
            calls.append(argv)
        prompt = argv[2]
        rows = [
            {"id": link_id, "take": name in names, "reason": f"motivo de {name}"}
            for name, link_id in ids["links"].items()
            if f"{link_id} · {name}" in prompt
        ]
        return subprocess.CompletedProcess(argv, 0, stdout=claude_output(rows), stderr="")

    return runner


def reach_the_fork(db_factory, scheduler, launcher, runner, **options):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE, **options)
    service = wire(scheduler, runner(ids) if callable(runner) else runner)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1", "requisitos")
    return ids, service


def test_the_model_picks_the_branches_and_its_call_is_recorded_as_usage(
    db_factory, scheduler, launcher
):
    ids, service = reach_the_fork(
        db_factory,
        scheduler,
        launcher,
        lambda ids: answering(ids, "Frontend"),
    )
    until(scheduler, db_factory, lambda: task_row(db_factory).status == "forked")
    assert {c for c, _ in launcher.launched[1:]} == {"T-1·frontend"}  # only that branch
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert (decision.decided_by, decision.chosen, decision.proposed) == (
            "model",
            [ids["links"]["Frontend"]],
            False,
        )
        assert decision.reasons[ids["links"]["Frontend"]] == "motivo de Frontend"
        run = db.get(Run, decision.run_id)
        assert (run.kind, run.status, run.agent_id, run.agent_name) == (
            RunKind.DECISION,
            RunStatus.COMPLETED,
            None,
            "Decisor",
        )
        assert (run.cli, run.model, run.cost_usd, run.usage_source) == (
            "claude",
            "claude-haiku-5-5",
            0.0004,
            "decider",
        )
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        assert run.task_id == mother.id and run.account_id
        totals = task_usage(db, [mother.id])[mother.id]
        assert totals.cost_usd >= 0.0004  # the decision counts in the task's consumption
    service.stop()


def test_branches_marked_always_join_the_models_choice(db_factory, scheduler, launcher):
    ids, _ = setup_split(db_factory, mode=WorkspaceMode.WORKTREE)
    with db_factory() as db:
        db.get(StageLink, ids["links"]["Backend"]).always = True
        db.commit()
    seen: list = []
    service = wire(scheduler, answering(ids, "Frontend", calls=seen))
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    until(scheduler, db_factory, lambda: task_row(db_factory).status == "forked")
    assert {c for c, _ in launcher.launched[1:]} == {"T-1·backend", "T-1·frontend"}
    # the model was only asked about the branch that needed a decision
    assert ids["links"]["Backend"] not in seen[0][2]
    with db_factory() as db:
        assert db.scalar(select(BranchDecision)).reasons[ids["links"]["Backend"]] == (
            "Siempre se toma"
        )
    service.stop()


def test_when_the_model_fails_twice_the_person_chooses(db_factory, scheduler, launcher):
    calls: list = []

    def broken(ids):
        def runner(argv, timeout, cwd=None, env=None, input=None):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="no soy json", stderr="")

        return runner

    _, service = reach_the_fork(db_factory, scheduler, launcher, broken)
    until(
        scheduler,
        db_factory,
        lambda: task_row(db_factory).status == TaskStatus.WAITING_HUMAN,
    )
    mother = task_row(db_factory)
    assert mother.waiting_reason == "choose_branch" and "JSON" in (mother.waiting_detail or "")
    assert len(calls) == 2  # one retry
    with db_factory() as db:
        failed = db.scalar(select(Run).where(Run.kind == RunKind.DECISION))
        assert failed.status == RunStatus.FAILED and failed.error
        item = db.scalar(select(InboxItem).where(InboxItem.task_id == mother.id))
        assert item is not None and "Hay que elegir la rama" in item.detail
    service.stop()


def test_a_decider_without_a_usable_account_leaves_the_choice_to_the_person(
    db_factory, scheduler, launcher
):
    runs: list = []
    _, service = reach_the_fork(
        db_factory, scheduler, launcher, lambda ids: answering(ids, "Backend", calls=runs)
    )
    until(scheduler, db_factory, lambda: task_row(db_factory).status == "forked")
    # now the pipeline's decider is agy, which is logged out (the agents still use claude)
    with db_factory() as db:
        db.scalar(select(Pipeline)).decider_cli = "agy"
        db.scalar(
            select(CliAccount).where(CliAccount.cli == "agy")
        ).session_state = SessionState.DOWN
        db.commit()
    new_task(db_factory)
    scheduler.step()
    # the first task's lane is queued/running; the new task starts at Requisitos
    finish_stage(db_factory, scheduler, launcher, "T-2")
    mother = task_row(db_factory, number=2)
    assert (mother.status, mother.waiting_reason) == ("waiting_human", "choose_branch")
    assert "no está disponible" in (mother.waiting_detail or "")
    service.stop()


def test_without_a_decider_service_the_person_chooses(db_factory, scheduler, launcher):
    setup_split(db_factory)
    new_task(db_factory)
    scheduler.step()
    finish_stage(db_factory, scheduler, launcher, "T-1")
    assert task_row(db_factory).waiting_reason == "choose_branch"


def test_a_cancelled_task_ignores_a_late_decision(db_factory, scheduler, launcher):
    release = []

    def slow(ids):
        base = answering(ids, "Backend")

        def runner(argv, timeout, cwd=None, env=None, input=None):
            while not release:
                time.sleep(0.02)
            return base(argv, timeout, cwd, env, input)

        return runner

    _, service = reach_the_fork(db_factory, scheduler, launcher, slow)
    from agentic_os.services import lanes

    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        assert mother.status == TaskStatus.DECIDING
        lanes.cancel_tree(db, mother)
        db.commit()
    release.append(1)
    time.sleep(0.5)
    scheduler.step()
    assert task_row(db_factory).status == "cancelled"
    with db_factory() as db:
        assert db.scalar(select(BranchDecision)) is None
        assert db.scalar(select(Task).where(Task.lane_of_id.is_not(None))) is None
    service.stop()


def test_a_fork_that_asks_for_confirmation_waits_in_review(db_factory, scheduler, launcher):
    ids, service = reach_the_fork(
        db_factory, scheduler, launcher, lambda ids: answering(ids, "Backend")
    )
    with db_factory() as db:  # (set after the fact: the task has not decided yet)
        db.get(Stage, ids["stages"]["Requisitos"]).confirm_decision = True
        db.commit()
    until(scheduler, db_factory, lambda: task_row(db_factory).status == TaskStatus.REVIEW)
    assert len(launcher.launched) == 1  # nothing started yet
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        proposal = db.scalar(select(BranchDecision))
        assert proposal.proposed and proposal.chosen == [ids["links"]["Backend"]]
        item = db.scalar(select(InboxItem).where(InboxItem.kind == InboxKind.REVIEW))
        assert item is not None and "Backend" in item.detail

        task_ops.review(db, mother, approve=True)  # confirmed
        db.commit()
    scheduler.step()
    assert task_row(db_factory).status == "forked"
    assert task_row(db_factory, key="backend").status == "running"
    with db_factory() as db:
        decision = db.scalar(select(BranchDecision))
        assert decision.proposed is False and decision.decided_by == "model"
    service.stop()


def test_a_proposal_can_be_changed_or_sent_back_to_be_chosen_by_hand(
    db_factory, scheduler, launcher
):
    from agentic_os.services import lanes

    ids, service = reach_the_fork(
        db_factory, scheduler, launcher, lambda ids: answering(ids, "Backend")
    )
    with db_factory() as db:
        db.get(Stage, ids["stages"]["Requisitos"]).confirm_decision = True
        db.commit()
    until(scheduler, db_factory, lambda: task_row(db_factory).status == TaskStatus.REVIEW)
    with db_factory() as db:
        mother = db.scalar(select(Task).where(Task.lane_key == ""))
        task_ops.review(db, mother, approve=False, reason="toca también la UI")
        db.commit()
    mother = task_row(db_factory)
    assert (mother.status, mother.waiting_reason) == ("waiting_human", "choose_branch")
    with db_factory() as db:
        db.get(Task, mother.id)
        lanes.decide(db, db.get(Task, mother.id), list(ids["links"].values()))
        db.commit()
    scheduler.step()
    assert {t.lane_key for t in _lanes(db_factory)} == {"backend", "frontend"}
    service.stop()


def _lanes(db_factory) -> list[Task]:
    with db_factory() as db:
        return list(db.scalars(select(Task).where(Task.lane_of_id.is_not(None))))


def test_preview_asks_without_a_task_and_records_its_usage(db_factory):
    rows = [
        {"id": "0", "take": True, "reason": "api"},
        {"id": "1", "take": False, "reason": "sin UI"},
    ]
    with db_factory() as db:
        project = make_project(db, "web")
        result, asked = decider.preview(
            db,
            project,
            Pipeline(),
            [BranchView("0", "Backend", COND_BACK), BranchView("1", "Frontend", "UI")],
            "Añadir endpoint",
            "",
            OVERRIDES,
            runner=fake_runner(claude_output(rows)),
        )
        assert asked is not None and asked.cli == Cli.CLAUDE
        assert result.chosen == ["0"] and result.reasons["1"] == "sin UI"
        run = db.scalar(select(Run).where(Run.kind == RunKind.DECISION))
        assert run.task_id is None and run.project_id == project.id and run.cost_usd == 0.0004
