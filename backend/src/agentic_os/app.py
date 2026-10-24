import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_os import APP_NAME, __version__
from agentic_os.api import api_router
from agentic_os.api.hooks import router as hooks_router
from agentic_os.config import Settings, get_settings
from agentic_os.db.backup import backup_before_migrating
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import register_error_handlers
from agentic_os.logging_setup import configure_logging
from agentic_os.models import CliAccount
from agentic_os.services import accounts as account_ops
from agentic_os.services import housekeeping
from agentic_os.services.accounts_login import AccountLogins
from agentic_os.services.clis import CliCatalog
from agentic_os.services.decider import DecisionService
from agentic_os.services.dictation.service import DictationService
from agentic_os.services.gitx import credentials
from agentic_os.services.gitx.events import GitEvents
from agentic_os.services.gitx.jobs import JobManager
from agentic_os.services.gitx.shell import ShellSessions
from agentic_os.services.knowledge.events import KnowledgeEvents
from agentic_os.services.knowledge.service import KnowledgeService
from agentic_os.services.localmodels import hf_token
from agentic_os.services.localmodels.catalog import EMBEDDING
from agentic_os.services.localmodels.downloads import DownloadManager
from agentic_os.services.mcp_server import mount_app
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.scheduler import Scheduler
from agentic_os.services.skills.library import SkillLibrary, refresh_skill_vectors
from agentic_os.services.skills.registries.service import RegistryService
from agentic_os.services.skills.store import SkillStore
from agentic_os.services.trust import TrustCleaner, account_trust_files, agy_settings, claude_config
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.worktrees import Worktrees

log = structlog.get_logger()


