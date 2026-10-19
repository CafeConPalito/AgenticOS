"""Local models and engines the knowledge library can download (phase 14, block 3)."""

import shutil
import sys
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.schemas.local_models import (
    DiskUse,
    ModelRead,
    ModelsRead,
    Selection,
    SelectionRead,
    TokenRead,
    TokenWrite,
)
from agentic_os.services.localmodels import catalog, hf_token, selection, store
from agentic_os.services.localmodels.catalog import CatalogEntry
from agentic_os.services.localmodels.downloads import DownloadError, DownloadManager

router = APIRouter(tags=["local-models"])
DbSession = Annotated[Session, Depends(get_session)]


def manager(request: Request) -> DownloadManager:
    return request.app.state.models


def _entry(entry_id: str) -> CatalogEntry:
    found = catalog.entry(entry_id)
    if found is None:
        raise NotFound("model")
    return found


def _read(entry: CatalogEntry, models: DownloadManager, picked: dict) -> ModelRead:
    state = models.state(entry)
    return ModelRead(
        id=entry.id,
        kind=entry.kind,
        title=entry.title,
        license=entry.license,
        size=entry.size,
        default=entry.default,
        selected=picked.get(entry.kind) == entry.id,
        needs_account=entry.needs_account,
        available=sys.platform in entry.platforms,
        bundled=state.bundled,
        state=state.state,
        done=state.done,
        total=state.total,
        error_code=state.error_code,
        error_message=state.error_message,
    )


def _error(error: DownloadError) -> ApiError:
    status_code = 409 if error.code in ("already_downloading", "downloading", "bundled") else 422
    return ApiError(status_code, error.code, error.message)


@router.get("/local-models")
def list_models(request: Request, db: DbSession) -> ModelsRead:
    models, data_dir = manager(request), Path(request.app.state.settings.data_dir)
    picked = selection.chosen(db)
    used = store.used_bytes(data_dir)
    free = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.anchor).free
    return ModelsRead(
        models=[_read(entry, models, picked) for entry in catalog.CATALOG],
        disk=DiskUse(models=used["models"], engines=used["engines"], free=free),
    )


@router.post("/local-models/{model_id}/download", status_code=status.HTTP_202_ACCEPTED)
def download(model_id: str, request: Request, db: DbSession) -> ModelRead:
    entry = _entry(model_id)
    if sys.platform not in entry.platforms:
        raise ApiError(422, "unsupported_platform", "there is no build of it for this system")
    models = manager(request)
    if models.state(entry).state == "ready":
        raise ApiError(409, "already_installed", "that model is already downloaded")
    try:
        models.start(entry)
    except DownloadError as error:
        raise _error(error) from error
    return _read(entry, models, selection.chosen(db))


@router.post("/local-models/{model_id}/cancel")
def cancel(model_id: str, request: Request, db: DbSession) -> ModelRead:
    entry, models = _entry(model_id), manager(request)
    models.cancel(entry)
    return _read(entry, models, selection.chosen(db))


@router.delete("/local-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(model_id: str, request: Request) -> None:
    try:
        manager(request).remove(_entry(model_id))
    except DownloadError as error:
        raise _error(error) from error


# ---------------------------------------------------------------------------- settings
@router.get("/settings/local-models")
def get_selection(db: DbSession) -> SelectionRead:
    return SelectionRead(**selection.chosen(db))


@router.put("/settings/local-models")
def put_selection(payload: Selection, request: Request, db: DbSession) -> SelectionRead:
    """Chooses the model for each job sent (`null`: the default). Choosing a model that is not
    downloaded is allowed: it takes effect once it is."""
    before = selection.chosen(db)
    for kind in payload.model_fields_set:
        try:
            selection.choose(db, kind, getattr(payload, kind))
        except ValueError as error:
            raise ApiError(422, "invalid_model", str(error), kind) from error
    db.commit()
    after = selection.chosen(db)
    changed = after[catalog.EMBEDDING] != before[catalog.EMBEDDING]
    return SelectionRead(**after, reindex=changed)


@router.get("/settings/huggingface-token")
def get_token() -> TokenRead:
    token, source = hf_token.find()
    return TokenRead(configured=token is not None, source=source)


@router.put("/settings/huggingface-token")
def put_token(payload: TokenWrite) -> TokenRead:
    """Saves the token in git's credential helper, or removes it (`null`). A token that comes
    from the environment or from Hugging Face's own file is theirs: not touched."""
    if payload.token:
        hf_token.save(payload.token)
    else:
        hf_token.forget()
    token, source = hf_token.find()
    return TokenRead(configured=token is not None, source=source)
