from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Agent
from agentic_os.schemas.agent import AgentCreate, AgentRead, AgentTemplate, AgentUpdate
from agentic_os.services.templates import BY_ID, TEMPLATES

router = APIRouter(tags=["agents"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("agent")
    return agent


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
    return [AgentRead.model_validate(a) for a in session.scalars(query)]


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
    return AgentRead.model_validate(agent)


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, session: DbSession) -> AgentRead:
    return AgentRead.model_validate(_get(session, agent_id))


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdate, session: DbSession) -> AgentRead:
    agent = _get(session, agent_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and not changes["name"]:
        raise ApiError(422, "name_required", "name is required", "name")
    for field, value in changes.items():
        setattr(agent, field, value)
    session.commit()
    return AgentRead.model_validate(agent)


@router.post("/agents/{agent_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_agent(agent_id: str, session: DbSession) -> AgentRead:
    source = _get(session, agent_id)
    copied = AgentRead.model_validate(source).model_dump(exclude={"id", "created_at", "updated_at"})
    copied["name"] = f"{source.name} (copia)"[:80]
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, **copied)
    session.add(agent)
    session.commit()
    return AgentRead.model_validate(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, session: DbSession) -> None:
    session.delete(_get(session, agent_id))
    session.commit()
