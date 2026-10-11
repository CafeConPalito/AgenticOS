from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Agent, Task, TaskStatus, WaitingReason
from agentic_os.schemas.agent import (
    AgentCreate,
    AgentDuplicate,
    AgentRead,
    AgentTemplate,
    AgentUpdate,
)
from agentic_os.services.tasks import wait_for_human
from agentic_os.services.templates import BY_ID, TEMPLATES

router = APIRouter(tags=["agents"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("agent")
    return agent


def _counts(session: Session, agent_ids: list[str]) -> dict[tuple[str, str], int]:
    rows = session.execute(
        select(Task.agent_id, Task.status, func.count())
        .where(
            Task.agent_id.in_(agent_ids),
            Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
        )
        .group_by(Task.agent_id, Task.status)
    ).all()
    return {(agent_id, status): count for agent_id, status, count in rows}


def _read_many(session: Session, agents: list[Agent]) -> list[AgentRead]:
    counts = _counts(session, [a.id for a in agents])
    result = []
    for agent in agents:
        read = AgentRead.model_validate(agent)
        read.queued_count = counts.get((agent.id, TaskStatus.QUEUED), 0)
        read.running_count = counts.get((agent.id, TaskStatus.RUNNING), 0)
        result.append(read)
    return result


def _read(session: Session, agent: Agent) -> AgentRead:
    return _read_many(session, [agent])[0]


@router.get("/agent-templates")
def list_templates() -> list[AgentTemplate]:
    return TEMPLATES


@router.get("/agents")
def list_agents(session: DbSession) -> list[AgentRead]:
    query = (
        select(Agent)
        .where(Agent.workspace_id == DEFAULT_WORKSPACE)
        .order_by(Agent.created_at, Agent.name)
    )
    return _read_many(session, list(session.scalars(query)))


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, session: DbSession) -> AgentRead:
    values: dict = {}
    if payload.template:
        template = BY_ID.get(payload.template)
        if template is None:
            raise ApiError(422, "unknown_template", "unknown template", "template")
        values = template.model_dump(exclude={"id"})
        values["template"] = template.id
    values.update(payload.model_dump(exclude_unset=True, exclude={"template"}))
    if not values.get("name"):
        raise ApiError(422, "name_required", "name is required", "name")
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, **values)
    session.add(agent)
    session.commit()
    return _read(session, agent)


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, session: DbSession) -> AgentRead:
    return _read(session, _get(session, agent_id))


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdate, session: DbSession) -> AgentRead:
    agent = _get(session, agent_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and not changes["name"]:
        raise ApiError(422, "name_required", "name is required", "name")
    for field, value in changes.items():
        setattr(agent, field, value)
    session.commit()
    return _read(session, agent)


@router.post("/agents/{agent_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_agent(
    agent_id: str, session: DbSession, payload: AgentDuplicate | None = None
) -> AgentRead:
    """Copies an agent. The UI sends the localized name for the copy."""
    source = _get(session, agent_id)
    copied = AgentRead.model_validate(source).model_dump(
        exclude={"id", "created_at", "updated_at", "queued_count", "running_count"}
    )
    copied["name"] = payload.name if payload and payload.name else f"{source.name} (2)"[:80]
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, **copied)
    session.add(agent)
    session.commit()
    return _read(session, agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, session: DbSession) -> None:
    """An agent working on a task cannot be deleted; its queued tasks are left without agent
    (they wait for the user)."""
    agent = _get(session, agent_id)
    if _counts(session, [agent.id]).get((agent.id, TaskStatus.RUNNING)):
        raise ApiError(409, "agent_busy", "the agent is working on a task", "id")
    queued = session.scalars(
        select(Task).where(Task.agent_id == agent.id, Task.status == TaskStatus.QUEUED)
    )
    for task in queued:
        wait_for_human(session, task, WaitingReason.NO_AGENT, agent.name)
    session.flush()
    session.delete(agent)
    session.commit()
