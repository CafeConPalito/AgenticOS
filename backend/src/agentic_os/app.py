import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_os import APP_NAME, __version__
from agentic_os.api import api_router
from agentic_os.api.hooks import router as hooks_router
from agentic_os.config import Settings, get_settings
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import register_error_handlers
from agentic_os.logging_setup import configure_logging
from agentic_os.services.clis import CliCatalog
from agentic_os.services.mcp_server import mount_app
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.scheduler import Scheduler
from agentic_os.services.trust import TrustCleaner, agy_settings, claude_config
from agentic_os.services.worktrees import Worktrees


class AgentGateway:
    """`/r/<token>/…`: the agent-facing MCP server, created with the RunManager in the lifespan."""

    async def __call__(self, scope, receive, send) -> None:
        gate = getattr(scope["app"].state, "mcp_gate", None)
        if gate is None:  # lifespan not started (or already shut down)
            await send({"type": "http.response.start", "status": 503, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await gate(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(database_url(settings))
        upgrade_to_head(engine)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.settings = settings
        app.state.cli_catalog = CliCatalog()
        manager = RunManager(app.state.sessionmaker, settings)
        manager.loop = asyncio.get_running_loop()
        manager.recover()
        app.state.run_manager = manager
        scheduler = Scheduler(app.state.sessionmaker, manager)
        trust = TrustCleaner(
            Path(settings.data_dir) / "trust-cleanup.json",
            {
                "claude": settings.claude_config_file or claude_config(),
                "agy": settings.agy_settings_file or agy_settings(),
            },
        )
        worktrees = Worktrees(trust)
        scheduler.prepare_workspace = worktrees.prepare
        scheduler.release_workspace = worktrees.release
        scheduler.housekeeping = trust.flush
        manager.on_run_ended = scheduler.run_ended
        scheduler.recover()
        app.state.scheduler = scheduler
        app.state.mcp_gate, session_manager = mount_app(manager, manager.tokens)
        scheduler.start()
        try:
            async with session_manager.run():
                yield
        finally:
            app.state.mcp_gate = None
            # The scheduler stops first: the runs closed by the shutdown are not "stopped by the
            # user"; their tasks are found interrupted on the next start.
            scheduler.stop()
            manager.on_run_ended = None
            try:
                await asyncio.to_thread(manager.shutdown)
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
