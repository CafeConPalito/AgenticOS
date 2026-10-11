"""The scheduler: takes queued tasks to their agents and moves tasks on when their runs end
(ADR 0009).

A single thread does all the work, so two decisions on the same queues never overlap and no row
locking is needed on SQLite. It wakes up on `poke()` (a task queued, reordered or edited, the
pause switched…), on `run_ended()` and every BACKUP_TICK seconds as a safety net.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.errors import ApiError
from agentic_os.models import (
    SCHEDULER_PAUSED,
    Agent,
    AgentStatus,
    AppState,
    Project,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    Verdict,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.services import tasks as task_ops

BACKUP_TICK = 5.0
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
    # task id → summary: the user finished the stage by hand while its run was alive.
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

    # ------------------------------------------------------------------ thread
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self.poke()

    def stop(self, timeout: float = 5.0) -> None:
        self._stopping.set()
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

    def complete_manually(self, task_id: str, summary: str) -> None:
        """The user ends the stage of a running task: its run is stopped, and when it ends the
        stage counts as approved with this summary."""
        with self._lock:
            self._inbox.manual[task_id] = summary

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
            running = list(db.scalars(select(Task).where(Task.status == TaskStatus.RUNNING)))
            for task in running:
                task_ops.wait_for_human(db, task, WaitingReason.INTERRUPTED)
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
            for agent in agents:
                self._fill(db, agent)

    def _fill(self, db: Session, agent: Agent) -> None:
        running = db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.agent_id == agent.id, Task.status == TaskStatus.RUNNING)
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
            if task.status == TaskStatus.CANCELLED:  # cancelled while it ran: now it is closed
                self.release_finished(db, task)
                db.commit()
                return
            if task.status != TaskStatus.RUNNING:
                return  # already handled
            with self._lock:
                manual = self._inbox.manual.pop(task.id, None)
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
                project = db.get(Project, task.project_id)
                if project is not None:
                    self._release(db, task, project)
            db.commit()

    def _release(self, db: Session, task: Task, project: Project) -> None:
        try:
            self.release_workspace(db, task, project)
        except Exception:
            log.exception("could not release the workspace", task=task.code)

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
            Task.status == TaskStatus.RUNNING,
            Task.id != task.id,
        )
    )
    return "folder_busy" if busy else None
