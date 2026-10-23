from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class DictationSettingsRead(BaseModel):
    enabled: bool
    language: str  # "auto" or an ISO code
    shortcut: str  # held to dictate, e.g. "Ctrl+Space"
    max_seconds: int
    vocabulary: list[str]


class DictationSettingsWrite(BaseModel):
    """Only the sent fields change. Out-of-range values are refused, not clamped."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    language: str | None = Field(default=None, pattern=r"^(auto|[a-z]{2,3})$")
    shortcut: str | None = Field(default=None, min_length=1, max_length=40)
    max_seconds: int | None = Field(default=None, ge=30, le=900)
    vocabulary: list[Term] | None = Field(default=None, max_length=200)


class DictationStatusRead(BaseModel):
    enabled: bool
    ready: bool  # a dictation can start now
    reason: str | None  # disabled | no_model | engine_missing
    model: str | None
    state: str  # stopped | ready | busy
    queued: int


class TranscriptRead(BaseModel):
    text: str
    seconds: float
    model: str