class AgentGateway:
    """`/r/<token>/…`: the agent-facing MCP server, created with the RunManager in the lifespan."""

    async def __call__(self, scope, receive, send) -> None:
        gate = getattr(scope["app"].state, "mcp_gate", None)
        if gate is None:  # lifespan not started (or already shut down)
            await send({"type": "http.response.start", "status": 503, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await gate(scope, receive, send)


def check_sessions(sessions, manager: RunManager, scheduler: Scheduler) -> None:
    """At startup (slow: it runs the CLIs): which accounts are logged in. A logout shows up in
    «Te necesitan» before any task trips over it."""
    try:
        with sessions() as db:
            for account in account_ops.list_accounts(db):
                manager.probe_account(db, account)
                db.commit()
            usage_limits.sync_session_items(db)
            db.commit()
        scheduler.poke()
    except Exception:
        log.exception("could not check the accounts' sessions")


def session_checked_after_login(
    sessions, manager: RunManager, scheduler: Scheduler, account_id: str
) -> None:
    """A login terminal closed: ask the CLI who is logged in now, and let the scheduler know."""
    with sessions() as db:
        account = db.get(CliAccount, account_id)
        if account is not None:
            manager.probe_account(db, account)
            usage_limits.sync_session_items(db)
            db.commit()
    scheduler.poke()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(database_url(settings))
        backup_before_migrating(engine, Path(settings.data_dir))
        upgrade_to_head(engine)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.settings = settings
        app.state.cli_catalog = CliCatalog()
        manager = RunManager(app.state.sessionmaker, settings)
        manager.loop = asyncio.get_running_loop()
        manager.cli_version = app.state.cli_catalog.cached_version
        manager.recover()
        manager.usage.start()
        manager.usage.backfill()  # runs from before phase 07, or that ended while we were down
        app.state.run_manager = manager
        scheduler = Scheduler(app.state.sessionmaker, manager)
        trust = TrustCleaner(
            Path(settings.data_dir) / "trust-cleanup.json",
            {
                "claude": settings.claude_config_file or claude_config(),
                "agy": settings.agy_settings_file or agy_settings(),
            },
            extra_configs=lambda: account_trust_files(app.state.sessionmaker),
        )
        worktrees = Worktrees(trust)
        scheduler.prepare_workspace = worktrees.prepare
        scheduler.release_workspace = worktrees.release
        scheduler.housekeeping = lambda: (
            trust.flush(),
            scheduler.check_stalled(),
            scheduler.check_limits(force=True),
        )
        manager.usage.on_updated = lambda run_id: scheduler.check_limits()
        manager.on_run_ended = scheduler.run_ended
        deciders = DecisionService(settings.cli_command_overrides)
        deciders.on_result = scheduler.decision_ready
        scheduler.deciders = deciders
        manager.on_quota_changed = scheduler.check_limits
        manager.on_tasks_changed = scheduler.poke
        scheduler.recover()
        scheduler.probe_account = manager.probe_account
        logins = AccountLogins(settings.cli_command_overrides)
        logins.loop = asyncio.get_running_loop()
        logins.on_end = lambda account_id: session_checked_after_login(
            app.state.sessionmaker, manager, scheduler, account_id
        )
        app.state.logins = logins
        git_events = GitEvents()
        git_jobs = JobManager()
        git_jobs.listener = git_events.publish
        app.state.git_events, app.state.git_jobs = git_events, git_jobs
        git_shells = ShellSessions()
        git_shells.loop = asyncio.get_running_loop()
        git_shells.on_end = git_events.changed
        app.state.git_shells = git_shells
        knowledge_events = KnowledgeEvents()
        knowledge = KnowledgeService(
            app.state.sessionmaker,
            Path(settings.data_dir),
            knowledge_events,
            mode=settings.knowledge_processing,
            cli_overrides=settings.cli_command_overrides,
        )
        app.state.knowledge_events, app.state.knowledge = knowledge_events, knowledge
        manager.knowledge = knowledge  # the agents' search_knowledge uses its search
        skills = SkillLibrary(
            SkillStore(Path(settings.data_dir)),
            # Skills and tasks both as questions: symmetric similarity (spike S4c).
            embed=lambda texts: knowledge.embed_passages(texts, kind="query"),
            model=lambda: entry.id if (entry := knowledge.embedding_model()) else None,
        )
        app.state.skills = skills
        manager.skills = skills  # the runs' skills and use_skill
        skill_registries = RegistryService(
            Path(settings.data_dir),
            skills,
            github_token=lambda: credentials.token_for("github.com"),
        )
        app.state.skill_registries = skill_registries
        if settings.check_sessions_at_startup:  # like the session checks: never in the tests
            skill_registries.start(app.state.sessionmaker)
        # Skills are selected by their vector: a new model gives them new ones (spike S4).
        knowledge.after_reindex.append(
            lambda: refresh_skill_vectors(app.state.sessionmaker, skills)
        )
        knowledge.start()
        if knowledge.mode != "off":
            # Also warms the query worker: a run's first launch then does not wait for it.
            threading.Thread(
                target=refresh_skill_vectors,
                args=(app.state.sessionmaker, skills),
                name="skills-vectors",
                daemon=True,
            ).start()
        models = DownloadManager(
            Path(settings.data_dir),
            knowledge_events,
            token=hf_token.token,
            # A model of embeddings that arrives: the documents get indexed with it.
            on_ready=lambda entry: knowledge.reindex() if entry.kind == EMBEDDING else None,
        )
        app.state.models = models
        dictation = DictationService(app.state.sessionmaker, Path(settings.data_dir))
        app.state.dictation = dictation
        if settings.check_sessions_at_startup:
            threading.Thread(
                target=check_sessions,
                args=(app.state.sessionmaker, manager, scheduler),
                name="startup-sessions",
                daemon=True,
            ).start()
        # Leftovers of earlier crashes (phase 08): agy plugins before the scheduler can write
        # new ones; the slow rest (git, old logs) in the background.
        housekeeping.stale_agy_plugins(app.state.sessionmaker)
        threading.Thread(
            target=housekeeping.run_at_startup,
            args=(
                app.state.sessionmaker,
                Path(settings.data_dir) / "runs",
                worktrees.release,
                trust.flush,
            ),
            name="startup-cleanup",
            daemon=True,
        ).start()
        app.state.scheduler = scheduler
        app.state.mcp_gate, session_manager = mount_app(manager, manager.tokens)
        scheduler.start()
        try:
            async with session_manager.run():
                yield
        finally:
            app.state.mcp_gate = None
            logins.shutdown()
            git_jobs.shutdown()
            git_shells.shutdown()
            models.stop()
            dictation.stop()
            skill_registries.stop()
            knowledge.stop()
            # The scheduler stops first: the runs closed by the shutdown are not "stopped by the
            # user"; their tasks are found interrupted on the next start.
            scheduler.stop()
            deciders.stop()
            manager.on_run_ended = None
            try:
                await asyncio.to_thread(manager.shutdown)
                # After the runs: their final usage reads are queued while they close, and
                # the worker must be done before the engine goes away.
                await asyncio.to_thread(manager.usage.stop)
            finally:
                engine.dispose()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router)
    app.include_router(hooks_router)  # /r/<token>/hook/… before the /r mount (MCP)
    app.mount("/r", AgentGateway())
    return app


def create_dev_app() -> FastAPI:
    """Factory for `--reload`: the app runs in a reloader child, so logging is set up here."""
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json, log_file=settings.log_file)
    return create_app(settings)
