from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from agentic_os.models.project import WorkspaceMode
from agentic_os.schemas.agent import Color, Name, reject_null
from agentic_os.services.git import GitInfo

PathStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
BranchName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    path: PathStr
    color: Color | None = None
    description: str | None = None
    workspace_mode: WorkspaceMode = WorkspaceMode.DIRECT
    base_branch: BranchName | None = None
    create_folder: bool = False

    _no_nulls = field_validator("color", "description", "workspace_mode", mode="before")(
        reject_null
    )


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    path: PathStr | None = None
    color: Color | None = None
    description: str | None = None
    workspace_mode: WorkspaceMode | None = None
    base_branch: BranchName | None = None

    _no_nulls = field_validator(
        "name", "path", "color", "description", "workspace_mode", mode="before"
    )(reject_null)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str
    description: str
    path: str
    workspace_mode: WorkspaceMode
    base_branch: str | None
    created_at: datetime
    updated_at: datetime
    git: GitInfo | None = None
    folder_exists: bool = True
