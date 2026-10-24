"""The Inbox (phase 06): what the agents need from the person. Plain functions on a DB session,
used by the RunManager (approvals, questions), the task state machine (reviews, deliveries) and
the scheduler (stalled runs). Whoever calls them commits."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import (
    NOTIFICATIONS,
    Agent,
    AppState,
    InboxItem,
    InboxKind,
    InboxStatus,
    Project,
    Resolution,
    Run,
    Task,
)

# Which kinds notify by default (Ajustes → Notificaciones, design 12).
DEFAULT_NOTIFICATIONS = {
    "approval": True,
    "question": True,  # questions and blockers
    "review": True,  # reviews and rejections between stages
    "stalled": True,
    "delivery": False,
    "limits": True,  # daily limits and «Cuota agotada» (phase 07)
    "sound": True,
}
# The setting that covers each kind.
SETTING_FOR = {
    InboxKind.APPROVAL: "approval",
    InboxKind.QUESTION: "question",
    InboxKind.BLOCKER: "question",
    InboxKind.REVIEW: "review",
    InboxKind.STALLED: "stalled",
    InboxKind.DELIVERY: "delivery",
    InboxKind.ATTENTION: "stalled",
    InboxKind.LIMIT: "limits",
    InboxKind.QUOTA: "limits",
    InboxKind.ACCOUNT: "limits",
    InboxKind.SWITCH: "limits",
    InboxKind.KNOWLEDGE: "review",  # a proposal is a review of the agents' work
    InboxKind.SKILL: "review",
    InboxKind.CONNECTION: "limits",  # like a CLI account that must log in again
}


def create(
    db: Session,
    kind: InboxKind,
    title: str,
    detail: str = "",
    *,
    task: Task | None = None,
    run: Run | None = None,
    command: str | None = None,
    options: list[str] | None = None,
    knowledge_doc_id: str | None = None,
    skill_version_id: str | None = None,
    connection_id: str | None = None,
) -> InboxItem:
    """A new pending item. Agent and project are copied from the run, else from the task."""
    item = InboxItem(
        workspace_id=DEFAULT_WORKSPACE,
        kind=kind,
        title=title.strip()[:500],
        detail=detail.strip(),
        task_id=task.id if task else (run.task_id if run else None),
        run_id=run.id if run else None,
        command=command,
        knowledge_doc_id=knowledge_doc_id,
        skill_version_id=skill_version_id,
        connection_id=connection_id,
        options=[str(o)[:80] for o in (options or []) if str(o).strip()][:8],
    )
    agent_id = task.agent_id if task is not None else None
    agent = db.get(Agent, agent_id) if agent_id else None
    if run is not None:
        item.agent_id, item.agent_name, item.agent_color = (
            run.agent_id,
            run.agent_name,
            run.agent_color,
        )
    elif agent is not None:
        item.agent_id, item.agent_name, item.agent_color = agent.id, agent.name, agent.color
    project_id = run.project_id if run else (task.project_id if task else None)
    project = db.get(Project, project_id) if project_id else None
    if project is not None:
        item.project_id, item.project_name, item.project_color = (
            project.id,
            project.name,
            project.color,
        )
    db.add(item)
    db.flush()
    return item


def resolve(
    db: Session, item: InboxItem, resolution: Resolution, response: str | None = None
) -> None:
    item.status = InboxStatus.RESOLVED
    item.resolution = resolution
    item.response = response
    item.resolved_at = utcnow()


def pending(
    db: Session,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    kinds: tuple[InboxKind, ...] = (),
) -> list[InboxItem]:
    query = select(InboxItem).where(InboxItem.status == InboxStatus.PENDING)
    if task_id is not None:
        query = query.where(InboxItem.task_id == task_id)
    if run_id is not None:
        query = query.where(InboxItem.run_id == run_id)
    if kinds:
        query = query.where(InboxItem.kind.in_([k.value for k in kinds]))
    else:
        # An agent's proposal outlives the task and the run it came from: only the person (or
        # the document going away) resolves it.
        query = query.where(
            InboxItem.kind.not_in(
                [InboxKind.KNOWLEDGE.value, InboxKind.SKILL.value, InboxKind.CONNECTION.value]
            )
        )
    return list(db.scalars(query.order_by(InboxItem.created_at)))


def resolve_pending(
    db: Session,
    resolution: Resolution,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    kinds: tuple[InboxKind, ...] = (),
    response: str | None = None,
) -> int:
    """Resolves the matching pending items (e.g. a review answered from the task page)."""
    items = pending(db, task_id=task_id, run_id=run_id, kinds=kinds)
    for item in items:
        resolve(db, item, resolution, response)
    return len(items)


def counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(InboxItem.status, func.count())
        .where(InboxItem.workspace_id == DEFAULT_WORKSPACE)
        .group_by(InboxItem.status)
    ).all()
    found = dict(rows)
    return {status.value: found.get(status.value, 0) for status in InboxStatus}


def unnotified(db: Session) -> list[InboxItem]:
    return list(
        db.scalars(
            select(InboxItem)
            .where(InboxItem.status == InboxStatus.PENDING, InboxItem.notified_at.is_(None))
            .order_by(InboxItem.created_at)
        )
    )


# ---------------------------------------------------------------- notification settings
def notification_settings(db: Session) -> dict[str, bool]:
    state = db.get(AppState, NOTIFICATIONS)
    stored: dict = {}
    if state is not None:
        try:
            stored = json.loads(state.value)
        except ValueError:
            stored = {}
    return {key: bool(stored.get(key, default)) for key, default in DEFAULT_NOTIFICATIONS.items()}


def save_notification_settings(db: Session, values: dict[str, bool]) -> dict[str, bool]:
    current = notification_settings(db) | {
        k: bool(v) for k, v in values.items() if k in DEFAULT_NOTIFICATIONS
    }
    state = db.get(AppState, NOTIFICATIONS) or AppState(key=NOTIFICATIONS)
    state.value = json.dumps(current)
    db.add(state)
    return current
