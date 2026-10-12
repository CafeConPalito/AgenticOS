from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from agentic_os.models.inbox import InboxKind, InboxStatus, Resolution

Answer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8_000)]


class InboxItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: InboxKind
    status: InboxStatus
    task_id: str | None
    task_code: str | None = None
    task_title: str | None = None
    run_id: str | None
    agent_id: str | None
    agent_name: str
    agent_color: str
    project_id: str | None
    project_name: str
    project_color: str
    title: str
    detail: str
    command: str | None
    options: list[str]
    response: str | None
    resolution: Resolution | None
    notified_at: datetime | None
    created_at: datetime
    resolved_at: datetime | None


class InboxSummary(BaseModel):
    pending: int
    resolved: int
    # Pending items no window has notified yet (the frontend notifies them once).
    unnotified: list[InboxItemRead]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Answer


class InboxReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=8_000)] = ""
    target_stage_id: str | None = None


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval: bool = True
    question: bool = True
    review: bool = True
    stalled: bool = True
    delivery: bool = False
    limits: bool = True
    sound: bool = True
