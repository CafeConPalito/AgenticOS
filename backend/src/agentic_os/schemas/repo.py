from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from agentic_os.models.repo import PullMode
from agentic_os.schemas.agent import Name
from agentic_os.services.git import GitInfo

PathStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
BranchName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RepoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    path: str
    rel_path: str | None
    base_branch: str | None
    participates: bool
    linked: bool
    missing: bool
    position: int
    pull_mode: PullMode
    forge: str | None
    git: GitInfo | None = None


class RepoLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: PathStr
    name: Name | None = None


class RepoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    base_branch: BranchName | None = None
    participates: bool | None = None
    pull_mode: PullMode | None = None
    forge: Annotated[str, StringConstraints(pattern="^(github|gitlab)$")] | None = None
