"""What an agent runs with right now: its own CLI, account and model, or the secondary ones
while the person has switched to them (phase 10 amendment)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from agentic_os.models import Agent, Cli, CliAccount
from agentic_os.services import accounts


@dataclass(frozen=True)
class Target:
    cli: Cli
    account: CliAccount
    model: str
    using_fallback: bool


def target_for(
    db: Session,
    agent: Agent,
    now: datetime | None = None,
    index: accounts.AccountIndex | None = None,
) -> Target:
    account = index.of(agent, now) if index else None
    account = account or accounts.of_agent(db, agent, now)
    switched = accounts.fallback_active(agent, now) and account.id == agent.fallback_account_id
    if switched:
        return Target(Cli(account.cli), account, agent.fallback_model, True)
    return Target(Cli(agent.cli), account, agent.model, False)
