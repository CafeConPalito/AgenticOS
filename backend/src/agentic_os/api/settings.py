"""Settings not about agents or projects: data folder (phase 08), appearance (phase 20)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agentic_os.config import home_dir, read_pointer
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.schemas.appearance import Appearance, StoredAppearance
from agentic_os.services import appearance, datadir
from agentic_os.services.proc import open_in_file_manager

router = APIRouter(tags=["settings"])
DbSession = Annotated[Session, Depends(get_session)]

SIZE_TTL = 60.0
_sizes: dict[str, tuple[float, datadir.Usage]] = {}


class DataDirRead(BaseModel):
    path: str
    is_default: bool
    database_bytes: int
    sessions_bytes: int
    logs_bytes: int
    knowledge_bytes: int
    models_bytes: int  # downloaded models and engines
    skills_bytes: int  # the skill library and its versions (phase 17)
    total_bytes: int
    # The last move that failed (the data stayed where it was).
    last_error: str | None = None


class DataDirMove(BaseModel):
    to: str


class MoveAccepted(BaseModel):
    to: str
    # False: the backend cannot restart by itself (development); restart it to finish.
    restarting: bool


def forget_sizes() -> None:
    """After something freed space (log cleanup): the next read measures again."""
    _sizes.clear()


def _usage(path: Path, fresh: bool = False) -> datadir.Usage:
    key = str(path)
    cached = _sizes.get(key)
    if cached and not fresh and time.monotonic() - cached[0] < SIZE_TTL:
        return cached[1]
    usage = datadir.disk_usage(path)
    _sizes[key] = (time.monotonic(), usage)
    return usage


@router.get("/settings/data-dir")
def get_data_dir(request: Request, refresh: bool = False) -> DataDirRead:
    path = Path(request.app.state.settings.data_dir)
    usage = _usage(path, refresh)
    error = read_pointer().get("last_error")
    return DataDirRead(
        path=str(path),
        is_default=datadir.same(path, home_dir()),
        database_bytes=usage.database,
        sessions_bytes=usage.sessions,
        logs_bytes=usage.logs,
        knowledge_bytes=usage.knowledge,
        models_bytes=usage.models,
        skills_bytes=usage.skills,
        total_bytes=usage.total,
        last_error=error if isinstance(error, str) else None,
    )


@router.post("/settings/data-dir/open", status_code=status.HTTP_204_NO_CONTENT)
def open_data_dir(request: Request) -> None:
    open_in_file_manager(str(request.app.state.settings.data_dir))


@router.post("/settings/data-dir/move", status_code=status.HTTP_202_ACCEPTED)
def move_data_dir(
    payload: DataDirMove, request: Request, background: BackgroundTasks
) -> MoveAccepted:
    """Records the move and restarts the backend, which moves the data before opening it."""
    # Nothing may start between this check and the restart: the scheduler stops first.
    scheduler = request.app.state.scheduler
    scheduler.stop()
    try:
        if request.app.state.run_manager.live_ids():
            raise ApiError(409, "runs_active", "stop the running agents first")
        target = datadir.request_move(Path(request.app.state.settings.data_dir), payload.to)
    except Exception:
        scheduler.start()
        raise
    restart = getattr(request.app.state, "request_restart", None)
    if restart is not None:
        background.add_task(restart)  # after the response is sent
    else:
        scheduler.start()  # development: the move waits for a manual restart
    return MoveAccepted(to=str(target), restarting=restart is not None)


@router.get("/settings/appearance")
def get_appearance(db: DbSession) -> StoredAppearance:
    """The chosen theme and the custom themes (phases 20 and 22)."""
    return appearance.load(db)


@router.put("/settings/appearance")
def put_appearance(payload: Appearance, db: DbSession) -> StoredAppearance:
    """Replaces the whole document; the theme references are checked by the schema."""
    saved = appearance.save(db, payload)
    db.commit()
    return saved
