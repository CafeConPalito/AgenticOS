"""Who picks the branches of a fork (phase 13, ADR 0020): a CLI called once, without tools.

The call is `claude -p` (structured output) or `agy -p` (JSON in the text), with the cheapest
model and an account of the CLI. It never runs on the scheduler thread: `DecisionService`
snapshots what it needs, a worker makes the call, and the scheduler applies the result (it
records the call as a `Run` of kind «decision», so its usage counts everywhere).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import structlog
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    CliAccount,
    DecisionBy,
    Pipeline,
    Project,
    Run,
    RunKind,
    RunStatus,
    SessionState,
    Stage,
    StageLink,
    Task,
    UsageStatus,
    WaitingReason,
)
from agentic_os.models.agent import Cli
from agentic_os.services import accounts as account_ops
from agentic_os.services import inbox
from agentic_os.services import lanes as lane_ops
from agentic_os.services import tasks as task_ops
from agentic_os.services.proc import run as run_process
from agentic_os.services.runs.launcher import clean_env, resolve_executable, safe_prompt
from agentic_os.services.usage import limits as usage_limits

log = structlog.get_logger()

# The cheapest model of each CLI: the decision is a short classification.
CHEAP_MODEL = {Cli.CLAUDE: "haiku", Cli.AGY: "gemini-3.8-flash-low"}
CALL_TIMEOUT = 90.0
MAX_BUDGET_USD = "0.05"
ATTEMPTS = 2  # one retry
ALWAYS_REASON = "Siempre se toma"

SCHEMA = {
    "type": "object",
    "properties": {
        "branches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "take": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "take", "reason"],
            },
        }
    },
    "required": ["branches"],
}

# Phase 24 (ADR 0030, spike S1): at a stage with an exit the answer also says whether the task
# ends there; with `exit.take` the branches are ignored.
EXIT_SCHEMA = {
    "type": "object",
    "properties": {
        "exit": {
            "type": "object",
            "properties": {"take": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["take", "reason"],
        },
        "branches": SCHEMA["properties"]["branches"],
    },
    "required": ["exit", "branches"],
}

Runner = Callable[..., subprocess.CompletedProcess[str]]


# ------------------------------------------------------------------------ request/result
@dataclass(frozen=True)
class BranchView:
    id: str
    name: str
    condition: str


@dataclass(frozen=True)
class DecisionRequest:
    """Everything a decision needs, copied out of the database."""

    task_id: str
    fork_stage_id: str
    title: str
    description: str
    history: tuple[str, ...]  # what the earlier stages said
    branches: tuple[BranchView, ...]  # only those that need a decision
    always: tuple[str, ...]  # link ids taken without asking
    cli: Cli
    account_id: str
    model: str
    prefix: tuple[str, ...]  # argv that starts the CLI
    env: Mapping[str, str]
    # Phase 24: «Terminar aquí» of the stage (its condition), and the stage's name.
    exit: BranchView | None = None
    stage_name: str = ""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None


@dataclass
class DecisionResult:
    taken: dict[str, bool] = field(default_factory=dict)  # link id → taken
    reasons: dict[str, str] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    seconds: float = 0.0
    error: str | None = None
    exit_taken: bool = False  # phase 24: the task ends at the stage
    exit_reason: str = ""

    @property
    def chosen(self) -> list[str]:
        return [i for i, taken in self.taken.items() if taken]


def build_prompt(request: DecisionRequest) -> str:
    if request.exit is not None:
        return _exit_prompt(request)
    branches = "\n".join(f"- {b.id} · {b.name}: {b.condition}" for b in request.branches)
    history = "\n".join(request.history) or "(todavía no hay trabajo previo)"
    return (
        "Eres el enrutador de un pipeline de desarrollo. Decide por qué ramas debe pasar la "
        "tarea según las condiciones de cada rama. Puedes elegir una, varias o todas, pero "
        "debes elegir al menos una. Explica cada decisión en una frase.\n\n"
        f"Tarea: {request.title}\n{request.description.strip()}\n\n"
        f"Trabajo ya hecho:\n{history}\n\n"
        f"Ramas:\n{branches}\n\n"
        'Responde solo con JSON: {"branches": [{"id": "...", "take": true|false, '
        '"reason": "..."}]} con todas las ramas.'
    )


def _exit_prompt(request: DecisionRequest) -> str:
    """Spike S1: first whether the task ends at the stage, then (only if it goes on) its
    branches."""
    assert request.exit is not None
    history = "\n".join(request.history) or "(todavía no hay trabajo previo)"
    head = (
        "Eres el enrutador de un pipeline de desarrollo. La etapa "
        f"«{request.stage_name or 'actual'}» acaba de terminar.\n\n"
        "1. Decide primero si la tarea **termina aquí**: termina solo si se cumple esta "
        f"condición: «{request.exit.condition}». Si la tarea pide además cualquier trabajo "
        "posterior (programar, desplegar…), no termina.\n"
    )
    if request.branches:
        branches = "\n".join(f"- {b.id} · {b.name}: {b.condition}" for b in request.branches)
        head += (
            "2. Si no termina, decide por qué ramas debe pasar según sus condiciones: una, "
            "varias o todas, pero al menos una. Si termina, no tomes ninguna rama.\n\n"
            f"Ramas:\n{branches}\n\n"
        )
    else:
        head += "2. Esta etapa no tiene ramas que decidir: devuelve `branches` vacío.\n\n"
    return (
        head
        + f"Tarea: {request.title}\n{request.description.strip()}\n\n"
        + f"Trabajo ya hecho:\n{history}\n\n"
        + 'Explica cada decisión en una frase. Responde solo con JSON: {"exit": {"take": '
        'true|false, "reason": "..."}, "branches": [{"id": "...", "take": true|false, '
        '"reason": "..."}]}.'
    )


def _read_exit(value: object, result: DecisionResult) -> None:
    exit_ = value.get("exit") if isinstance(value, dict) else None
    if isinstance(exit_, dict):
        result.exit_taken = bool(exit_.get("take"))
        result.exit_reason = str(exit_.get("reason") or "")[:500]


# ----------------------------------------------------------------------------- parsing
def _loads_object(text: str) -> dict | None:
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        value = json.loads(text[start:end])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _read_branches(value: object, request: DecisionRequest) -> tuple[dict, dict] | None:
    """(taken, reasons) by link id from the model's answer; None if it is not usable."""
    items = value.get("branches") if isinstance(value, dict) else None
    if not isinstance(items, list):
        return None
    known = {b.id for b in request.branches}
    taken: dict[str, bool] = {b.id: False for b in request.branches}
    reasons: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in known:
            continue
        taken[item["id"]] = bool(item.get("take"))
        reasons[item["id"]] = str(item.get("reason") or "")[:500]
    return taken, reasons


