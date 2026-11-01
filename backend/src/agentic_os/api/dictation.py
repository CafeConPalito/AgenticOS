"""Dictation (phase 16): voice to text, on this machine."""

import contextlib
from dataclasses import asdict
from typing import Annotated

import anyio.to_thread
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.errors import ApiError
from agentic_os.schemas.dictation import (
    DictationSettingsRead,
    DictationSettingsWrite,
    DictationStatusRead,
    TranscriptRead,
)
from agentic_os.services.dictation import audio, config
from agentic_os.services.dictation.audio import DictationError
from agentic_os.services.dictation.service import DictationService

router = APIRouter(tags=["dictation"])
DbSession = Annotated[Session, Depends(get_session)]


def service(request: Request) -> DictationService:
    return request.app.state.dictation


def _api(error: DictationError) -> ApiError:
    return ApiError(error.status, error.code, error.message)


@router.post("/dictation/transcribe")
async def transcribe(request: Request, partial: bool = False) -> TranscriptRead:
    """The body is the WAV itself (16 kHz, mono, 16 bit): no multipart, nothing on disk.
    `partial` (phase 23): the text so far while the person speaks; 409 when the engine is busy."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > audio.MAX_BYTES:
        raise ApiError(413, "too_large", "the recording is too big")
    wav = await request.body()
    try:
        # A worker thread: the API keeps answering while the engine works.
        result = await anyio.to_thread.run_sync(service(request).transcribe, wav, partial)
    except DictationError as error:
        raise _api(error) from error
    return TranscriptRead(text=result.text, seconds=result.seconds, model=result.model)


@router.post("/dictation/warmup", status_code=status.HTTP_202_ACCEPTED)
async def warm_up(request: Request) -> None:
    """The person started to talk: load the model while they do."""
    with contextlib.suppress(DictationError):  # the transcription will say what is missing
        await anyio.to_thread.run_sync(service(request).warm_up)


@router.get("/dictation/status")
def get_status(request: Request) -> DictationStatusRead:
    return DictationStatusRead(**asdict(service(request).status()))


@router.get("/settings/dictation")
def get_settings(db: DbSession) -> DictationSettingsRead:
    return DictationSettingsRead(**asdict(config.load(db)))


@router.put("/settings/dictation")
def put_settings(payload: DictationSettingsWrite, db: DbSession) -> DictationSettingsRead:
    values = payload.model_dump(exclude_unset=True)
    saved = config.save(db, {k: v for k, v in values.items() if v is not None})
    db.commit()
    return DictationSettingsRead(**asdict(saved))
