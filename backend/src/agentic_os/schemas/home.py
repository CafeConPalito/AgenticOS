from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from agentic_os.models.agent import AgentStatus, Cli
from agentic_os.models.run import RunStatus


class AgentState(StrEnum):
    RUNNING = "running"  # a run is active
    WAITING = "waiting"  # waits for the person: a task in «Esperando humano» or a pending request
    IDLE = "idle"
    DRAFT = "draft"


class HomeSession(BaseModel):
    """A live run of the agent, or one that can be resumed."""

    run_id: str
    task_id: str | None
    task_code: str | None
    task_title: str | None
    project_id: str | None
    project_name: str
    project_color: str | None
    status: RunStatus
    resumable: bool
    started_at: datetime | None
    created_at: datetime


class HomeAgent(BaseModel):
    id: str
    name: str
    role: str
    color: str
    cli: Cli
    status: AgentStatus
    state: AgentState
    queued: int  # tasks waiting in its queue
    pending_requests: int  # pending Inbox items of the agent
    sessions: list[HomeSession]


class HomeWorker(BaseModel):
    agent_id: str
    agent_name: str
    task_code: str
    task_title: str


class HomeProject(BaseModel):
    id: str
    name: str
    color: str
    open_tasks: int
    workers: list[HomeWorker]


class HomeCounts(BaseModel):
    sessions: int  # live sessions (runs of the agents, not their subagents)
    agents_working: int
    open_tasks: int  # the Board's counter
    active_runs: int  # the Ejecuciones counter


class HomeRead(BaseModel):
    agents: list[HomeAgent]
    projects: list[HomeProject]
    counts: HomeCounts
