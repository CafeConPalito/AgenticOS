"""Owns every live RunSession of this backend and keeps the `runs` table in sync."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    CliAccount,
    EventKind,
    InboxItem,
    InboxKind,
    PermissionMode,
    Project,
    Resolution,
    Run,
    RunEvent,
    RunRepo,
    RunStatus,
    Stage,
    Task,
    TaskEventKind,
    TaskStatus,
    Verdict,
    WaitingReason,
)
from agentic_os.services import accounts as account_ops
from agentic_os.services import changes as change_ops
from agentic_os.services import git, inbox, runrepos, snapshots
from agentic_os.services import tasks as task_ops
from agentic_os.services.adapters import CliAdapter, LaunchContext, adapter_for
from agentic_os.services.agent_target import Target, target_for
from agentic_os.services.connections import runtime as connection_runtime
from agentic_os.services.connections.redact import Redactor
from agentic_os.services.context import RepoLine, build_context, build_instructions
from agentic_os.services.gitx import activity as git_activity
from agentic_os.services.gitx.runner import Repo as GitRepo
from agentic_os.services.hooks import (
    HOOK_EVENTS,
    STATUS_LINE,
    TOOL_EVENTS,
    HookEffect,
    interpret,
    write_hook_script,
)
from agentic_os.services.knowledge import agent_tools as knowledge_tools
from agentic_os.services.knowledge import context as knowledge_context
from agentic_os.services.knowledge import graph_tools
from agentic_os.services.knowledge import proposals as knowledge_proposals
from agentic_os.services.mcp_server import RunTokens
from agentic_os.services.memory import add_agent_note, list_notes, render_memory
from agentic_os.services.runs import resume as resume_ops
from agentic_os.services.runs.launcher import resolve_executable
from agentic_os.services.runs.resume import SESSION_MISSING
from agentic_os.services.runs.screen import PermissionDialog
from agentic_os.services.runs.session import RunSession
from agentic_os.services.skills import proposals as skill_proposals
from agentic_os.services.skills import runtime as skill_runtime
from agentic_os.services.skills.library import SkillLibrary
from agentic_os.services.skills.store import SkillStore
from agentic_os.services.tasks import task_context
from agentic_os.services.usage.limits import title_name
from agentic_os.services.usage.reader import UsageService

PERMISSION_DETAIL = {
    "claude": "Claude Code pide permiso para esta acción.",
    "command": "agy pide permiso para ejecutar este comando.",
    "tool": "agy pide permiso para usar esta herramienta.",
    "edit": "agy pide permiso para editar este archivo.",
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
        # The «Conexiones MCP» block of each live run's instructions (phase 18).
        self._connection_sections: dict[str, str] = {}
        self._natives: dict[str, NativeState] = {}  # native subagents being tracked, by run
        # Claude's PermissionRequest hook: what the open dialog asks, by run (the screen
        # cannot always be read cleanly).
        self._permission_requests: dict[str, str] = {}
        # Resumed agy runs until their first hook confirms the conversation (agy opens a new
        # one, silently, when it no longer has the requested one: evidence R1).
        self._resume_unconfirmed: set[str] = set()
        self._session_missing: set[str] = set()
        # One resume at a time: two requests for the same run would start two CLIs on the
        # same conversation.
        self._resume_lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        # Called (from the run's thread) once a run has ended and its state is persisted.
        self.on_run_ended: Callable[[str], None] | None = None
        self.on_quota_changed: Callable[[], None] | None = None
        # Called when tasks change outside an API request (a permission dialog, an answer…).
        self.on_tasks_changed: Callable[[], None] | None = None
        # Usage of the runs (phase 07). Without `start()` it reads synchronously (tests).
        self.usage = UsageService(sessions, publish=self._publish)
        # The knowledge library's service (phase 14): set by the app once both exist.
        self.knowledge: Any = None
        # The skill library (phase 17): set by the app; a plain one over the data folder if not.
        self.skills: SkillLibrary | None = None
        # The installed version of a CLI, if already known (never probes: that is slow).
        self.cli_version: Callable[[Cli], str | None] = lambda cli: None

    @property
    def _data_dir(self) -> Path:
        return Path(self._settings.data_dir)

    @property
    def skill_library(self) -> SkillLibrary:
        if self.skills is None:
            self.skills = SkillLibrary(SkillStore(self._data_dir))
        return self.skills

    def skill_ranker(self) -> skill_runtime.Ranker:
        """The meaning model the skills are chosen with, if there is one (spike S4)."""
        entry = self.knowledge.embedding_model() if self.knowledge is not None else None
        if entry is None:
            return skill_runtime.Ranker()
        return skill_runtime.Ranker(
            self.knowledge.embed_query,
            entry.id,
            float(entry.usage.get("skill_floor", 0.0)),
            float(entry.usage.get("skill_duplicate", 0.0)),
        )

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
            for run_id, _cli, _cwd in leftovers:  # their diff ends where the folders are now
                self._close_changes(run_id)
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
        if resumed_from is not None:
            # A resumed conversation lives in the CLI, account and model that started it.
            account = self._account_of_run(db, resumed_from)
            target = Target(Cli(resumed_from.cli), account, resumed_from.model, False)
        else:
            target = target_for(db, agent, index=None)
        cli = target.cli
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
                target,
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
        with self._resume_lock:
            db.refresh(old)  # a resume that just finished may have taken it
            return self._resume(db, old)

    def _resume(self, db: Session, old: Run) -> Run:
        resume_ops.check(db, old, self.usage.transcript(old))
        # The old run's usage is settled now: once the resumed run writes to the same
        # transcript, a later read of the old one would count it too.
        self.usage.refresh(old.id, final=True)
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
                task.waiting_reason = task.waiting_detail = None
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
        target: Target,
        adapter: CliAdapter,
        folder: str | None,
        parent: Run | None = None,
        resumed_from: Run | None = None,
        baseline: dict | None = None,
    ) -> Run:
        cli, account, model = target.cli, target.account, target.model
        # The task's vector first: no row of this run is written while the model answers.
        ranker = self.skill_ranker().for_query(
            skill_runtime.query_text(
                db, task.stage_id if task else None, parent is not None, prompt, agent, task
            )
        )
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_id=agent.id,
            project_id=project.id,
            agent_name=agent.name,
            agent_color=agent.color,
            project_name=project.name,
            account_id=account.id,
            account_label=account_ops.display_name(account),
            cli=cli.value,
            model=model,
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
        # The run's skills are chosen once, here: every get_context shows the same ones.
        skill_runtime.prepare_run(db, self.skill_library, self.runs_dir, run, agent, task, ranker)
        # The external MCP servers of the run (phase 18): resolved and recorded once, here.
        connections = connection_runtime.prepare_run(
            db, run, agent, project, task.stage_id if task else None, cli.value
        )
        self._connection_sections[run.id] = connection_runtime.section(connections)
        skills_folder = skill_runtime.skills_dir(self.runs_dir, run.id)
        skills_folder.mkdir(parents=True, exist_ok=True)
        token = self.tokens.issue(run.id)
        targets = runrepos.targets_for(db, project, task)
        ctx = LaunchContext(
            run_id=run.id,
            cli=cli,
            model=model,
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
            account_env=account_ops.env_for(account),
            extra_dirs=(
                *runrepos.extra_dirs(targets, cwd),
                *(str(p) for p in knowledge_context.prepare_folders(self._data_dir, run.id)),
                str(skills_folder),  # the skills' scripts run from there
            ),
            git_authorized=bool(project.agents_git_authorized),
            skills_dir=skills_folder,
            connections=connections,
        )
        try:
            spec = adapter.prepare(ctx)
        except Exception:
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            skill_runtime.clean_run(self.runs_dir, run.id)
            raise
        run.cli_session_id = spec.session_id
        db.commit()
        # What each repository holds before the CLI touches it: the origin of this run's diff.
        self._open_changes(db, run, targets)
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
            redactor=Redactor(connections.secret_values),
            mcp_grace=connections.agy_grace if connections else 0,
        )
        try:
            session.start()
        except Exception as error:  # spawn failed (bad executable, permissions…)
            self.tokens.revoke(run.id)
            adapter.cleanup(ctx)
            skill_runtime.clean_run(self.runs_dir, run.id)
            self._release_agy_folder(folder)
            run.status, run.error, run.ended_at = RunStatus.FAILED, str(error), utcnow()
            self._drop_changes(db, run)  # the CLI never ran: nothing to compare, no refs to keep
            db.commit()
            return run
        with self._live_lock:
            if session.alive:  # it may already have ended (and been dropped) meanwhile
                self._live[run.id] = session
        db.refresh(run)
        return run

    def cli_installed(self, cli: Cli) -> bool:
        return account_ops.is_installed(cli, self._settings.cli_command_overrides)

    def probe_account(self, db: Session, account: CliAccount) -> CliAccount:
        """Asks the account's CLI whether its session is alive (the caller commits)."""
        return account_ops.probe(db, account, self._settings.cli_command_overrides)

    @staticmethod
    def _account_of_run(db: Session, run: Run) -> CliAccount:
        """The login an earlier run used (its account may be gone: then the CLI's default)."""
        earlier = db.get(CliAccount, run.account_id) if run.account_id else None
        if earlier is not None and earlier.cli == run.cli:
            return earlier
        return account_ops.default_for(db, Cli(run.cli))

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
            self._connection_sections.pop(run_id, None)
            knowledge_context.clean_run(self._data_dir, run_id)
            skill_runtime.clean_run(self.runs_dir, run_id)
            self._release_agy_folder(folder)
            self._close_changes(run_id)
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

    # ------------------------------------------------------------------ changes (phase 11)
    @property
    def _scratch_dir(self) -> Path:
        return Path(self._settings.data_dir) / "tmp"

    def _snapshot(
        self, run_id: str, folder: str, label: str, exclude: Sequence[str] = ()
    ) -> snapshots.Snapshot | None:
        """Never fails the run: a snapshot that cannot be taken leaves a system event instead."""
        snapshot, error = snapshots.take_checked(folder, run_id, label, self._scratch_dir, exclude)
        if error is not None:
            self.add_event(run_id, EventKind.SYSTEM, "snapshot_failed", f"{label}: {error}")
        return snapshot

    def _snapshots(
        self, run_id: str, label: str, folders: list[str]
    ) -> list[snapshots.Snapshot | None]:
        """One snapshot per repository folder, at the same time (each is I/O bound)."""

        def one(folder: str) -> snapshots.Snapshot | None:
            return self._snapshot(run_id, folder, label, runrepos.nested_in(folder, folders))

        if len(folders) <= 1:
            return [one(f) for f in folders]
        with ThreadPoolExecutor(max_workers=min(8, len(folders))) as pool:
            return list(pool.map(one, folders))

    def _open_changes(self, db: Session, run: Run, targets: list[runrepos.RunTarget]) -> None:
        """A row per repository of the run, with the snapshot of where it starts."""
        taken = self._snapshots(run.id, "start", [t.folder for t in targets])
        for target, snapshot in zip(targets, taken, strict=True):
            db.add(
                RunRepo(
                    run_id=run.id,
                    repo_id=target.repo_id,
                    repo_name=target.name,
                    path=target.folder,
                    snapshot_start=snapshot.sha if snapshot else None,
                    snapshot_skipped=snapshot.skipped_large if snapshot else 0,
                    refs_start=self._refs_of(target.folder),
                )
            )
        db.commit()

    @staticmethod
    def _refs_of(folder: str) -> dict | None:
        """The references of a repository as a run starts (to tell later what it did with git)."""
        try:
            return git_activity.snapshot(GitRepo(folder))
        except Exception as error:  # a folder that is not a repository (yet): nothing to compare
            log.warning("could not note the references of a run's repository", error=str(error))
            return None

    @staticmethod
    def _drop_changes(db: Session, run: Run) -> None:
        """Forgets the snapshots of a run whose CLI never ran."""
        for row in db.scalars(select(RunRepo).where(RunRepo.run_id == run.id)):
            if row.snapshot_start:
                snapshots.delete_runs(row.path, [run.id])
            db.delete(row)

    def _close_changes(self, run_id: str) -> None:
        """Takes the final snapshot of each repository of the run and stores the +/- summaries.
        Never raises."""
        try:
            with self._db() as db:
                rows = [
                    (row.id, row.path, row.snapshot_start)
                    for row in db.scalars(select(RunRepo).where(RunRepo.run_id == run_id))
                    if row.snapshot_start
                ]
            if not rows:
                # No snapshots to close, but what the run did with git is still worth recording.
                with self._db() as db:
                    run = db.get(Run, run_id)
                    if run is not None:
                        self._record_git_activity(db, run)
                        db.commit()
                return
            ends = self._snapshots(run_id, "end", [path for _id, path, _start in rows])
            results = []
            for (row_id, path, start), end in zip(rows, ends, strict=True):
                if end is None:
                    continue
                try:
                    summary = change_ops.totals(path, start or "", end.sha)
                except git.GitError as error:
                    log.warning("could not summarise the changes", run_id=run_id, error=str(error))
                    summary = None
                results.append((row_id, end, summary))
            with self._db() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                summed = [0, 0, 0]
                have = False
                for row_id, end, summary in results:
                    row = db.get(RunRepo, row_id)
                    if row is None:
                        continue
                    row.snapshot_end = end.sha
                    row.snapshot_skipped = max(row.snapshot_skipped, end.skipped_large)
                    if summary is not None:
                        row.changes_files = summary.files
                        row.changes_added = summary.additions
                        row.changes_deleted = summary.deletions
                        summed = [
                            summed[0] + summary.files,
                            summed[1] + summary.additions,
                            summed[2] + summary.deletions,
                        ]
                        have = True
                if have:
                    run.changes_files, run.changes_added, run.changes_deleted = summed
                self._record_git_activity(db, run)
                db.commit()
        except Exception:  # a run's end must always finish
            log.exception("could not close the run's changes", run_id=run_id)

    @staticmethod
    def _record_git_activity(db: Session, run: Run) -> None:
        """What the run did with git in each repository: stored on its row, the commits
        attributed to the agent, and one line in the task's history. Never raises."""
        done: list[str] = []
        task = db.get(Task, run.task_id) if run.task_id else None
        until = run.ended_at or utcnow()
        for row in db.scalars(select(RunRepo).where(RunRepo.run_id == run.id)):
            if not row.refs_start or row.activity is not None:
                continue
            try:
                found = git_activity.collect(
                    GitRepo(row.path), row.refs_start, run.started_at or run.created_at, until
                )
            except Exception:  # the folder is gone (a released worktree): nothing to read
                log.warning("could not read what the run did with git", run_id=run.id)
                continue
            row.activity = found.model_dump()
            if found.empty:
                continue
            if row.repo_id:
                git_activity.attribute(
                    db, row.repo_id, run, found.commits, task.code if task else None
                )
            done.append(f"{row.repo_name}: {_describe(found)}")
        if done and task is not None:
            task_ops.add_event(db, task, TaskEventKind.GIT, "; ".join(done), run.id)

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
        agents = [a for a in (run.agent_id, parent.agent_id if parent else None) if a]
        return build_instructions(
            agent,
            project,
            run.cwd,
            self._memory(db, project),
            task_context(db, task) if task else None,
            subagent=(parent.agent_name, run.prompt) if parent else None,
            repos=self._repo_lines(db, run, project, task),
            git_authorized=bool(project and project.agents_git_authorized),
            knowledge=knowledge_context.knowledge_section(
                db, self._data_dir, run.id, run.project_id, agents
            ),
            skills=skill_runtime.section(db, self.skill_library, self.runs_dir, run.id),
            connections=self._connection_sections.get(run.id, ""),
        )

    @staticmethod
    def _repo_lines(
        db: Session, run: Run, project: Project | None, task: Task | None
    ) -> list[RepoLine]:
        """The project's repositories as this run sees them, paths relative to its folder."""
        lines: list[RepoLine] = []
        for target in runrepos.targets_for(db, project, task):
            if runrepos.is_within(target.folder, run.cwd):
                path = os.path.relpath(target.folder, run.cwd).replace("\\", "/")
            else:
                path = target.folder
            lines.append(RepoLine(target.name, path, target.branch, target.base))
        return lines

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

    def search_knowledge(
        self, run_id: str, query: str, limit: int, graph: str = "neighbors"
    ) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = knowledge_tools.search_knowledge(
                db, self.knowledge, self._data_dir, run, query, limit, graph
            )
        self.add_event(run_id, EventKind.MCP, "search_knowledge", detail)
        return answer

    def _graph_tool(
        self, run_id: str, name: str, call: Callable[[Session, Run], tuple[str, str]]
    ) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = call(db, run)
        self.add_event(run_id, EventKind.MCP, name, detail)
        return answer

    def knowledge_map(self, run_id: str, topic: str) -> str:
        return self._graph_tool(
            run_id, "knowledge_map", lambda db, run: graph_tools.knowledge_map(db, run, topic)
        )

    def related_knowledge(self, run_id: str, document: str, kinds: str, origin: str) -> str:
        return self._graph_tool(
            run_id,
            "related_knowledge",
            lambda db, run: graph_tools.related_knowledge(db, run, document, kinds, origin),
        )

    def explore_knowledge(
        self,
        run_id: str,
        document: str,
        query: str,
        hops: int,
        kinds: str,
        origin: str,
        level: str,
        max_docs: int,
    ) -> str:
        return self._graph_tool(
            run_id,
            "explore_knowledge",
            lambda db, run: graph_tools.explore_knowledge(
                db, self.knowledge, run, document, query, hops, kinds, origin, level, max_docs
            ),
        )

    def knowledge_path(self, run_id: str, source: str, target: str, max_hops: int) -> str:
        return self._graph_tool(
            run_id,
            "knowledge_path",
            lambda db, run: graph_tools.knowledge_path(db, run, source, target, max_hops),
        )

    def read_knowledge(self, run_id: str, document: str, location: str, part: int) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = knowledge_tools.read_knowledge(
                db, self._data_dir, run, document, location, part
            )
        self.add_event(run_id, EventKind.MCP, "read_knowledge", detail)
        return answer

    def propose_knowledge(
        self,
        run_id: str,
        title: str,
        markdown: str,
        description: str,
        based_on: list[str],
        level: str,
        replaces: str,
    ) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = knowledge_proposals.propose(
                db, self.knowledge, run, title, markdown, description, based_on, level, replaces
            )
        self.add_event(run_id, EventKind.MCP, "propose_knowledge", detail)
        return answer

    def _skill_tool(
        self, run_id: str, name: str, call: Callable[[Session, Run], tuple[str, str]]
    ) -> str:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = call(db, run)
            db.commit()
        self.add_event(run_id, EventKind.MCP, name, detail)
        return answer

    def use_skill(self, run_id: str, name: str) -> str:
        return self._skill_tool(
            run_id,
            "use_skill",
            lambda db, run: skill_runtime.use_skill(
                db, self.skill_library, self.runs_dir, run, name
            ),
        )

    def read_skill_file(self, run_id: str, name: str, path: str) -> str:
        return self._skill_tool(
            run_id,
            "read_skill_file",
            lambda db, run: skill_runtime.read_skill_file(
                db, self.skill_library, self.runs_dir, run, name, path
            ),
        )

    def propose_skill(
        self,
        run_id: str,
        name: str,
        description: str,
        body: str,
        files: dict[str, str],
        remove: list[str],
        level: str,
        replaces: str,
        note: str,
    ) -> str:
        threshold = self.skill_ranker().duplicate
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                raise LookupError(run_id)
            answer, detail = skill_proposals.propose(
                db,
                self.skill_library,
                run,
                name,
                description,
                body,
                files,
                remove,
                level,
                replaces,
                note,
                duplicate_threshold=threshold,
            )
        self.add_event(run_id, EventKind.MCP, "propose_skill", detail)
        return answer

    def report_status(self, run_id: str, message: str) -> None:
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            run.last_status = message
            db.commit()
        self.add_event(run_id, EventKind.MCP, "report_status", message)

    def complete_task(
        self,
        run_id: str,
        summary: str,
        verdict: Verdict = Verdict.APPROVED,
        reject_to: str = "",
    ) -> str | None:
        """Records the end of the agent's work. Returns an error for the model (and records
        nothing) when it rejects outside a stage that can reject."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return None
            target: str | None = None
            if verdict == Verdict.REJECTED:
                stage = db.get(Stage, run.stage_id) if run.stage_id else None
                if stage is None or stage.reject_to_stage_id is None:
                    return (
                        "Esta etapa no puede rechazar. Si has terminado, llama a complete_task "
                        'con verdict="approved" y cuenta en el resumen lo que no esté bien.'
                    )
                target, problem = self._reject_target(db, stage, reject_to)
                if problem:
                    return problem
            run.summary = summary
            run.verdict = verdict
            run.reject_to_stage_id = target
            db.commit()
        detail = summary if verdict == Verdict.APPROVED else f"[rechazada] {summary}"
        self.add_event(run_id, EventKind.MCP, "complete_task", detail)
        session = self.get(run_id)
        if session is not None:
            session.mark_completed()
        return None

    @staticmethod
    def _reject_target(db: Session, stage: Stage, wanted: str) -> tuple[str | None, str | None]:
        """(the stage a rejection goes back to, an error for the model). The target is None
        for the stage's default one; the error says what to call again with."""
        ids = [i for i in [stage.reject_to_stage_id, *stage.reject_extra_ids] if i]
        names = {i: (st.name if (st := db.get(Stage, i)) else "") for i in ids}
        options = ", ".join(f"«{n}»" for n in names.values())
        if not wanted:
            if len(ids) > 1:
                return (
                    None,
                    f"¿A qué etapa devuelves la tarea? Vuelve a llamar con reject_to: {options}.",
                )
            return None, None
        for stage_id, name in names.items():
            if name.casefold() == wanted.casefold():
                return (None if stage_id == stage.reject_to_stage_id else stage_id), None
        return None, f"¿Qué etapa es «{wanted}»? Opciones de reject_to: {options}."

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
                account = db.get(CliAccount, run.account_id) if run.account_id else None
                account = account or account_ops.default_for(db, cli)
                if not inbox.pending(db, run_id=run_id, kinds=(InboxKind.QUOTA,)):
                    siblings = len(account_ops.list_accounts(db, cli))
                    item = inbox.create(
                        db,
                        InboxKind.QUOTA,
                        f"{title_name(account, siblings)} se ha quedado sin cuota",
                        notice,
                        task=task,
                        run=run,
                    )
                    # Which account is held (limits.quota_pending_accounts)
                    item.command = account.id
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

    def _native_skill(self, run_id: str, name: str) -> None:
        """The CLI loaded one of the run's skills by itself (phase 17, block 4)."""
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None or not skill_runtime.mark_native(db, run, name):
                return
            db.commit()
        self.add_event(run_id, EventKind.SYSTEM, "skill_native", name)

    def _native_event(self, run_id: str, name: str, node: str, description: str) -> None:
        detail = json.dumps({"id": node, "description": description[:300]}, ensure_ascii=False)
        self.add_event(run_id, EventKind.HOOK, name, detail)

    def _record_account_status(self, account_id: str | None, effect: HookEffect) -> None:
        """The subscription windows and the identity the CLI reported for the run's account."""
        if account_id is None or not (effect.quota or effect.email or effect.plan):
            return
        try:
            with self._db() as db:
                account = db.get(CliAccount, account_id)
                if account is None:
                    return
                account_ops.record_identity(account, effect.email or "", effect.plan or "")
                changed = account_ops.record_quota(account, effect.quota)
                db.commit()
            if changed and self.on_quota_changed is not None:
                self.on_quota_changed()
        except Exception:
            log.exception("could not record the account status", account_id=account_id)

    # ------------------------------------------------------------------ CLI hooks
    def on_hook(self, run_id: str, event: str, payload: object) -> None:
        session = self.get(run_id)
        with self._db() as db:
            run = db.get(Run, run_id)
            if run is None:
                return
            cli = Cli(run.cli)
            effect = interpret(cli, event, payload)
            if event == STATUS_LINE:  # the status line: cost so far, and the account's quota
                account_id = run.account_id
                db.close()
                if effect.transcript_path:
                    self.usage.note_transcript(run_id, effect.transcript_path, own=True)
                if cli == Cli.CLAUDE:
                    self.usage.status_line(run_id, effect.cost_usd, effect.cli_version)
                self._record_account_status(account_id, effect)
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
        try:
            name = skill_runtime.native_name(cli.value, event, payload)
            if name is not None:
                self._native_skill(run_id, name)
        except Exception:
            log.exception("could not record a native skill load", run_id=run_id, hook=event)
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


def _describe(found: git_activity.Activity) -> str:
    """«2 commits, 1 rama, push»: one repository's git activity in a line."""
    parts = []
    if found.commits:
        parts.append(f"{len(found.commits)} commit(s)")
    if found.branches:
        parts.append(f"{len(found.branches)} rama(s)")
    if found.tags:
        parts.append(f"{len(found.tags)} tag(s)")
    if found.pushes:
        parts.append("push forzado" if any(p.forced for p in found.pushes) else "push")
    return ", ".join(parts)
