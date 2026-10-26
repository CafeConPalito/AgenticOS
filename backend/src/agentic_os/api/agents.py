from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    Agent,
    AgentStatus,
    Cli,
    CliAccount,
    Proposal,
    ProposalStatus,
    Task,
    TaskStatus,
    Team,
    WaitingReason,
)
from agentic_os.schemas.agent import (
    AgentCreate,
    AgentDuplicate,
    AgentRead,
    AgentTemplate,
    AgentUpdate,
)
from agentic_os.services import accounts, proposals
from agentic_os.services.knowledge import docs as knowledge_docs
from agentic_os.services.tasks import wait_for_human
from agentic_os.services.templates import BY_ID, TEMPLATES

router = APIRouter(tags=["agents"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("agent")
    return agent


def _pending_proposal(session: Session, agent: Agent) -> Proposal | None:
    """The pending proposal that created this draft, if any (phase 19)."""
    if agent.status != AgentStatus.DRAFT or not agent.proposal_id:
        return None
    proposal = session.get(Proposal, agent.proposal_id)
    return proposal if proposal and proposal.status == ProposalStatus.PENDING else None


def _check_links(session: Session, cli: str, team_id: str | None, account_id: str | None) -> None:
    """The team and the account an agent points to must exist, and the account must be one of
    the agent's CLI."""
    if team_id and session.get(Team, team_id) is None:
        raise ApiError(422, "team_not_found", "the team does not exist", "team_id")
    if account_id:
        account = session.get(CliAccount, account_id)
        if account is None:
            raise ApiError(422, "account_not_found", "the account does not exist", "account_id")
        if account.cli != cli:
            raise ApiError(
                422, "account_cli_mismatch", "the account is of another CLI", "account_id"
            )


def _check_fallback(session: Session, agent: Agent | None, values: dict) -> None:
    """The secondary account must exist and differ from the main one (an agent with the same
    account on both sides has nothing to switch to). The main account is the explicit one or, if
    none, the default account of the agent's CLI."""
    account_id = values.get("fallback_account_id")
    if not account_id:
        return
    account = session.get(CliAccount, account_id)
    if account is None:
        raise ApiError(
            422, "account_not_found", "the account does not exist", "fallback_account_id"
        )
    cli = str(values.get("cli", agent.cli if agent else Cli.CLAUDE))
    main_id = values.get("account_id", agent.account_id if agent else None)
    main = session.get(CliAccount, main_id) if main_id else accounts.default_for(session, Cli(cli))
    if main is not None and main.id == account.id:
        raise ApiError(
            422,
            "fallback_same_account",
            "the secondary account is the main one",
            "fallback_account_id",
        )


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
        read.using_fallback = bool(
            agent.using_fallback_until and agent.using_fallback_until > utcnow()
        )
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
        .where(Agent.workspace_id == DEFAULT_WORKSPACE, Agent.archived_at.is_(None))
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
    cli = str(values.get("cli") or Cli.CLAUDE)
    _check_links(session, cli, values.get("team_id"), values.get("account_id"))
    values["fallback_account_id"] = values.get("fallback_account_id") or None
    _check_fallback(session, None, values)
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
    # Changing the CLI leaves the old CLI's account behind (unless a new one was sent).
    if changes.get("cli", agent.cli) != agent.cli and "account_id" not in changes:
        changes["account_id"] = None
    # Checked before assigning: a wrong id would fail the flush with a foreign key error.
    _check_links(
        session,
        str(changes.get("cli", agent.cli)),
        changes.get("team_id", agent.team_id),
        changes.get("account_id", agent.account_id),
    )
    if "fallback_account_id" in changes:
        # Radix selects emit "" for «none».
        changes["fallback_account_id"] = changes["fallback_account_id"] or None
    _check_fallback(session, agent, changes)
    # Phase 19: a draft of a pending proposal becomes active by approving the proposal (its
    # skills, documents and Inbox item go with it), not by switching its status.
    if changes.get("status") == AgentStatus.ACTIVE and _pending_proposal(session, agent):
        raise ApiError(409, "pending_proposal", "approve the agent's proposal instead", "status")
    # Phase 19: the History tab lists which fields were edited by hand.
    proposals.record_hand_edit(
        session, agent, [f for f, value in changes.items() if getattr(agent, f) != value]
    )
    for field, value in changes.items():
        setattr(agent, field, value)
    if not agent.fallback_account_id:
        # Without a secondary there is nothing to run on or to ask about.
        agent.fallback_model = ""
        agent.using_fallback_until = None
        agent.switch_decided_until = None
    session.commit()
    return _read(session, agent)


@router.post("/agents/{agent_id}/fallback/clear")
def clear_fallback(agent_id: str, session: DbSession) -> AgentRead:
    """Back to the main CLI before the window resets. Queued tasks follow; a running one ends
    with the CLI it started with."""
    agent = _get(session, agent_id)
    agent.using_fallback_until = None
    session.commit()
    return _read(session, agent)


@router.post("/agents/{agent_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_agent(
    agent_id: str, session: DbSession, payload: AgentDuplicate | None = None
) -> AgentRead:
    """Copies an agent. The UI sends the localized name for the copy."""
    source = _get(session, agent_id)
    copied = AgentRead.model_validate(source).model_dump(
        exclude={
            "id",
            "created_at",
            "updated_at",
            "queued_count",
            "running_count",
            "using_fallback",
        }
    )
    copied["name"] = payload.name if payload and payload.name else f"{source.name} (2)"[:80]
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, **copied)
    session.add(agent)
    session.commit()
    return _read(session, agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, session: DbSession, request: Request) -> None:
    """An agent working on a task cannot be deleted; its queued tasks are left without agent
    (they wait for the user)."""
    agent = _get(session, agent_id)
    if _counts(session, [agent.id]).get((agent.id, TaskStatus.RUNNING)):
        raise ApiError(409, "agent_busy", "the agent is working on a task", "id")
    # A draft deleted by hand rejects its proposal (its Inbox item and skills go too).
    pending = _pending_proposal(session, agent)
    if pending is not None:
        proposals.reject(session, request.app.state.run_manager.skill_library, pending)
        if session.get(Agent, agent_id) is None:
            session.commit()
            return
    queued = session.scalars(
        select(Task).where(Task.agent_id == agent.id, Task.status == TaskStatus.QUEUED)
    )
    for task in queued:
        wait_for_human(session, task, WaitingReason.NO_AGENT, agent.name)
    session.flush()
    knowledge_docs.remove_owned(
        session,
        Path(request.app.state.settings.data_dir) / "knowledge" / "images",
        agent_id=agent.id,
    )
    session.delete(agent)
    session.commit()
