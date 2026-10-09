from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_os import APP_NAME, __version__
from agentic_os.api import api_router
from agentic_os.config import Settings, get_settings
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import register_error_handlers
from agentic_os.logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(database_url(settings))
        upgrade_to_head(engine)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.settings = settings
        try:
            yield
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
    return app


def create_dev_app() -> FastAPI:
    """Factory for `--reload`: the app runs in a reloader child, so logging is set up here."""
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json, log_file=settings.log_file)
    return create_app(settings)
