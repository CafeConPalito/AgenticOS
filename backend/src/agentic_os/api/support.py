"""Help when something fails (phase 20): the logs to send, and the interface's errors."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.services import support
from agentic_os.services.proc import reveal_in_file_manager

router = APIRouter(tags=["support"])
DbSession = Annotated[Session, Depends(get_session)]
# Plain stdlib logging: its records go through the app's handlers (and the redacting filter).
frontend_log = logging.getLogger("frontend")


def logs_dir(request: Request) -> Path:
    """Where the backend writes its log: the data folder's `logs`, unless set elsewhere."""
    settings = request.app.state.settings
    if settings.log_file is not None:
        return Path(settings.log_file).parent
    return Path(settings.data_dir) / "logs"


class LogFileRead(BaseModel):
    name: str
    size: int


class LogsPreview(BaseModel):
    files: list[LogFileRead]
    total: int
    default_path: str


class BundleWrite(BaseModel):
    # Where to write the zip (the «Guardar como» of the desktop app); default: Downloads.
    path: str | None = Field(default=None, max_length=1024)


class BundleRead(BaseModel):
    path: str
    size: int
    files: list[str]
    redactions: dict[str, int]


class RevealWrite(BaseModel):
    path: str = Field(max_length=1024)


class ClientEntry(BaseModel):
    level: Literal["error", "warn"]
    message: str = Field(max_length=2000)
    source: str = Field(default="", max_length=300)
    at: str = Field(default="", max_length=40)


class ClientLog(BaseModel):
    entries: list[ClientEntry] = Field(max_length=50)


@router.get("/support/logs")
def preview_logs(request: Request) -> LogsPreview:
    files = support.log_files(logs_dir(request))
    return LogsPreview(
        files=[LogFileRead(name=f.name, size=f.size) for f in files],
        total=sum(f.size for f in files),
        default_path=str(support.default_target()),
    )


@router.post("/support/logs/bundle", status_code=status.HTTP_201_CREATED)
def bundle_logs(payload: BundleWrite, request: Request, db: DbSession) -> BundleRead:
    target = Path(payload.path) if payload.path else support.default_target()
    if target.suffix.lower() != ".zip" or not target.is_absolute():
        raise ApiError(422, "bundle_path", "an absolute path ending in .zip", "path")
    try:
        made = support.bundle(
            db, logs_dir(request), target, request.app.state.cli_catalog.cached_version
        )
    except OSError as error:
        raise ApiError(
            409, "bundle_failed", f"could not write the file: {error}", "path"
        ) from error
    return BundleRead(
        path=str(made.path), size=made.size, files=made.files, redactions=made.redactions
    )


@router.post("/support/logs/reveal", status_code=status.HTTP_204_NO_CONTENT)
def reveal_bundle(payload: RevealWrite) -> None:
    path = Path(payload.path)
    if path.suffix.lower() != ".zip" or not path.is_file():
        raise ApiError(404, "bundle_not_found", "no such file", "path")
    reveal_in_file_manager(str(path))


@router.post("/support/client-log", status_code=status.HTTP_204_NO_CONTENT)
def client_log(payload: ClientLog) -> None:
    """Errors and warnings of the interface, kept in the backend's log (the redacting filter
    applies to them as to any line)."""
    for entry in payload.entries:
        level = logging.ERROR if entry.level == "error" else logging.WARNING
        frontend_log.log(level, "%s [%s %s]", entry.message, entry.source, entry.at)
