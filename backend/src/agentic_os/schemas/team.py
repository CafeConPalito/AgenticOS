from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: str = ""
    agent_ids: list[str] = []


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: str | None = None
    # The members: the listed agents join, the ones not listed leave (they go to «Sin equipo»).
    agent_ids: list[str] | None = None


class TeamRead(BaseModel):
    id: str
    name: str
    description: str
    position: int
    agent_ids: list[str]
    created_at: datetime
    updated_at: datetime
