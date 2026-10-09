from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_os import APP_NAME, __version__
from agentic_os.api import api_router
from agentic_os.config import Settings, get_settings
from agentic_os.logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=APP_NAME, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


def create_dev_app() -> FastAPI:
    """Factory for `--reload`: the app runs in a reloader child, so logging is set up here."""
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json, log_file=settings.log_file)
    return create_app(settings)
