from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ModelRead(BaseModel):
    id: str
    kind: str  # embedding | ocr | vision | engine
    title: str
    license: str
    size: int  # bytes to download
    default: bool  # what is used until the user chooses
    selected: bool  # what is used now for its job (the engine has no job: always False)
    needs_account: bool
    available: bool  # false on a platform the entry has no build for
    bundled: bool  # it came inside the app: ready from the start, and not removable
    state: str  # absent | partial | downloading | ready | error
    done: int  # bytes already on disk or downloaded
    total: int
    error_code: str | None
    error_message: str | None


class DiskUse(BaseModel):
    models: int
    engines: int
    free: int  # free space on the data folder's disk


class ModelsRead(BaseModel):
    models: list[ModelRead]
    disk: DiskUse


class Selection(BaseModel):
    """Which downloaded model does each job. `null` goes back to the default."""

    model_config = ConfigDict(extra="forbid")

    embedding: str | None = None
    ocr: str | None = None
    vision: str | None = None


class SelectionRead(BaseModel):
    embedding: str | None
    ocr: str | None
    vision: str | None
    # An embedding model change makes the documents' vectors stale: they are indexed again.
    reindex: bool = False


class TokenRead(BaseModel):
    configured: bool
    source: str | None  # env | file | git


class TokenWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