def parse_claude(stdout: str, request: DecisionRequest) -> DecisionResult:
    data = _loads_object(stdout)
    if data is None:
        return DecisionResult(error="Claude Code no devolvió JSON")
    usage = data.get("usage") or {}
    result = DecisionResult(
        usage=Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
            cost_usd=data.get("total_cost_usd"),
        ),
        model=next(iter(data.get("modelUsage") or {}), request.model),
    )
    if data.get("is_error"):
        result.error = str(data.get("result") or "Claude Code devolvió un error")[:300]
        return result
    value = data.get("structured_output")
    if value is None:
        value = _loads_object(str(data.get("result") or ""))
    parsed = _read_branches(value, request)
    if parsed is None:
        result.error = "la respuesta no tiene el formato esperado"
        return result
    result.taken, result.reasons = parsed
    if request.exit is not None:
        _read_exit(value, result)
    return result


def parse_agy(stdout: str, request: DecisionRequest) -> DecisionResult:
    data = _loads_object(stdout)
    if data is None:
        return DecisionResult(error="agy no devolvió JSON")
    inner = data.get("result") if isinstance(data.get("result"), dict) else data
    usage = inner.get("usage") or {}
    result = DecisionResult(
        usage=Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            thinking_tokens=int(usage.get("thinking_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_tokens") or 0),
        ),
        model=request.model,
    )
    if inner.get("status") not in (None, "SUCCESS"):
        result.error = f"agy terminó con {inner.get('status')}"
        return result
    value = _loads_object(str(inner.get("response") or ""))
    parsed = _read_branches(value, request)
    if parsed is None:
        result.error = "la respuesta no tiene el formato esperado"
        return result
    result.taken, result.reasons = parsed
    if request.exit is not None:
        _read_exit(value, result)
    return result


