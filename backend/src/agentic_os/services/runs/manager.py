"""Owns every live RunSession of this backend and keeps the `runs` table in sync."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import ApiError
from agentic_os.models import ACTIVE_STATUSES, Agent, Cli, Project, Run, RunStatus
from agentic_os.services.runs.launcher import build_launch
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
        self.loop: asyncio.AbstractEventLoop | None = None

    @property
    def runs_dir(self) -> Path:
        return Path(self._settings.data_dir) / "runs"

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
        spec = build_launch(cli, agent.model, prompt, self._settings.cli_command_overrides)
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
            cli_session_id=spec.session_id,
        )
        db.add(run)
        db.flush()
        run.log_path = str(self.runs_dir / f"{run.id}.log")
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
        )
        try:
            session.start()
        except Exception as error:  # spawn failed (bad executable, permissions…)
            run.status, run.error, run.ended_at = RunStatus.FAILED, str(error), utcnow()
            db.commit()
            return run
        with self._live_lock:
            if session.alive:  # it may already have ended (and been dropped) meanwhile
                self._live[run.id] = session
        db.refresh(run)
        return run

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
