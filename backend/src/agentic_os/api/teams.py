"""Teams of agents (phase 10): a name, a description and the agents that belong to it."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import Agent, Team
from agentic_os.schemas.team import TeamCreate, TeamRead, TeamUpdate

router = APIRouter(tags=["teams"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(db: Session, team_id: str) -> Team:
    team = db.get(Team, team_id)
    if team is None or team.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("team")
    return team


def _members(db: Session, team_ids: list[str]) -> dict[str, list[str]]:
    rows = db.execute(
        select(Agent.team_id, Agent.id)
        .where(Agent.team_id.in_(team_ids))
        .order_by(Agent.created_at, Agent.name)
    ).all()
    members: dict[str, list[str]] = {team_id: [] for team_id in team_ids}
    for team_id, agent_id in rows:
        members[team_id].append(agent_id)
    return members


def _read_many(db: Session, teams: list[Team]) -> list[TeamRead]:
    members = _members(db, [t.id for t in teams])
    return [
        TeamRead(
            id=t.id,
            name=t.name,
            description=t.description,
            position=t.position,
            agent_ids=members[t.id],
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in teams
    ]


def _set_members(db: Session, team: Team, agent_ids: list[str]) -> None:
    wanted = list(dict.fromkeys(agent_ids))
    found = set(db.scalars(select(Agent.id).where(Agent.id.in_(wanted))))
    missing = [a for a in wanted if a not in found]
    if missing:
        raise ApiError(422, "agent_not_found", f"unknown agent {missing[0]}", "agent_ids")
    # An agent is in one team: joining this one leaves the old one.
    db.execute(update(Agent).where(Agent.team_id == team.id).values(team_id=None))
    if wanted:
        db.execute(update(Agent).where(Agent.id.in_(wanted)).values(team_id=team.id))


@router.get("/teams")
def list_teams(db: DbSession) -> list[TeamRead]:
    teams = db.scalars(
        select(Team)
        .where(Team.workspace_id == DEFAULT_WORKSPACE)
        .order_by(Team.position, Team.created_at, Team.name)
    )
    return _read_many(db, list(teams))


@router.post("/teams", status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamCreate, db: DbSession) -> TeamRead:
    last = db.scalar(select(func.max(Team.position)))
    team = Team(
        workspace_id=DEFAULT_WORKSPACE,
        name=payload.name,
        description=payload.description.strip(),
        position=0 if last is None else last + 1,
    )
    db.add(team)
    db.flush()
    _set_members(db, team, payload.agent_ids)
    db.commit()
    return _read_many(db, [team])[0]


@router.get("/teams/{team_id}")
def get_team(team_id: str, db: DbSession) -> TeamRead:
    return _read_many(db, [_get(db, team_id)])[0]


@router.patch("/teams/{team_id}")
def update_team(team_id: str, payload: TeamUpdate, db: DbSession) -> TeamRead:
    team = _get(db, team_id)
    if payload.name is not None:
        team.name = payload.name
    if payload.description is not None:
        team.description = payload.description.strip()
    if payload.agent_ids is not None:
        _set_members(db, team, payload.agent_ids)
    db.commit()
    db.refresh(team)
    return _read_many(db, [team])[0]


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: str, db: DbSession) -> None:
    """The agents of the team stay, under «Sin equipo»."""
    team = _get(db, team_id)
    db.execute(update(Agent).where(Agent.team_id == team.id).values(team_id=None))
    db.delete(team)
    db.commit()
