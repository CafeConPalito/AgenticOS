from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agentic_os.models.agent import Cli
from agentic_os.models.run import Activity, EventKind, RunStatus, Verdict
from agentic_os.schemas.usage import RunUsage

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    project_id: str
    prompt: Prompt


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str | None
    project_id: str | None
    agent_name: str
    agent_color: str
    project_name: str
    cli: Cli
    model: str
    prompt: str
    cwd: str
    status: RunStatus
    activity: Activity
    error: str | None
    cli_session_id: str | None
    exit_code: int | None
    cols: int
    rows: int
    started_at: datetime | None
    ended_at: datetime | None
    summary: str | None
    last_status: str | None
    mcp_connected_at: datetime | None
    # The task (and stage) a scheduled run works on; null for a manual run.
    task_id: str | None
    stage_id: str | None
    verdict: Verdict | None
    parent_run_id: str | None = None
    # «Reanudar sesión» (phase 08): the run this one continues, the one that continued it,
    # and whether it can be resumed now.
    resumed_from_id: str | None = None
    resumed_by_id: str | None = None
    resumable: bool = False
    log_purged: bool = False
    # The CLI account it ran with (phase 10): the account's current name while it exists, the
    # copy taken at launch after it was removed.
    account_id: str | None = None
    account_label: str = ""
    task_code: str | None = None
    stage_name: str | None = None
    created_at: datetime
    updated_at: datetime
    # Live state, only while the run has a session in this backend.
    controller: str | None = None
    viewers: int = 0
    usage: RunUsage = Field(default_factory=RunUsage)
    # Set when a run is launched by hand with an account that is held: "limit_reached" (daily
    # limit), "quota_reached" or "session_reached" (logged out).
    warning: str | None = None


class ControlAction(StrEnum):
    TAKE = "take"
    RELEASE = "release"


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ControlAction
    client_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class PermissionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool


class RunEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    at: datetime
    kind: EventKind
    name: str
    detail: str