# ------------------------------------------------------------------------------ calling
def call(request: DecisionRequest, runner: Runner = run_process) -> DecisionResult:
    """One call to the CLI, blocking. Never raises."""
    prompt = safe_prompt(build_prompt(request))
    if request.cli == Cli.CLAUDE:
        argv = [
            *request.prefix, "-p", prompt, "--model", request.model,
            "--output-format", "json",
            "--json-schema", json.dumps(EXIT_SCHEMA if request.exit else SCHEMA),
            "--tools", "", "--strict-mcp-config", "--no-session-persistence",
            "--max-budget-usd", MAX_BUDGET_USD,
        ]  # fmt: skip
        parse = parse_claude
    else:
        argv = [
            *request.prefix, "-p", prompt, "--model", request.model, "--output-format", "json"
        ]  # fmt: skip
        parse = parse_agy
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="agentic-decider-") as folder:
            proc = runner(argv, CALL_TIMEOUT, cwd=folder, env=request.env)
    except subprocess.TimeoutExpired:
        return DecisionResult(error=f"el decisor tardó más de {int(CALL_TIMEOUT)} s")
    except OSError as error:
        return DecisionResult(error=f"no se pudo lanzar el CLI: {error}")
    result = parse(proc.stdout or "", request)
    if proc.returncode and result.error is None and not result.taken:
        result.error = (proc.stderr or "").strip()[:300] or f"el CLI terminó con {proc.returncode}"
    result.seconds = time.monotonic() - started
    if result.error is None and not result.exit_taken and not result.chosen and not request.always:
        result.error = "no eligió ninguna rama"
    return result


# ---------------------------------------------------------------------- configuration
@dataclass(frozen=True)
class Config:
    cli: Cli
    account: CliAccount
    model: str
    prefix: tuple[str, ...]


def resolve_config(
    db: Session, pipeline: Pipeline, overrides: Mapping[str, list[str]] | None = None
) -> Config | str:
    """The CLI, account and model to decide with; or why none can be used."""
    wanted = [Cli(pipeline.decider_cli)] if pipeline.decider_cli else [Cli.CLAUDE, Cli.AGY]
    problems: list[str] = []
    for cli in wanted:
        try:
            prefix = resolve_executable(cli, overrides)
        except ApiError:
            problems.append(f"{cli} no está instalado")
            continue
        account = (
            db.get(CliAccount, pipeline.decider_account_id) if pipeline.decider_account_id else None
        )
        if account is None or account.cli != cli:
            account = account_ops.default_for(db, cli)
        gate = usage_limits.blocked(db, account)
        if gate is not None or account.session_state == SessionState.DOWN:
            name = account_ops.display_name(account)
            problems.append(f"la cuenta {name} no está disponible ({gate or 'sesión'})")
            continue
        model = pipeline.decider_model or CHEAP_MODEL[cli]
        return Config(cli, account, model, tuple(prefix))
    return "; ".join(problems) or "no hay ningún CLI para decidir"


# ----------------------------------------------------------------------------- service
class DecisionService:
    """Asks the model on worker threads; the scheduler applies the answers."""

    def __init__(
        self,
        overrides: Mapping[str, list[str]] | None = None,
        runner: Runner = run_process,
        workers: int = 2,
    ) -> None:
        self._overrides = overrides
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="decider")
        self._lock = threading.Lock()
        self.pending: set[str] = set()  # task ids with a call in flight
        # Set by the scheduler: receives (request, result) from a worker thread.
        self.on_result: Callable[[DecisionRequest, DecisionResult], None] | None = None

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # Scheduler thread ----------------------------------------------------------------
    def request(
        self, db: Session, task: Task, fork: Stage, undecided: list[StageLink], always: list[str]
    ) -> None:
        """`lanes.request_decision`: snapshot the question and send it to a worker."""
        pipeline = db.get(Pipeline, fork.pipeline_id)
        assert pipeline is not None
        config = resolve_config(db, pipeline, self._overrides)
        if isinstance(config, str):
            self.give_up(db, task, config)
            return
        context = task_ops.task_context(db, task)
        request = DecisionRequest(
            task_id=task.id,
            fork_stage_id=fork.id,
            title=task.title,
            description=task.description,
            history=context.history,
            branches=tuple(BranchView(x.id, x.name, x.condition) for x in undecided),
            always=tuple(always),
            cli=config.cli,
            account_id=config.account.id,
            model=config.model,
            prefix=config.prefix,
            env={**clean_env(), **account_ops.env_for(config.account)},
            exit=(
                BranchView(lane_ops.EXIT, lane_ops.EXIT_LABEL, fork.exit_condition or "")
                if lane_ops.has_exit(fork)
                else None
            ),
            stage_name=fork.name,
        )
        with self._lock:
            if task.id in self.pending:
                return
            self.pending.add(task.id)
        self._pool.submit(self._work, request)

    def _work(self, request: DecisionRequest) -> None:
        result = DecisionResult(error="sin respuesta")
        for _ in range(ATTEMPTS):
            result = call(request, self._runner)
            if result.error is None:
                break
            log.warning("branch decision failed", task=request.task_id, error=result.error)
        if self.on_result is None:
            self.forget(request.task_id)
        else:  # the scheduler applies it, and only then is the question closed
            self.on_result(request, result)

    def forget(self, task_id: str) -> None:
        with self._lock:
            self.pending.discard(task_id)

    # Scheduler thread, when the answer arrives ------------------------------------------
    def apply(self, db: Session, request: DecisionRequest, result: DecisionResult) -> None:
        try:
            self._apply(db, request, result)
        finally:
            self.forget(request.task_id)

    def _apply(self, db: Session, request: DecisionRequest, result: DecisionResult) -> None:
        task = db.get(Task, request.task_id)
        fork = db.get(Stage, request.fork_stage_id)
        if task is None or fork is None or task.stage_id != fork.id:
            return
        if task.status != "deciding":  # cancelled or decided by hand meanwhile
            return
        project = db.get(Project, task.project_id)
        run = record_run(db, project, task, fork.id, request, result)
        if result.error is not None:
            self.give_up(db, task, result.error)
            return
        chosen = [*request.always, *result.chosen]
        reasons = {**{i: ALWAYS_REASON for i in request.always}, **result.reasons}
        by = DecisionBy.MODEL
        if request.exit is not None:
            reasons[lane_ops.EXIT] = result.exit_reason
            if result.exit_taken:
                chosen = [lane_ops.EXIT]
            elif preset := lane_ops.root_of(db, task).preset_lanes.get(fork.id):
                # Branches fixed when the task was created still hold once it goes on.
                chosen, by = list(dict.fromkeys([*preset, *request.always])), DecisionBy.PRESET
        if fork.confirm_decision:
            lane_ops.propose(db, task, fork, chosen, reasons, run.id)
            return
        lane_ops.take(db, task, fork, chosen, by, reasons, run.id)

    @staticmethod
    def give_up(db: Session, task: Task, reason: str) -> None:
        """Nobody could pick the branches: the person does."""
        task_ops.wait_for_human(db, task, WaitingReason.CHOOSE_BRANCH, reason)


