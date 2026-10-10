"""Owns every live RunSession of this backend and keeps the `runs` table in sync."""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    ACTIVE_STATUSES,
    Agent,
    Cli,
    EventKind,
    PermissionMode,
    Project,
    Run,
    RunEvent,
    RunStatus,
)
from agentic_os.services.adapters import LaunchContext, adapter_for
from agentic_os.services.context import build_context, build_instructions
from agentic_os.services.hooks import HOOK_EVENTS, interpret, write_hook_script
from agentic_os.services.mcp_server import RunTokens
from agentic_os.services.runs.launcher import resolve_executable
from agentic_os.services.runs.session import RunSession

SHUTDOWN_TIMEOUT = 5.0

log = structlog.get_logger()


class RunManager:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings) -> None:
        self._db = sessions
        self._settings = settings
        # Only runs that are still alive: a finished run is served from its log file.
        self._live: dict[str, RunSession] = {}
        self._live_lock = threading.Lock()
        self.tokens = RunTokens()
        self._mcp_seen: set[str] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

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

    def launch(self, db: Session, agent: Agent, project: Project, prompt: str) -> Run:
        if self.loop is None:
            raise RuntimeError("RunManager.loop is not set (lifespan not started)")
        if not Path(project.path).is_dir():
            raise ApiError(
                422, "folder_not_found", "the project folder does not exist", "project_id"
            )
        cli = Cli(agent.cli)
        adapter = adapter_for(cli)
        resolve_executable(cli, self._settings.cli_command_overrides)  # fail before any write
        if cli == Cli.AGY and self._agy_busy(project.path):
            # Two agy runs in one folder would share the workspace plugin (ADR 0004).
            raise ApiError(409, "agy_folder_busy", "an agy run is already working in this folder")
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
            cwd=project.path,
        )
        db.add(run)
        db.flush()
        run.log_path = str(self.runs_dir / f"{run.id}.log")
        run_dir = self.runs_dir / run.id
        token = self.tokens.issue(run.id)
        ctx = LaunchContext(
            run_id=run.id,
            cli=cli,
            model=agent.model,
            prompt=prompt,
            permission_mode=PermissionMode(agent.permission_mode),
            allowed_tools=tuple(agent.allowed_tools),
            cwd=Path(project.path),
            run_dir=run_dir,
            base_url=self.public_url,
            token=token,
            instructions=build_instructions(agent, project, project.path),
            hook_command=write_hook_script(run_dir, self.public_url, token),
            overrides=self._settings.cli_command_overrides,
        )
        try:
            spec = adapter.prepare(ctx)
        except Exception:
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            raise
        run.cli_session_id = spec.session_id
        db.commit()

        session = RunSession(
            run.id,
            cli,
            spec,
            project.path,
            Path(run.log_path),
            self.loop,
            lambda changes, run_id=run.id: self._persist(run_id, changes),
            run.cols,
            run.rows,
            deferred_prompt=adapter.deferred_prompt(ctx),
            on_end=lambda: adapter.cleanup(ctx),
            on_system_event=lambda name, detail="", run_id=run.id: self.add_event(
                run_id, EventKind.SYSTEM, name, detail
            ),
        )
        try:
            session.start()
        except Exception as error:  # spawn failed (bad executable, permissions…)
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            run.status, run.error, run.ended_at = RunStatus.FAILED, str(error), utcnow()
            db.commit()
            return run
        with self._live_lock:
            if session.alive:  # it may already have ended (and been dropped) meanwhile
                self._live[run.id] = session
        db.refresh(run)
        return run

    def _agy_busy(self, folder: str) -> bool:
        key = os.path.normcase(os.path.realpath(folder))
        with self._live_lock:
            sessions = list(self._live.values())
        return any(
            s.alive and s.cli == Cli.AGY and os.path.normcase(os.path.realpath(s.cwd)) == key
            for s in sessions
        )

    def stop(self, run_id: str) -> bool:
        session = self.get(run_id)
        if session is None or not session.alive:
            return False
        session.stop()
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
                if changes.get("started") and run.started_at is None:
                    run.started_at = now
                if changes.get("ended"):
                    run.ended_at = now
                db.commit()
        except Exception:  # never break the PTY threads; the state is retried on next change
            log.exception("could not persist run state", run_id=run_id, changes=changes)

    # ------------------------------------------------------------------ events
    def add_event(self, run_id: str, kind: EventKind, name: str, detail: str = "") -> None:
        """Stores an event and pushes it to the run's viewers («Eventos MCP» panel)."""
        with self._db() as db:
            event = RunEvent(run_id=run_id, kind=kind, name=name, detail=detail)
            db.add(event)
            db.commit()
            message = {
                "type": "event",
                "id": event.id,
                "run_id": run_id,
                "at": event.at.isoformat().replace("+00:00", "Z"),
                "kind": event.kind,
                "name": event.name,
                "detail": event.detail,
            }
        session = self.get(run_id)
        if session is not None:
            session.emit(message)

    # ------------------------------------------------------------------ agentic-os MCP tools
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
            instructions = build_instructions(agent, project, run.cwd)
            prompt = run.prompt
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

    def complete_task(self, run_id: str, summary: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            run.summary = summary
            db.commit()
        self.add_event(run_id, EventKind.MCP, "complete_task", summary)
        session = self.get(run_id)
        if session is not None:
            session.mark_completed()

    def write_project_memory(self, run_id: str, note: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            project = db.get(Project, run.project_id) if run and run.project_id else None
            if run is None or project is None:
                return
            stamp = utcnow().astimezone().strftime("%Y-%m-%d %H:%M")
            block = f"### {stamp} · {run.agent_name}\n{note.strip()}"
            project.memory = f"{project.memory.rstrip()}\n\n{block}".strip()
            db.commit()
        self.add_event(run_id, EventKind.MCP, "write_project_memory", note)

    # ------------------------------------------------------------------ CLI hooks
    def on_hook(self, run_id: str, event: str, payload: object) -> None:
        session = self.get(run_id)
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            cli = Cli(run.cli)
            effect = interpret(cli, event, payload)
            if effect.session_id and run.cli_session_id != effect.session_id:
                run.cli_session_id = effect.session_id  # agy: its conversation id
                db.commit()
        boundary = session.on_hook(effect) if session is not None else False
        # agy fires PreInvocation on every model step: only turn boundaries are events.
        if event in HOOK_EVENTS[cli] and (boundary or event not in ("PreInvocation",)):
            self.add_event(run_id, EventKind.HOOK, event)
