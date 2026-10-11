from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from agentic_os.models.memory import AuthorKind

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


class NoteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: NoteText


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_kind: AuthorKind
    author_name: str
    agent_id: str | None
    text: str
    created_at: datetime
    updated_at: datetime


class MemoryRead(BaseModel):
    notes: list[NoteRead]
    size: int  # characters of the rendered memory
    limit: int  # what the agents see; above it the oldest notes are left out
