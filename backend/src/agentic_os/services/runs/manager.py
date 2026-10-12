"""Owns every live RunSession of this backend and keeps the `runs` table in sync."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    ACTIVE_STATUSES,
    Agent,
    AgentStatus,
    Cli,
    EventKind,
    InboxItem,
    InboxKind,
    PermissionMode,
    Project,
    Resolution,
    Run,
    RunEvent,
    RunStatus,
    Stage,
    Task,
    TaskEventKind,
    TaskStatus,
    Verdict,
    WaitingReason,
)
from agentic_os.services import inbox
from agentic_os.services import tasks as task_ops
from agentic_os.services.adapters import CliAdapter, LaunchContext, adapter_for
from agentic_os.services.context import build_context, build_instructions
from agentic_os.services.hooks import (
    HOOK_EVENTS,
    STATUS_LINE,
    TOOL_EVENTS,
    interpret,
    write_hook_script,
)
from agentic_os.services.mcp_server import RunTokens
from agentic_os.services.memory import add_agent_note, list_notes, render_memory
from agentic_os.services.runs import resume as resume_ops
from agentic_os.services.runs.launcher import resolve_executable
from agentic_os.services.runs.resume import SESSION_MISSING
from agentic_os.services.runs.screen import PermissionDialog
from agentic_os.services.runs.session import RunSession
from agentic_os.services.tasks import task_context
from agentic_os.services.usage.limits import CLI_NAMES
from agentic_os.services.usage.reader import UsageService

PERMISSION_DETAIL = {
    "claude": "Claude Code pide permiso para esta acción.",
    "command": "agy pide permiso para ejecutar este comando.",
    "tool": "agy pide permiso para usar esta herramienta.",
}

SHUTDOWN_TIMEOUT = 5.0
MAX_SUBAGENTS = 3  # live subagents per run


@dataclass
class NativeState:
    """Native subagents of a run being paired: announced (pending) → started (by_key)."""

    pending: list[str] = field(default_factory=list)
    by_key: dict[str, str] = field(default_factory=dict)  # agent id / conversation → node


log = structlog.get_logger()


class RunManager:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings) -> None:
        self._db = sessions
        self._settings = settings
        # Only runs that are still alive: a finished run is served from its log file.
        self._live: dict[str, RunSession] = {}
        self._live_lock = threading.Lock()
        self._agy_folders: set[str] = set()  # folders with a live (or starting) agy run
        self.tokens = RunTokens()
        self._mcp_seen: set[str] = set()
        self._natives: dict[str, NativeState] = {}  # native subagents being tracked, by run
        # Claude's PermissionRequest hook: what the open dialog asks, by run (the screen
        # cannot always be read cleanly).
        self._permission_requests: dict[str, str] = {}
        # Resumed agy runs until their first hook confirms the conversation (agy opens a new
        # one, silently, when it no longer has the requested one: evidence R1).
        self._resume_unconfirmed: set[str] = set()
        self._session_missing: set[str] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        # Called (from the run's thread) once a run has ended and its state is persisted.
        self.on_run_ended: Callable[[str], None] | None = None
        # Called when tasks change outside an API request (a permission dialog, an answer…).
        self.on_tasks_changed: Callable[[], None] | None = None
        # Usage of the runs (phase 07). Without `start()` it reads synchronously (tests).
        self.usage = UsageService(sessions, publish=self._publish)
        # The installed version of a CLI, if already known (never probes: that is slow).
        self.cli_version: Callable[[Cli], str | None] = lambda cli: None

    @property
    def runs_dir(self) -> Path:
        return Path(self._settings.data_dir) / "runs"

    @property
    def public_url(self) -> str:
        """Where the agent CLIs reach this backend (MCP server and hooks)."""
        return f"http://127.0.0.1:{self._settings.port}"

    # ------------------------------------------------------------------ queries
    def get(self, run_id: str) -> RunSession | None:
        with self._live_lock:
            return self._live.get(run_id)

    def live_ids(self) -> list[str]:
        with self._live_lock:
            return [run_id for run_id, s in self._live.items() if s.alive]

    # ------------------------------------------------------------------ lifecycle
    def recover(self) -> int:
        """Runs left active by a previous backend (crash, forced close) cannot be resumed."""
        with self._db() as db:
            leftovers = db.execute(
                select(Run.id, Run.cli, Run.cwd).where(
                    Run.status.in_([st.value for st in ACTIVE_STATUSES])
                )
            ).all()
            for run_id, cli, cwd in leftovers:
                with contextlib.suppress(Exception):  # a plugin left by a crashed run
                    adapter_for(Cli(cli)).recover(Path(cwd), run_id)
            result = db.execute(
                update(Run)
                .where(Run.status.in_([s.value for s in ACTIVE_STATUSES]))
                .values(status=RunStatus.INTERRUPTED, activity="idle", ended_at=utcnow())
            )
            db.commit()
            return result.rowcount or 0

    def launch(
        self,
        db: Session,
        agent: Agent,
        project: Project,
        prompt: str,
        task: Task | None = None,
        cwd: str | None = None,
        parent: Run | None = None,
        resumed_from: Run | None = None,
        baseline: dict | None = None,
    ) -> Run:
        """Starts a CLI session. `task`: a run the scheduler launches for a task's current stage;
        `cwd`: its workspace (the task's worktree), the project folder by default; `parent`: the
        run that launched this one as its subagent (spawn_subagent); `resumed_from`: the run
        whose CLI conversation this one continues, with the transcript's `baseline` (resume)."""
        if self.loop is None:
            raise RuntimeError("RunManager.loop is not set (lifespan not started)")
        cwd = cwd or project.path
        if not Path(cwd).is_dir():
            raise ApiError(
                422, "folder_not_found", "the project folder does not exist", "project_id"
            )
        cli = Cli(agent.cli)
        adapter = adapter_for(cli)
        resolve_executable(cli, self._settings.cli_command_overrides)  # fail before any write
        # Two agy runs in one folder would share the workspace plugin (ADR 0004): the folder is
        # reserved atomically before anything is written, and released when the run ends.
        folder = self._reserve_agy_folder(cwd) if cli == Cli.AGY else None
        try:
            return self._launch(
                db,
                agent,
                project,
                prompt,
                task,
                cwd,
                cli,
                adapter,
                folder,
                parent,
                resumed_from,
                baseline,
            )
        except Exception:
            self._release_agy_folder(folder)
            raise

    def resume(self, db: Session, old: Run) -> Run:
        """«Reanudar sesión»: a new run that continues the CLI conversation of `old`, with a new
        context and token. Its task (if any) runs again with it."""
        baseline = resume_ops.check(db, old, self.usage.transcript(old))
        agent = db.get(Agent, old.agent_id) if old.agent_id else None
        project = db.get(Project, old.project_id) if old.project_id else None
        if agent is None or project is None:
            raise ApiError(409, "not_resumable", "the run's agent or project no longer exists")
        task = db.get(Task, old.task_id) if old.task_id else None
        run = self.launch(
            db,
            agent,
            project,
            resume_ops.RESUME_PROMPT,
            task,
            old.cwd,
            resumed_from=old,
            baseline=baseline,
        )
        if task is not None:
            task = db.get(Task, task.id)
            assert task is not None
            if run.status == RunStatus.FAILED:  # the process could not be spawned
                task_ops.wait_for_human(
                    db, task, WaitingReason.LAUNCH_FAILED, run.error or "", run_id=run.id
                )
            else:
                inbox.resolve_pending(
                    db, Resolution.DISMISSED, task_id=task.id, kinds=task_ops.ATTENTION_KINDS
                )
                task_ops.mark_running(db, task, run.id)
            db.commit()
            self._notify_change()
        self.add_event(old.id, EventKind.SYSTEM, "resumed", run.id)
        return run

    def _launch(
        self,
        db: Session,
        agent: Agent,
        project: Project,
        prompt: str,
        task: Task | None,
        cwd: str,
        cli: Cli,
        adapter: CliAdapter,
        folder: str | None,
        parent: Run | None = None,
        resumed_from: Run | None = None,
        baseline: dict | None = None,
    ) -> Run:
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_id=agent.id,
            project_id=project.id,
            agent_name=agent.name,
            agent_color=agent.color,
            project_name=project.name,
            cli=cli.value,
            model=agent.model,
            prompt=prompt,
            cwd=cwd,
            task_id=task.id if task else None,
            stage_id=task.stage_id if task else None,
            parent_run_id=parent.id if parent else None,
            resumed_from_id=resumed_from.id if resumed_from else None,
            usage_baseline=baseline if resumed_from else None,
        )
        db.add(run)
        db.flush()
        run.log_path = str(self.runs_dir / f"{run.id}.log")
        run.cli_version = self.cli_version(cli)
        run_dir = self.runs_dir / run.id
        token = self.tokens.issue(run.id)
        ctx = LaunchContext(
            run_id=run.id,
            cli=cli,
            model=agent.model,
            prompt=prompt,
            permission_mode=PermissionMode(agent.permission_mode),
            allowed_tools=tuple(agent.allowed_tools),
            cwd=Path(cwd),
            run_dir=run_dir,
            base_url=self.public_url,
            token=token,
            instructions=self._instructions(db, run, agent, project, task),
            hook_command=write_hook_script(run_dir, self.public_url, token),
            overrides=self._settings.cli_command_overrides,
            resume_session=resumed_from.cli_session_id if resumed_from else None,
        )
        try:
            spec = adapter.prepare(ctx)
        except Exception:
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            raise
        run.cli_session_id = spec.session_id
        db.commit()
        if resumed_from is not None and cli == Cli.AGY:
            self._resume_unconfirmed.add(run.id)

        session = RunSession(
            run.id,
            cli,
            spec,
            cwd,
            Path(run.log_path),
            self.loop,
            lambda changes, run_id=run.id: self._persist(run_id, changes),
            run.cols,
            run.rows,
            deferred_prompt=adapter.deferred_prompt(ctx),
            on_end=lambda run_id=run.id: self._on_end(run_id, adapter, ctx, folder, session),
            on_system_event=lambda name, detail="", run_id=run.id: self.add_event(
                run_id, EventKind.SYSTEM, name, detail
            ),
            on_permission=lambda dialog, run_id=run.id: self.permission_requested(run_id, dialog),
            on_permission_gone=lambda run_id=run.id: self.permission_gone(run_id),
            on_quota=lambda notice, run_id=run.id: self.quota_detected(run_id, notice),
        )
        try:
            session.start()
        except Exception as error:  # spawn failed (bad executable, permissions…)
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            self._release_agy_folder(folder)
            run.status, run.error, run.ended_at = RunStatus.FAILED, str(error), utcnow()
            db.commit()
            return run
        with self._live_lock:
            if session.alive:  # it may already have ended (and been dropped) meanwhile
                self._live[run.id] = session
        db.refresh(run)
        return run

    def _on_end(
        self,
        run_id: str,
        adapter: CliAdapter,
        ctx: LaunchContext,
        folder: str | None,
        session: RunSession | None = None,
    ) -> None:
        try:
            adapter.cleanup(ctx)
        finally:
            self._release_agy_folder(folder)
            if ctx.resume_session:
                self._end_of_resumed(run_id, session)
            self.usage.request(run_id, final=True)
            try:
                self._after_run_end(run_id)
            except Exception:
                log.exception("could not finish the run's links", run_id=run_id)
            if self.on_run_ended is not None:  # the scheduler moves the task on
                self.on_run_ended(run_id)

    def _end_of_resumed(self, run_id: str, session: RunSession | None) -> None:
        """A resumed run whose CLI did not have the conversation any more ends as failed, with
        an error the UI explains (Claude says so and exits; agy opened another one)."""
        self._resume_unconfirmed.discard(run_id)
        missing = run_id in self._session_missing or (
            session is not None and session.session_missing()
        )
        self._session_missing.discard(run_id)
        if not missing:
            return
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            run.status, run.error = RunStatus.FAILED, SESSION_MISSING
            db.commit()
        self.add_event(run_id, EventKind.SYSTEM, "session_missing")

    def _after_run_end(self, run_id: str) -> None:
        """A subagent's result goes to its parent; a parent's end stops its subagents."""
        self._natives.pop(run_id, None)
        self._permission_requests.pop(run_id, None)
        self._mcp_seen.discard(run_id)
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            children = list(
                db.scalars(
                    select(Run.id).where(
                        Run.parent_run_id == run_id,
                        Run.status.in_([s.value for s in ACTIVE_STATUSES]),
                    )
                )
            )
            parent_id, name, status, summary = (
                run.parent_run_id,
                run.agent_name,
                run.status,
                run.summary,
            )
        for child in children:
            self.stop(child)
        if parent_id:
            result = summary or f"terminó sin resumen (estado: {status})"
            self.deliver(parent_id, f"Resultado del subagente {name}: {result}")
            self.add_event(parent_id, EventKind.SYSTEM, "subagent_finished", f"{name}: {result}")

    def _reserve_agy_folder(self, folder: str) -> str:
        key = os.path.normcase(os.path.realpath(folder))
        with self._live_lock:
            if key in self._agy_folders:
                raise ApiError(
                    409, "agy_folder_busy", "an agy run is already working in this folder"
                )
            self._agy_folders.add(key)
        return key

    def _release_agy_folder(self, key: str | None) -> None:
        if key is not None:
            with self._live_lock:
                self._agy_folders.discard(key)

    def stop(self, run_id: str) -> bool:
        """Stops a run and its live subagents."""
        session = self.get(run_id)
        if session is None or not session.alive:
            return False
        session.stop()
        with self._db() as db:
            children = list(
                db.scalars(
                    select(Run.id).where(
                        Run.parent_run_id == run_id,
                        Run.status.in_([s.value for s in ACTIVE_STATUSES]),
                    )
                )
            )
        for child in children:
            self.stop(child)
        return True

    def shutdown(self, timeout: float = SHUTDOWN_TIMEOUT) -> None:
        """Stops every live run in parallel; whatever does not exit in time is killed."""
        with self._live_lock:
            live = [s for s in self._live.values() if s.alive]
        if not live:
            return

        def stop_one(session: RunSession) -> None:
            session.stop(timeout=timeout)
            if not session.wait(timeout + 1):
                session.kill()
                session.wait(2)

        with ThreadPoolExecutor(max_workers=len(live)) as pool:
            list(pool.map(stop_one, live))

    # ------------------------------------------------------------------ persistence
    def _persist(self, run_id: str, changes: dict) -> None:
        if changes.get("ended"):
            with self._live_lock:
                self._live.pop(run_id, None)
            self.tokens.revoke(run_id)
        values: dict = {}
        for key in ("status", "activity", "exit_code", "cols", "rows"):
            if key in changes:
                values[key] = changes[key]
        now = utcnow()
        try:
            with self._db() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                for key, value in values.items():
                    setattr(run, key, value)
                if "activity" in values:
                    if values["activity"] == "idle":
                        run.idle_since = run.idle_since or now
                    else:  # working again: an «Sin terminar» notice no longer applies
                        run.idle_since = None
                        inbox.resolve_pending(
                            db, Resolution.DISMISSED, run_id=run_id, kinds=(InboxKind.STALLED,)
                        )
                if changes.get("started") and run.started_at is None:
                    run.started_at = now
                if changes.get("ended"):
                    run.ended_at = now
                db.commit()
        except Exception:  # never break the PTY threads; the state is retried on next change
            log.exception("could not persist run state", run_id=run_id, changes=changes)

    # ------------------------------------------------------------------ events
    def _publish(self, run_id: str, message: dict) -> None:
        session = self.get(run_id)
        if session is not None:
            session.emit(message)

    def add_event(self, run_id: str, kind: EventKind, name: str, detail: str = "") -> None:
        """Stores an event and pushes it to the run's viewers («Eventos MCP» panel). Called from
        the session threads too: an error is logged, never raised into them."""
        try:
            message = self._store_event(run_id, kind, name, detail)
        except Exception:
            log.exception("could not store run event", run_id=run_id, name=name)
            return
        session = self.get(run_id)
        if session is not None:
            session.emit(message)

    def _store_event(self, run_id: str, kind: EventKind, name: str, detail: str) -> dict:
        with self._db() as db:
            event = RunEvent(run_id=run_id, kind=kind, name=name, detail=detail)
            db.add(event)
            db.commit()
            return {
                "type": "event",
                "id": event.id,
                "run_id": run_id,
                "at": event.at.isoformat().replace("+00:00", "Z"),
                "kind": event.kind,
                "name": event.name,
                "detail": event.detail,
            }

    # ------------------------------------------------------------------ agentic-os MCP tools
    def _instructions(
        self,
        db: Session,
        run: Run,
        agent: Agent | None,
        project: Project | None,
        task: Task | None,
    ) -> str:
        parent = db.get(Run, run.parent_run_id) if run.parent_run_id else None
        return build_instructions(
            agent,
            project,
            run.cwd,
            self._memory(db, project),
            task_context(db, task) if task else None,
            subagent=(parent.agent_name, run.prompt) if parent else None,
        )

    @staticmethod
    def _memory(db: Session, project: Project | None) -> str:
        return render_memory(list_notes(db, project.id)) if project is not None else ""

    def mcp_connected(self, run_id: str) -> None:
        """Called on every MCP request of a run: only the first one is news."""
        if run_id in self._mcp_seen:
            return
        self._mcp_seen.add(run_id)
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is not None and run.mcp_connected_at is None:
                run.mcp_connected_at = utcnow()
                db.commit()
        self.add_event(run_id, EventKind.SYSTEM, "mcp_connected")
        session = self.get(run_id)
        if session is not None:
            session.on_mcp_connected()

    def get_context(self, run_id: str) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            agent = db.get(Agent, run.agent_id) if run.agent_id else None
            project = db.get(Project, run.project_id) if run.project_id else None
            task = db.get(Task, run.task_id) if run.task_id else None
            instructions = self._instructions(db, run, agent, project, task)
            prompt = None if task else run.prompt
        self.add_event(run_id, EventKind.MCP, "get_context")
        return build_context(instructions, prompt)

    def report_status(self, run_id: str, message: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            run.last_status = message
            db.commit()
        self.add_event(run_id, EventKind.MCP, "report_status", message)

    def complete_task(
        self, run_id: str, summary: str, verdict: Verdict = Verdict.APPROVED
    ) -> str | None:
        """Records the end of the agent's work. Returns an error for the model (and records
        nothing) when it rejects outside a stage that can reject."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return None
            if verdict == Verdict.REJECTED:
                stage = db.get(Stage, run.stage_id) if run.stage_id else None
                if stage is None or stage.reject_to_stage_id is None:
                    return (
                        "Esta etapa no puede rechazar. Si has terminado, llama a complete_task "
                        'con verdict="approved" y cuenta en el resumen lo que no esté bien.'
                    )
            run.summary = summary
            run.verdict = verdict
            db.commit()
        detail = summary if verdict == Verdict.APPROVED else f"[rechazada] {summary}"
        self.add_event(run_id, EventKind.MCP, "complete_task", detail)
        session = self.get(run_id)
        if session is not None:
            session.mark_completed()
        return None

    def write_project_memory(self, run_id: str, note: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            project = db.get(Project, run.project_id) if run and run.project_id else None
            if run is None or project is None:
                return
            add_agent_note(db, project.id, run.agent_id, run.agent_name, note)
            db.commit()
        self.add_event(run_id, EventKind.MCP, "write_project_memory", note)

    # ------------------------------------------------------------------ permission dialogs
    def permission_requested(self, run_id: str, dialog: PermissionDialog) -> None:
        """A permission dialog of the CLI is waiting (from the session's thread): an
        «Aprobación» in the Inbox, and its task waits for the person."""
        detail = self._permission_requests.pop(run_id, None) or dialog.subject
        try:
            with self._db() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                task = db.get(Task, run.task_id) if run.task_id else None
                inbox.resolve_pending(  # a previous dialog of this run is gone
                    db, Resolution.ANSWERED_IN_TERMINAL, run_id=run_id, kinds=(InboxKind.APPROVAL,)
                )
                inbox.create(
                    db,
                    InboxKind.APPROVAL,
                    "¿Puedo continuar?",
                    PERMISSION_DETAIL.get(dialog.kind, ""),
                    task=task,
                    run=run,
                    command=detail or None,
                )
                if task is not None and task.status == TaskStatus.RUNNING:
                    task_ops.wait_for_human(db, task, WaitingReason.PERMISSION, detail, run_id)
                db.commit()
        except Exception:
            log.exception("could not record a permission request", run_id=run_id)
        self.add_event(run_id, EventKind.SYSTEM, "permission_requested", detail)
        self._notify_change()

    def permission_gone(self, run_id: str) -> None:
        """The dialog went away: answered from the Inbox, or by the person in the terminal."""
        try:
            with self._db() as db:
                inbox.resolve_pending(
                    db, Resolution.ANSWERED_IN_TERMINAL, run_id=run_id, kinds=(InboxKind.APPROVAL,)
                )
                run = db.get(Run, run_id)
                task = db.get(Task, run.task_id) if run and run.task_id else None
                if task is not None and task.waiting_reason == WaitingReason.PERMISSION:
                    task_ops.resume(db, task)
                db.commit()
        except Exception:
            log.exception("could not record a permission answer", run_id=run_id)
        self.add_event(run_id, EventKind.SYSTEM, "permission_answered")
        self._notify_change()

    def quota_detected(self, run_id: str, notice: str) -> None:
        """The CLI says it ran out of quota (from the session's thread): a «Cuota agotada» in
        the Inbox, its task waits, and the scheduler starts nothing of this CLI until the
        person resumes (phase 07)."""
        try:
            with self._db() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                cli = Cli(run.cli)
                task = db.get(Task, run.task_id) if run.task_id else None
                if not inbox.pending(db, run_id=run_id, kinds=(InboxKind.QUOTA,)):
                    item = inbox.create(
                        db,
                        InboxKind.QUOTA,
                        f"{CLI_NAMES[cli]} se ha quedado sin cuota",
                        notice,
                        task=task,
                        run=run,
                    )
                    item.command = cli.value  # which CLI is blocked (limits.quota_pending)
                if task is not None and task.status == TaskStatus.RUNNING:
                    task_ops.wait_for_human(db, task, WaitingReason.QUOTA, notice, run_id)
                db.commit()
        except Exception:
            log.exception("could not record a quota notice", run_id=run_id)
        self.add_event(run_id, EventKind.SYSTEM, "quota_exhausted", notice)
        self._notify_change()

    def resume_after_quota(
        self,
        db: Session,
        item: InboxItem,
        resolution: Resolution = Resolution.APPROVED,
        nudge: bool = True,
    ) -> None:
        """«Reanudar» (or «Descartar», without the nudge): the task runs again, the agent is
        told to go on if its CLI is still alive, and the scheduler may start tasks of this CLI
        again. The caller commits."""
        inbox.resolve(db, item, resolution)
        task = db.get(Task, item.task_id) if item.task_id else None
        if task is not None and task.waiting_reason == WaitingReason.QUOTA:
            task_ops.resume(db, task)
        if item.run_id:
            session = self.get(item.run_id)
            if session is not None and session.alive:
                session.quota_resumed()  # a new notice is reported again
                if nudge:
                    session.deliver("continúa")
                    self.add_event(item.run_id, EventKind.SYSTEM, "quota_resumed")

    def _notify_change(self) -> None:
        """Tasks or the Inbox changed outside a request: the scheduler takes another look."""
        if self.on_tasks_changed is not None:
            self.on_tasks_changed()

    # ------------------------------------------------------------------ request_human
    def request_human(
        self, run_id: str, title: str, detail: str = "", options: list[str] | None = None
    ) -> str:
        """The agent asks the person (MCP request_human): an Inbox item, the task waits, and
        the answer comes back as a message typed into the CLI."""
        options = [o for o in (options or []) if str(o).strip()]
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return "Error: ejecución desconocida."
            task = db.get(Task, run.task_id) if run.task_id else None
            kind = InboxKind.QUESTION if options else InboxKind.BLOCKER
            inbox.create(db, kind, title, detail, task=task, run=run, options=options)
            if task is not None:
                task_ops.add_event(db, task, TaskEventKind.HUMAN_REQUEST, title, run_id)
                if task.status == TaskStatus.RUNNING:
                    task_ops.wait_for_human(db, task, WaitingReason.HUMAN_REQUEST, title, run_id)
            db.commit()
        self.add_event(run_id, EventKind.MCP, "request_human", title)
        self._notify_change()
        return (
            "Petición enviada a la persona (Inbox). Termina tu turno ahora, sin seguir "
            "trabajando: su respuesta te llegará como un mensaje nuevo."
        )

    def answer_human(self, db: Session, item: InboxItem, text: str) -> None:
        """The person answered a question or a blocker. A live CLI gets it as a message; if the
        CLI is gone, the answer stays in the task's history and the task is queued again."""
        inbox.resolve(db, item, Resolution.ANSWERED, text)
        task = db.get(Task, item.task_id) if item.task_id else None
        if task is not None:
            task_ops.add_event(
                db, task, TaskEventKind.HUMAN_ANSWERED, f"{item.title} → {text}", item.run_id
            )
        self._reply_to_question(db, item, task, f"Respuesta de la persona a «{item.title}»: {text}")
        if item.run_id:
            self.add_event(item.run_id, EventKind.SYSTEM, "human_answered", text[:200])
        self._notify_change()

    def dismiss_human(self, db: Session, item: InboxItem) -> None:
        """The person dismissed a question or a blocker: the agent is told to go on without
        the answer (otherwise its task would wait forever)."""
        inbox.resolve(db, item, Resolution.DISMISSED)
        task = db.get(Task, item.task_id) if item.task_id else None
        self._reply_to_question(
            db,
            item,
            task,
            f"La persona ha descartado tu petición «{item.title}». Sigue sin esa respuesta o "
            "termina explicando lo que falta.",
        )
        self._notify_change()

    def _reply_to_question(
        self, db: Session, item: InboxItem, task: Task | None, message: str
    ) -> None:
        """Types the reply into the CLI that asked or, if that was a subagent that has ended,
        into its parent. With no live CLI, the task goes back to its queue: a new run reads the
        reply in its context."""
        target = self._live_asker(db, item.run_id)
        if target is not None:
            target.deliver(message)
            if task is not None:
                others = inbox.pending(
                    db, task_id=task.id, kinds=(InboxKind.QUESTION, InboxKind.BLOCKER)
                )
                if not [o for o in others if o.id != item.id]:
                    task_ops.resume(db, task)
            return
        if task is None:
            return
        live_main = db.scalar(
            select(Run.id).where(
                Run.task_id == task.id,
                Run.parent_run_id.is_(None),
                Run.status.in_([s.value for s in ACTIVE_STATUSES]),
            )
        )
        if live_main is None and task.waiting_reason in (
            WaitingReason.HUMAN_REQUEST,
            WaitingReason.QUESTION_PENDING,
        ):
            task_ops.requeue(db, task, front=True)

    def _live_asker(self, db: Session, run_id: str | None) -> RunSession | None:
        if not run_id:
            return None
        session = self.get(run_id)
        if session is not None and session.alive:
            return session
        run = db.get(Run, run_id)
        parent = self.get(run.parent_run_id) if run and run.parent_run_id else None
        return parent if parent is not None and parent.alive else None

    # ------------------------------------------------------------------ subagents, subtasks
    def spawn_subagent(self, run_id: str, prompt: str, agent_name: str = "") -> str:
        """MCP spawn_subagent: a child run in the same workspace, in parallel. Errors are
        returned to the model as text."""
        with self._db() as db:
            parent = db.get(Run, run_id)
            if parent is None:
                return "Error: ejecución desconocida."
            if parent.parent_run_id is not None:
                return "Error: un subagente no puede lanzar otros subagentes."
            launcher = db.get(Agent, parent.agent_id) if parent.agent_id else None
            if launcher is None or not launcher.can_spawn_subagents:
                return (
                    "Error: tu agente no tiene permiso para lanzar subagentes "
                    "(«Puede lanzar subagentes»)."
                )
            alive = db.scalar(
                select(func.count())
                .select_from(Run)
                .where(
                    Run.parent_run_id == run_id,
                    Run.status.in_([s.value for s in ACTIVE_STATUSES]),
                )
            )
            if (alive or 0) >= MAX_SUBAGENTS:
                return f"Error: ya tienes {MAX_SUBAGENTS} subagentes trabajando; espera a uno."
            agent = launcher
            if agent_name.strip():
                agent = db.scalar(
                    select(Agent).where(
                        func.lower(Agent.name) == agent_name.strip().lower(),
                        Agent.status == AgentStatus.ACTIVE,
                    )
                )
                if agent is None:
                    names = ", ".join(db.scalars(select(Agent.name).order_by(Agent.name)))
                    return f"Error: no hay ningún agente «{agent_name}». Agentes: {names}."
            project = db.get(Project, parent.project_id) if parent.project_id else None
            if project is None:
                return "Error: la ejecución no tiene proyecto."
            task = db.get(Task, parent.task_id) if parent.task_id else None
            try:
                child = self.launch(
                    db, agent, project, prompt.strip(), task=task, cwd=parent.cwd, parent=parent
                )
            except ApiError as error:
                if error.code == "agy_folder_busy":
                    return (
                        "Error: ya hay un agente de agy trabajando en esta carpeta; agy no puede "
                        "tener dos sesiones en la misma. Elige un agente de otro CLI."
                    )
                return f"Error: no se pudo lanzar el subagente ({error.message})."
            child_id, child_status = child.id, child.status
        if child_status == RunStatus.FAILED:
            return "Error: el subagente no pudo arrancar."
        self.add_event(run_id, EventKind.MCP, "spawn_subagent", f"{agent.name}: {prompt[:160]}")
        return (
            f"Subagente {agent.name} lanzado (ejecución {child_id[:8]}). Su resultado te llegará "
            "como un mensaje cuando termine; mientras, sigue con tu parte."
        )

    def create_subtask(
        self, run_id: str, title: str, description: str = "", agent_name: str = ""
    ) -> str:
        """MCP create_subtask: a new task in the same project, queued like any other."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None or run.project_id is None:
                return "Error: la ejecución no tiene proyecto."
            creator = db.get(Agent, run.agent_id) if run.agent_id else None
            if creator is None or not creator.can_create_tasks:
                return "Error: tu agente no tiene permiso para crear tareas («Puede crear tareas»)."
            project = db.get(Project, run.project_id)
            agent = creator
            if agent_name.strip():
                agent = db.scalar(
                    select(Agent).where(func.lower(Agent.name) == agent_name.strip().lower())
                )
                if agent is None:
                    return f"Error: no hay ningún agente «{agent_name}»."
            parent_task = db.get(Task, run.task_id) if run.task_id else None
            subtask = task_ops.create_task(
                db,
                project,
                title.strip(),
                description.strip(),
                agent_id=agent.id,
                parent_task_id=parent_task.id if parent_task else None,
            )
            if parent_task is not None:
                task_ops.add_event(
                    db,
                    parent_task,
                    TaskEventKind.SUBTASK,
                    f"{subtask.code} · {subtask.title}",
                    run_id,
                )
            db.commit()
            code = subtask.code
        self.add_event(run_id, EventKind.MCP, "create_subtask", f"{code}: {title[:160]}")
        self._notify_change()
        return f"Subtarea {code} creada y en cola."

    def deliver(self, run_id: str, text: str) -> bool:
        session = self.get(run_id)
        if session is None or not session.alive:
            return False
        session.deliver(text)
        return True

    def answer_permission(self, run_id: str, approve: bool) -> bool:
        session = self.get(run_id)
        return session is not None and session.answer_permission(approve)

    # ------------------------------------------------------------------ native subagents
    def _native_subagent(
        self, run_id: str, cli: Cli, event: str, payload: object, foreign: bool
    ) -> None:
        """The CLIs' own subagents, from their hooks (ADR 0010), as run events
        `subagent_start` / `subagent_stop` with a JSON detail {id, description}."""
        data = payload if isinstance(payload, dict) else {}
        state = self._natives.setdefault(run_id, NativeState())
        if cli == Cli.CLAUDE:
            if event == "PreToolUse" and data.get("tool_name") in ("Agent", "Task"):
                tool_input = (
                    data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
                )
                node = str(data.get("tool_use_id") or f"agent-{len(state.pending)}")
                state.pending.append(node)
                description = tool_input.get("description") or tool_input.get("subagent_type")
                self._native_event(run_id, "subagent_start", node, description or "Subagente")
            elif event == "SubagentStart" and state.pending:
                state.by_key[str(data.get("agent_id"))] = state.pending.pop(0)
            elif event == "SubagentStop":
                # Claude also stops internal agents it never announced: only ours count.
                node = state.by_key.pop(str(data.get("agent_id")), None)
                if node is not None:
                    self._native_event(run_id, "subagent_stop", node, "")
            return
        tool_call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
        if event == "PreToolUse" and tool_call.get("name") == "invoke_subagent":
            args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
            subagents = args.get("Subagents") or [{}]
            for i, sub in enumerate(subagents):
                node = f"{data.get('conversationId', '')}:{data.get('stepIdx', '')}:{i}"
                role = (sub or {}).get("Role") or "Subagente"
                summary = args.get("toolSummary") or ""
                state.pending.append(node)
                self._native_event(run_id, "subagent_start", node, f"{role}: {summary}".strip(": "))
        elif foreign:
            # agy runs the subagent in its own conversation, which never sends its Stop.
            conversation = str(data.get("conversationId"))
            if conversation not in state.by_key and state.pending:
                state.by_key[conversation] = state.pending.pop(0)
        elif event == "PreInvocation" and data.get("invocationNum") == 0 and state.by_key:
            # The main conversation starts a new turn (with the subagents' results): done.
            for node in state.by_key.values():
                self._native_event(run_id, "subagent_stop", node, "")
            state.by_key.clear()

    def _native_event(self, run_id: str, name: str, node: str, description: str) -> None:
        detail = json.dumps({"id": node, "description": description[:300]}, ensure_ascii=False)
        self.add_event(run_id, EventKind.HOOK, name, detail)

    # ------------------------------------------------------------------ CLI hooks
    def on_hook(self, run_id: str, event: str, payload: object) -> None:
        session = self.get(run_id)
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            cli = Cli(run.cli)
            effect = interpret(cli, event, payload)
            if event == STATUS_LINE:  # Claude's status line: only the cost so far
                db.close()
                if effect.transcript_path:
                    self.usage.note_transcript(run_id, effect.transcript_path, own=True)
                self.usage.status_line(run_id, effect.cost_usd, effect.cli_version)
                return
            if effect.permission_request:
                self._permission_requests[run_id] = effect.permission_request
            # A resumed agy run: its first conversation must be the one it asked for.
            if effect.session_id and run_id in self._resume_unconfirmed:
                self._resume_unconfirmed.discard(run_id)
                if effect.session_id != run.cli_session_id:
                    db.close()
                    log.warning("resumed conversation not found", run_id=run_id)
                    self._session_missing.add(run_id)
                    self.stop(run_id)
                    return
            # agy: the first conversation is the run's. A native subagent has its own
            # conversation and fires hooks through the same plugin: they are not the run's
            # turns (and must not replace its id).
            foreign = bool(
                effect.session_id
                and run.cli_session_id
                and cli == Cli.AGY
                and effect.session_id != run.cli_session_id
            )
            if effect.session_id and run.cli_session_id is None:
                run.cli_session_id = effect.session_id
                db.commit()
        if effect.transcript_path:
            try:
                self.usage.note_transcript(run_id, effect.transcript_path, own=not foreign)
            except Exception:
                log.exception("could not note the transcript", run_id=run_id)
        try:
            self._native_subagent(run_id, cli, event, payload, foreign)
        except Exception:
            log.exception("could not track a native subagent", run_id=run_id, hook=event)
        if foreign:
            return
        boundary = session.on_hook(effect) if session is not None else False
        # agy fires PreInvocation on every model step: only turn boundaries are events.
        if event in HOOK_EVENTS[cli] and (boundary or event not in ("PreInvocation", *TOOL_EVENTS)):
            self.add_event(run_id, EventKind.HOOK, event)
        if effect.turn_ended:
            self.usage.request(run_id)  # live usage at the end of every turn
        if effect.turn_ended and session is not None:
            session.after_turn_end()
