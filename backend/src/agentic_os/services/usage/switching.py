"""The secondary CLI of an agent (phase 10 amendment, ADR 0014).

When the subscription window of the account an agent runs with reaches the threshold (90 % by
default) and the agent has a secondary CLI, the person gets one «switch» Inbox item per agent:
switch to the secondary until that window resets, or stay. Until the person answers, the agent's
queued tasks wait (`blocked = "decision"`); a running task ends with the CLI it has.

The agent is back on its main CLI by itself when the window resets (`using_fallback_until`
passes), or earlier if the person clears it. Plain functions on a DB session; whoever calls
them commits.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    AgentStatus,
    AppState,
    CliAccount,
    InboxItem,
    InboxKind,
    InboxStatus,
    Resolution,
)
from agentic_os.models.app_state import SWITCH_THRESHOLD
from agentic_os.services import accounts as account_ops
from agentic_os.services import inbox
from agentic_os.services.usage import limits

DEFAULT_THRESHOLD = 90
MIN_THRESHOLD = 50
MAX_THRESHOLD = 100
# When the CLI reports no reset time, a switch lasts as long as the shortest window.
FALLBACK_HOURS = 5

SWITCH = "switch"
STAY = "stay"


# ---------------------------------------------------------------------- threshold
def threshold(db: Session) -> int:
    row = db.get(AppState, SWITCH_THRESHOLD)
    try:
        value = int(row.value) if row is not None else DEFAULT_THRESHOLD
    except ValueError:
        return DEFAULT_THRESHOLD
    return value if MIN_THRESHOLD <= value <= MAX_THRESHOLD else DEFAULT_THRESHOLD


def set_threshold(db: Session, value: int) -> None:
    if not MIN_THRESHOLD <= value <= MAX_THRESHOLD:
        raise ApiError(422, "invalid_threshold", "the threshold is out of range", "threshold")
    row = db.get(AppState, SWITCH_THRESHOLD) or AppState(key=SWITCH_THRESHOLD)
    row.value = str(value)
    db.add(row)


# ---------------------------------------------------------------------- detection
def _window(account: CliAccount | None, limit: int, now: datetime):
    """The fullest window of the account if it reached the threshold, else None."""
    if account is None:
        return None
    fullest = account_ops.highest_quota(account, now)
    return fullest if fullest is not None and fullest.used_pct >= limit else None


def secondary_problem(
    db: Session, agent: Agent, gates: dict[str, str | None], limit: int, now: datetime
) -> str | None:
    """Why the agent cannot switch to its secondary now, or None if it can."""
    secondary = db.get(CliAccount, agent.fallback_account_id) if agent.fallback_account_id else None
    if secondary is None:
        return "missing"
    gate = gates.get(secondary.id)
    if gate is not None:
        return gate
    if _window(secondary, limit, now) is not None:
        return "threshold"
    return None


def _explain(problem: str | None, secondary_name: str, limit: int) -> str:
    if problem is None:
        return ""
    reasons = {
        "session": f"la sesión de {secondary_name} está cerrada",
        "quota": f"{secondary_name} también ha agotado su cuota",
        "limit": f"{secondary_name} ha alcanzado su límite diario",
        "threshold": f"{secondary_name} también está por encima del {limit} %",
        "missing": "ya no hay un CLI secundario configurado",
    }
    return f" No se ofrece cambiar: {reasons.get(problem, problem)}."


def pending_for(db: Session) -> dict[str, InboxItem]:
    """The pending «switch» item of each agent."""
    return {
        item.agent_id: item
        for item in inbox.pending(db, kinds=(InboxKind.SWITCH,))
        if item.agent_id
    }


def decisions_pending(db: Session) -> set[str]:
    """The agents whose queued tasks wait for the person's choice: there is an item and the
    switch is on offer (without an offer there is nothing to decide)."""
    return {agent_id for agent_id, item in pending_for(db).items() if item.options}


def sync_switch_items(db: Session, now: datetime | None = None) -> bool:
    """Creates the «switch» items of the agents whose account is about to run out and resolves
    the ones that no longer apply. True if a decision stopped pending (the scheduler can start
    the agent's tasks)."""
    now = now or utcnow()
    limit = threshold(db)
    index = account_ops.AccountIndex(db)
    gates = limits.blocked_all(db)
    pending = pending_for(db)
    freed = False
    agents = {
        a.id: a
        for a in db.scalars(
            select(Agent).where(
                Agent.status == AgentStatus.ACTIVE, Agent.fallback_account_id.is_not(None)
            )
        )
    }
    for agent_id, item in list(pending.items()):  # the agent is gone or has no secondary now
        if agent_id not in agents:
            inbox.resolve(db, item, Resolution.DISMISSED)
            freed = freed or bool(item.options)
            del pending[agent_id]
    for agent in agents.values():
        if agent.using_fallback_until and agent.using_fallback_until <= now:
            agent.using_fallback_until = None  # back on the main CLI
        item = pending.get(agent.id)
        on_secondary = account_ops.fallback_active(agent, now)
        window = None if on_secondary else _window(index.of(agent, now), limit, now)
        decided = bool(agent.switch_decided_until and agent.switch_decided_until > now)
        if window is None or decided:
            if item is not None:
                inbox.resolve(db, item, Resolution.DISMISSED)
                freed = freed or bool(item.options)
            continue
        problem = secondary_problem(db, agent, gates, limit, now)
        if item is not None and bool(item.options) == (problem is None):
            continue  # already up to date
        if item is not None:  # the secondary became (un)usable: say it again
            inbox.resolve(db, item, Resolution.DISMISSED)
            freed = freed or bool(item.options)
        _create(db, agent, index, window, problem, limit)
    return freed


def _create(db: Session, agent: Agent, index, window, problem: str | None, limit: int) -> None:
    main = index.of(agent)
    secondary = index.accounts.get(agent.fallback_account_id or "")
    main_name = account_ops.display_name(main) if main else agent.cli
    secondary_name = account_ops.display_name(secondary) if secondary else "el secundario"
    options = []
    if problem is None:
        options = [f"Cambiar a {secondary_name}", f"Seguir con {main_name}"]
    resets = window.resets_at.astimezone().strftime("%d/%m a las %H:%M")
    detail = (
        f"{main_name} va por el {round(window.used_pct)} % de su ventana "
        f"({window.id.replace('_', ' ')}), que se reinicia el {resets}. "
        "Las tareas en cola de este agente esperan tu decisión; la que está en marcha "
        "termina con el CLI actual." + _explain(problem, secondary_name, limit)
    )
    item = inbox.create(
        db,
        InboxKind.SWITCH,
        f"{agent.name} está a punto de agotar la cuota de {main_name}",
        detail,
        command=agent.id,
        options=options,
    )
    item.agent_id, item.agent_name, item.agent_color = agent.id, agent.name, agent.color


# ---------------------------------------------------------------------- answer
def answer(db: Session, item: InboxItem, choice: str, now: datetime | None = None) -> None:
    """The person's choice. Both end at the reset of the window that was about to run out."""
    now = now or utcnow()
    if choice not in (SWITCH, STAY):
        raise ApiError(422, "invalid_choice", "choose «switch» or «stay»", "choice")
    agent = db.get(Agent, item.agent_id) if item.agent_id else None
    if agent is None or item.status != InboxStatus.PENDING:
        raise ApiError(409, "switch_not_pending", "this request no longer applies")
    main = account_ops.of_agent(db, agent, now)
    window = account_ops.highest_quota(main, now)
    until = window.resets_at if window else now + timedelta(hours=FALLBACK_HOURS)
    if choice == SWITCH:
        problem = secondary_problem(db, agent, limits.blocked_all(db), threshold(db), now)
        if not item.options or problem is not None:
            raise ApiError(409, "switch_unavailable", "the secondary CLI cannot be used now")
        agent.using_fallback_until = until
        agent.switch_decided_until = None
    else:
        agent.switch_decided_until = until
    inbox.resolve(db, item, Resolution.ANSWERED, response=choice)