def record_run(
    db: Session,
    project: Project | None,
    task: Task | None,
    fork_stage_id: str | None,
    request: DecisionRequest,
    result: DecisionResult,
) -> Run:
    """The call as a run of kind «decision»: its usage is the project's and the account's."""
    account = db.get(CliAccount, request.account_id)
    now = utcnow()
    usage = result.usage
    run = Run(
        workspace_id=project.workspace_id if project else DEFAULT_WORKSPACE,
        kind=RunKind.DECISION,
        agent_id=None,
        project_id=project.id if project else None,
        agent_name="Decisor",
        agent_color="#8a8f98",
        project_name=project.name if project else "",
        cli=request.cli,
        model=result.model or request.model,
        prompt=build_prompt(request),
        cwd="",
        status=RunStatus.COMPLETED if result.error is None else RunStatus.FAILED,
        error=result.error,
        task_id=task.id if task else None,
        stage_id=fork_stage_id,
        started_at=now,
        ended_at=now,
        summary=lane_ops.EXIT_LABEL if result.exit_taken else ", ".join(result.chosen),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        thinking_tokens=usage.thinking_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_creation_tokens=usage.cache_creation_tokens,
        cost_usd=usage.cost_usd,
        usage_source="decider",
        usage_status=UsageStatus.FINAL,
        account_id=account.id if account else None,
        account_label=account_ops.display_name(account) if account else "",
    )
    db.add(run)
    db.flush()
    return run


def preview(
    db: Session,
    project: Project,
    pipeline: Pipeline,
    branches: list[BranchView],
    title: str,
    description: str,
    overrides: Mapping[str, list[str]] | None = None,
    runner: Runner = run_process,
    exit_condition: str | None = None,
    stage_name: str = "",
) -> tuple[DecisionResult, DecisionRequest | None]:
    """«Probar»: asks what the decider would choose for an example task, without a task. The
    call is recorded (it costs like any other); `pipeline` may be unsaved."""
    config = resolve_config(db, pipeline, overrides)
    if isinstance(config, str):
        return DecisionResult(error=config), None
    request = DecisionRequest(
        task_id="",
        fork_stage_id="",
        title=title,
        description=description,
        history=(),
        branches=tuple(branches),
        always=(),
        cli=config.cli,
        account_id=config.account.id,
        model=config.model,
        prefix=config.prefix,
        env={**clean_env(), **account_ops.env_for(config.account)},
        exit=(
            BranchView(lane_ops.EXIT, lane_ops.EXIT_LABEL, exit_condition)
            if exit_condition
            else None
        ),
        stage_name=stage_name,
    )
    result = call(request, runner)
    record_run(db, project, None, None, request, result)
    return result, request


__all__ = ["inbox"]
