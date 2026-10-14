"""The scheduler: takes queued tasks to their agents and moves tasks on when their runs end
(ADR 0009).

A single thread does all the work, so two decisions on the same queues never overlap and no row
locking is needed on SQLite. It wakes up on `poke()` (a task queued, reordered or edited, the
pause switched…), on `run_ended()` and every BACKUP_TICK seconds as a safety net.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    ACTIVE_STATUSES,
    SCHEDULER_PAUSED,
    Agent,
    AgentStatus,
    AppState,
    CliAccount,
    InboxKind,
    Project,
    Resolution,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    Verdict,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.services import accounts as account_ops
from agentic_os.services import inbox
from agentic_os.services import tasks as task_ops
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.usage import switching

BACKUP_TICK = 5.0
STALLED_AFTER = timedelta(minutes=10)
HOUSEKEEPING = 60.0
# A run's usage changes after every turn: the daily limits are checked at most this often.
LIMIT_CHECK_EVERY = 5.0
# Launch errors worth retrying on the next tick (the task stays queued).
TRANSIENT_ERRORS = {"agy_folder_busy"}

log = structlog.get_logger()

RUN_END_REASONS = {
    RunStatus.EXITED: WaitingReason.RUN_EXITED,
    RunStatus.FAILED: WaitingReason.RUN_FAILED,
    RunStatus.STOPPED: WaitingReason.RUN_STOPPED,
    RunStatus.INTERRUPTED: WaitingReason.INTERRUPTED,
}


class Launcher(Protocol):
    """What the scheduler needs from the RunManager (a fake in unit tests)."""

    def launch(
        self,
        db: Session,
        agent: Agent,
        project: Project,
        prompt: str,
        task: Task | None = None,
        cwd: str | None = None,
    ) -> Run: ...


@dataclass
class _Inbox:
    """Work for the scheduler thread, filled from any thread."""

    ended: deque[str] = field(default_factory=deque)
    # run id → summary: the user finished the stage by hand while this run was alive.
    manual: dict[str, str] = field(default_factory=dict)


class Scheduler:
    def __init__(self, sessions: sessionmaker[Session], launcher: Launcher) -> None:
        self._db = sessions
        self._launcher = launcher
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._inbox = _Inbox()
        self._thread: threading.Thread | None = None
        # Workspace hooks (worktrees, phase 05 H4): prepare before a launch, clean up at the end.
        self.prepare_workspace: Callable[[Session, Task, Project], str | None] = (
            lambda db, task, project: None
        )
        self.release_workspace: Callable[[Session, Task, Project], None] = (
            lambda db, task, project: None
        )
        # Asks a CLI whether an account's session is alive (phase 10). Without it (unit tests of
        # the queues) sessions are never checked before a launch.
        self.probe_account: Callable[[Session, CliAccount], object] | None = None
        self._probing: set[str] = set()  # accounts being checked right now
        # Slow periodic chores (e.g. pending folder-trust cleanups), every HOUSEKEEPING seconds.
        self.housekeeping: Callable[[], None] | None = None
        self._last_housekeeping = 0.0
        self._last_limit_check = 0.0
        # Usage worker, housekeeping and the API check the limits: one at a time.
        self._limit_lock = threading.Lock()
        self._limit_timer: threading.Timer | None = None

    # ------------------------------------------------------------------ thread
    def start(self) -> None:
        self._stopping.clear()  # it may start again after a stop (a refused data move)
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self.poke()

    def stop(self, timeout: float = 5.0) -> None:
        self._stopping.set()
        with self._limit_lock:
            if self._limit_timer is not None:
                self._limit_timer.cancel()
                self._limit_timer = None
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def poke(self) -> None:
        self._wake.set()

    def run_ended(self, run_id: str) -> None:
        """RunManager.on_run_ended: called from the run's thread."""
        with self._lock:
            self._inbox.ended.append(run_id)
        self.poke()

    def complete_manually(self, run_id: str, summary: str) -> None:
        """The user ends the stage of a running task: its run is stopped, and when *that run*
        ends the stage counts as approved with this summary."""
        with self._lock:
            self._inbox.manual[run_id] = summary

    def discard_manual(self, run_id: str) -> None:
        with self._lock:
            self._inbox.manual.pop(run_id, None)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            self._wake.wait(BACKUP_TICK)
            self._wake.clear()
            if self._stopping.is_set():
                return
            try:
                self.step()
            except Exception:  # never let the scheduler die: the next tick retries
                log.exception("scheduler step failed")
            now = time.monotonic()
            if self.housekeeping is not None and now - self._last_housekeeping > HOUSEKEEPING:
                self._last_housekeeping = now
                try:
                    self.housekeeping()
                except Exception:
                    log.exception("scheduler housekeeping failed")

    def step(self) -> None:
        """One round: process the ended runs, then start what can start. Public for tests."""
        while True:
            with self._lock:
                if not self._inbox.ended:
                    break
                run_id = self._inbox.ended.popleft()
            try:
                self._handle_run_end(run_id)
            except Exception:
                log.exception("could not process the end of a run", run_id=run_id)
        self.tick()

    # ------------------------------------------------------------------ pause
    @property
    def paused(self) -> bool:
        with self._db() as db:
            state = db.get(AppState, SCHEDULER_PAUSED)
            return state is not None and state.value == "1"

    def set_paused(self, paused: bool) -> None:
        with self._db() as db:
            state = db.get(AppState, SCHEDULER_PAUSED) or AppState(key=SCHEDULER_PAUSED)
            state.value = "1" if paused else "0"
            db.add(state)
            db.commit()
        self.poke()

    # ------------------------------------------------------------------ recovery
    def recover(self) -> int:
        """At startup (after RunManager.recover): tasks whose run died with the previous backend
        wait for the user. Nothing is relaunched by itself."""
        with self._db() as db:
            running = list(db.scalars(select(Task).where(task_ops.occupies_agent())))
            for task in running:
                if task.waiting_reason == WaitingReason.HUMAN_REQUEST:
                    # Its question is still in the Inbox: the answer will start a new run.
                    task_ops.wait_for_human(db, task, WaitingReason.QUESTION_PENDING)
                else:
                    task_ops.wait_for_human(db, task, WaitingReason.INTERRUPTED)
            inbox.resolve_pending(db, Resolution.DISMISSED, kinds=(InboxKind.APPROVAL,))
            db.commit()
            return len(running)

    # ------------------------------------------------------------------ starting tasks
    def tick(self) -> None:
        if self.paused:
            return
        with self._db() as db:
            agents = list(
                db.scalars(
                    select(Agent).where(
                        Agent.status == AgentStatus.ACTIVE,
                        Agent.id.in_(select(Task.agent_id).where(Task.status == TaskStatus.QUEUED)),
                    )
                )
            )
            if not agents:
                return
            index = account_ops.AccountIndex(db)
            self._refresh_sessions(db, {a.id for a in (index.of(g) for g in agents) if a})
            # An account over its daily limit, out of quota or logged out starts nothing
            # (phases 07 and 10); the other accounts of its CLI go on.
            gates = usage_limits.blocked_all(db)
            deciding = switching.decisions_pending(db)
            for agent in agents:
                if agent.id in deciding:  # the person is choosing between its CLIs
                    continue
                account = index.of(agent)
                if account is None or gates.get(account.id) is None:
                    self._fill(db, agent)

    def _refresh_sessions(self, db: Session, account_ids: set[str]) -> None:
        """Asks the CLI again about the accounts whose session was last checked a while ago,
        before a task starts with them: a logout is found here and not as a stuck terminal."""
        if self.probe_account is None:
            return
        stale = [
            a.id
            for a in account_ops.list_accounts(db)
            if a.id in account_ids
            and not account_ops.session_is_fresh(a)
            and a.id not in self._probing
        ]
        if not stale:
            return
        self._probing.update(stale)
        # The CLIs take seconds to answer: never on the scheduler thread. The tick goes on with
        # what is known; a logout found here holds the account from the next tick.
        threading.Thread(
            target=self._probe_sessions, args=(stale,), name="session-probe", daemon=True
        ).start()

    def _probe_sessions(self, account_ids: list[str]) -> None:
        try:
            for account_id in account_ids:
                with self._db() as db:
                    account = db.get(CliAccount, account_id)
                    if account is None or self.probe_account is None:
                        continue
                    try:
                        self.probe_account(db, account)
                        usage_limits.sync_session_items(db)
                        db.commit()
                    except Exception:
                        db.rollback()
                        log.exception("could not check an account's session", account=account_id)
        finally:
            self._probing.difference_update(account_ids)
            self.poke()

    # ------------------------------------------------------------------ daily limits
    def check_limits(self, force: bool = False) -> None:
        """Creates or resolves the «Límite diario alcanzado» items (phase 07). Called when a
        run's usage changes (throttled) and by the housekeeping (a new day)."""
        with self._limit_lock:
            now = time.monotonic()
            wait = LIMIT_CHECK_EVERY - (now - self._last_limit_check)
            if not force and wait > 0:
                # Throttled: one trailing check, so the change that crosses the limit counts.
                if self._limit_timer is None and not self._stopping.is_set():
                    self._limit_timer = threading.Timer(wait, self._trailing_limit_check)
                    self._limit_timer.daemon = True
                    self._limit_timer.start()
                return
            self._last_limit_check = now
            with self._db() as db:
                unblocked = usage_limits.sync_limit_items(db)
                unblocked = usage_limits.sync_session_items(db) or unblocked
                unblocked = switching.sync_switch_items(db) or unblocked
                db.commit()
        if unblocked:
            self.poke()

    def _trailing_limit_check(self) -> None:
        with self._limit_lock:
            self._limit_timer = None
        try:
            self.check_limits(force=True)
        except Exception:
            log.exception("could not check the daily limits")

    def _fill(self, db: Session, agent: Agent) -> None:
        running = db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.agent_id == agent.id, task_ops.occupies_agent())
        )
        free = agent.max_concurrency - (running or 0)
        for task in task_ops.queue_of(db, agent.id):
            if free <= 0:
                return
            project = db.get(Project, task.project_id)
            if project is None:
                continue
            if blocked_reason(db, task, project) is not None:
                continue  # the only reason to skip ahead in a queue (spec 05)
            if self._start(db, agent, project, task):
                free -= 1

    def _start(self, db: Session, agent: Agent, project: Project, task: Task) -> bool:
        try:
            cwd = self.prepare_workspace(db, task, project)
        except Exception as error:
            log.exception("could not prepare the workspace", task=task.code)
            task_ops.wait_for_human(db, task, WaitingReason.WORKSPACE_FAILED, str(error))
            db.commit()
            return False
        # The worktree exists on disk now: record it before launching, so a failed launch (and
        # its rollback) does not lose it and a retry reuses it.
        db.commit()
        try:
            run = self._launcher.launch(db, agent, project, task_ops.task_prompt(task), task, cwd)
        except ApiError as error:
            db.rollback()
            if error.code in TRANSIENT_ERRORS:
                log.info("launch postponed", task=task.code, reason=error.code)
                return False
            task = db.get(Task, task.id)
            assert task is not None
            task_ops.wait_for_human(db, task, WaitingReason.LAUNCH_FAILED, error.message)
            db.commit()
            return False
        except Exception as error:
            db.rollback()
            log.exception("launch failed", task=task.code)
            task = db.get(Task, task.id)
            assert task is not None
            task_ops.wait_for_human(db, task, WaitingReason.LAUNCH_FAILED, str(error))
            db.commit()
            return False
        task = db.get(Task, task.id)
        assert task is not None
        if run.status == RunStatus.FAILED:  # the process could not be spawned
            task_ops.wait_for_human(
                db, task, WaitingReason.LAUNCH_FAILED, run.error or "", run_id=run.id
            )
        else:
            task_ops.mark_running(db, task, run.id)
        db.commit()
        return run.status != RunStatus.FAILED

    # ------------------------------------------------------------------ ending runs
    def _handle_run_end(self, run_id: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None or run.task_id is None:
                return
            task = db.get(Task, run.task_id)
            if task is None:
                return
            # Nothing the run asked for is still useful once it has ended.
            inbox.resolve_pending(
                db,
                Resolution.DISMISSED,
                run_id=run.id,
                kinds=(InboxKind.APPROVAL, InboxKind.STALLED),
            )
            if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
                self._release_when_idle(db, task)  # the last of its CLIs has to be closed
                db.commit()
                return
            if run.parent_run_id is not None:
                # A subagent: its end never moves the task (its parent's does). A permission
                # dialog it left open no longer holds the task.
                if task.waiting_reason == WaitingReason.PERMISSION and not inbox.pending(
                    db, task_id=task.id, kinds=(InboxKind.APPROVAL,)
                ):
                    task_ops.resume(db, task)
                db.commit()
                return
            if not task_ops.is_live(task):
                return  # already handled
            if (
                task.status == TaskStatus.WAITING_HUMAN
                and task.waiting_reason == WaitingReason.HUMAN_REQUEST
                and run.status != RunStatus.COMPLETED
            ):
                # It waits for an answer with no CLI: no longer holds the agent or the folder.
                task_ops.wait_for_human(db, task, WaitingReason.QUESTION_PENDING, run_id=run.id)
                db.commit()
                return
            with self._lock:
                manual = self._inbox.manual.pop(run.id, None)
            if manual is not None:
                task_ops.stage_completed(db, task, manual, run.id, manual=True)
            elif run.status == RunStatus.COMPLETED and run.verdict == Verdict.REJECTED:
                task_ops.stage_rejected(db, task, run.summary or "", run.id)
            elif run.status == RunStatus.COMPLETED:
                task_ops.stage_completed(db, task, run.summary or "", run.id)
            else:
                reason = RUN_END_REASONS.get(RunStatus(run.status), WaitingReason.RUN_EXITED)
                detail = run.error or (
                    f"exit code {run.exit_code}" if run.exit_code is not None else ""
                )
                task_ops.wait_for_human(db, task, reason, detail, run.id)
            if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
                self._release_when_idle(db, task)
            db.commit()

    def _release_when_idle(self, db: Session, task: Task) -> None:
        """Releases a finished task's workspace once none of its runs (main or subagents) is
        alive: their CLIs may still have files open in the worktree."""
        alive = db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.task_id == task.id, Run.status.in_([s.value for s in ACTIVE_STATUSES]))
        )
        if not alive:
            self.release_finished(db, task)

    def _release(self, db: Session, task: Task, project: Project) -> None:
        try:
            self.release_workspace(db, task, project)
        except Exception:
            log.exception("could not release the workspace", task=task.code)

    def check_stalled(self, now: datetime | None = None) -> int:
        """«Sin terminar»: a task's run that has waited for input for STALLED_AFTER without
        complete_task gets an Inbox item (never closed by itself)."""
        now = now or utcnow()
        created = 0
        with self._db() as db:
            runs = db.scalars(
                select(Run).where(
                    Run.status.in_([s.value for s in ACTIVE_STATUSES]),
                    Run.task_id.is_not(None),
                    Run.parent_run_id.is_(None),
                    Run.summary.is_(None),
                    Run.idle_since.is_not(None),
                    Run.idle_since < now - STALLED_AFTER,
                )
            )
            for run in runs:
                if inbox.pending(db, run_id=run.id, kinds=(InboxKind.STALLED,)):
                    continue
                task = db.get(Task, run.task_id)
                if task is None or task.status != TaskStatus.RUNNING:
                    continue
                minutes = int(STALLED_AFTER.total_seconds() // 60)
                inbox.create(
                    db,
                    InboxKind.STALLED,
                    f"{task.code} · {task.title}",
                    f"{run.agent_name} lleva más de {minutes} minutos esperando sin dar la "
                    "tarea por terminada.",
                    task=task,
                    run=run,
                )
                created += 1
            db.commit()
        return created

    def release_finished(self, db: Session, task: Task) -> None:
        """For tasks finished outside a run end (cancelled, approved in review…)."""
        project = db.get(Project, task.project_id)
        if project is not None:
            self._release(db, task, project)


def blocked_reason(db: Session, task: Task, project: Project) -> str | None:
    """Why a queued task cannot start now even with a free agent: in a direct folder, only one
    task of the project runs at a time."""
    if project.workspace_mode != WorkspaceMode.DIRECT:
        return None
    busy = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.project_id == project.id,
            task_ops.occupies_agent(),
            Task.id != task.id,
        )
    )
    return "folder_busy" if busy else None
