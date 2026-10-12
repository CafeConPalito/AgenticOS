from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.tasks import ManagerDep, SchedulerDep
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import InboxItem, InboxKind, InboxStatus, Resolution, Task
from agentic_os.schemas.inbox import (
    AnswerRequest,
    InboxItemRead,
    InboxReview,
    InboxSummary,
    NotificationSettings,
)
from agentic_os.services import inbox
from agentic_os.services import tasks as task_ops

router = APIRouter(tags=["inbox"])
DbSession = Annotated[Session, Depends(get_session)]


def _get(db: Session, item_id: str) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if item is None or item.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("inbox_item")
    return item


def _pending(item: InboxItem, *kinds: InboxKind) -> None:
    if item.status != InboxStatus.PENDING:
        raise ApiError(409, "inbox_resolved", "the item is already resolved", "status")
    if kinds and item.kind not in kinds:
        raise ApiError(409, "inbox_kind", f"not possible on a {item.kind} item", "kind")


def read_items(db: Session, items: list[InboxItem]) -> list[InboxItemRead]:
    task_ids = {i.task_id for i in items if i.task_id}
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids)))}
    result = []
    for item in items:
        read = InboxItemRead.model_validate(item)
        task = tasks.get(item.task_id) if item.task_id else None
        if task is not None:
            read.task_code, read.task_title = task.code, task.title
        result.append(read)
    return result


@router.get("/inbox")
def list_inbox(db: DbSession, status: InboxStatus = InboxStatus.PENDING) -> list[InboxItemRead]:
    query = (
        select(InboxItem)
        .where(InboxItem.workspace_id == DEFAULT_WORKSPACE, InboxItem.status == status)
        .order_by(
            (
                InboxItem.created_at if status == InboxStatus.PENDING else InboxItem.resolved_at
            ).desc()
        )
        .limit(300)
    )
    return read_items(db, list(db.scalars(query)))


@router.get("/inbox/summary")
def inbox_summary(db: DbSession) -> InboxSummary:
    counts = inbox.counts(db)
    return InboxSummary(
        pending=counts["pending"],
        resolved=counts["resolved"],
        unnotified=read_items(db, inbox.unnotified(db)),
    )


@router.post("/inbox/{item_id}/notified")
def mark_notified(item_id: str, db: DbSession) -> InboxItemRead:
    item = _get(db, item_id)
    item.notified_at = item.notified_at or utcnow()
    db.commit()
    return read_items(db, [item])[0]


@router.post("/inbox/{item_id}/answer")
def answer_item(
    item_id: str, payload: AnswerRequest, db: DbSession, manager: ManagerDep
) -> InboxItemRead:
    """Answers a question or a blocker: the agent gets it as a message in its terminal."""
    item = _get(db, item_id)
    _pending(item, InboxKind.QUESTION, InboxKind.BLOCKER)
    manager.answer_human(db, item, payload.text)
    db.commit()
    return read_items(db, [item])[0]


@router.post("/inbox/{item_id}/resume")
def resume_item(
    item_id: str, db: DbSession, manager: ManagerDep, scheduler: SchedulerDep
) -> InboxItemRead:
    """«Cuota agotada» → Reanudar: the task runs again and the CLI is no longer held."""
    item = _get(db, item_id)
    _pending(item, InboxKind.QUOTA)
    manager.resume_after_quota(db, item)
    db.commit()
    scheduler.poke()
    return read_items(db, [item])[0]


def _answer_permission(db: Session, manager, item: InboxItem, approve: bool) -> InboxItemRead:
    _pending(item, InboxKind.APPROVAL)
    if item.run_id is None or not manager.answer_permission(item.run_id, approve):
        # The dialog is gone (answered in the terminal, the run ended…).
        inbox.resolve(db, item, Resolution.ANSWERED_IN_TERMINAL)
        db.commit()
        raise ApiError(409, "no_permission_dialog", "the dialog is no longer waiting")
    # The session reports the dialog gone (on_permission_gone): the task resumes then.
    inbox.resolve(db, item, Resolution.APPROVED if approve else Resolution.REJECTED)
    db.commit()
    return read_items(db, [item])[0]


@router.post("/inbox/{item_id}/approve")
def approve_item(item_id: str, db: DbSession, manager: ManagerDep) -> InboxItemRead:
    return _answer_permission(db, manager, _get(db, item_id), True)


@router.post("/inbox/{item_id}/reject")
def reject_item(item_id: str, db: DbSession, manager: ManagerDep) -> InboxItemRead:
    return _answer_permission(db, manager, _get(db, item_id), False)


@router.post("/inbox/{item_id}/review")
def review_item(
    item_id: str, payload: InboxReview, db: DbSession, scheduler: SchedulerDep
) -> InboxItemRead:
    """Same as reviewing from the task page (it resolves this item)."""
    item = _get(db, item_id)
    _pending(item, InboxKind.REVIEW)
    task = db.get(Task, item.task_id) if item.task_id else None
    if task is None:
        raise NotFound("task")
    task_ops.review(db, task, payload.approve, payload.reason, payload.target_stage_id)
    if task.status == "done":
        scheduler.release_finished(db, task)
    db.commit()
    scheduler.poke()
    return read_items(db, [item])[0]


@router.post("/inbox/{item_id}/dismiss")
def dismiss_item(
    item_id: str, db: DbSession, manager: ManagerDep, scheduler: SchedulerDep
) -> InboxItemRead:
    """«Marcar como revisado» on a delivery; «Descartar» on anything else. Dismissing a
    question tells the agent to go on without the answer."""
    item = _get(db, item_id)
    _pending(item)
    if item.kind in (InboxKind.QUESTION, InboxKind.BLOCKER):
        manager.dismiss_human(db, item)
        db.commit()
        return read_items(db, [item])[0]
    if item.kind == InboxKind.QUOTA:
        # Without «Reanudar» the task must not stay waiting: it goes on, the CLI is free.
        manager.resume_after_quota(db, item, resolution=Resolution.DISMISSED, nudge=False)
        db.commit()
        scheduler.poke()
        return read_items(db, [item])[0]
    # A seen «Límite diario» is «reviewed»: it is not created again today (limits.py).
    reviewed = item.kind in (InboxKind.DELIVERY, InboxKind.LIMIT)
    inbox.resolve(db, item, Resolution.REVIEWED if reviewed else Resolution.DISMISSED)
    db.commit()
    return read_items(db, [item])[0]


# ---------------------------------------------------------------------- settings
@router.get("/settings/notifications")
def get_notification_settings(db: DbSession) -> NotificationSettings:
    return NotificationSettings(**inbox.notification_settings(db))


@router.put("/settings/notifications")
def put_notification_settings(payload: NotificationSettings, db: DbSession) -> NotificationSettings:
    values = inbox.save_notification_settings(db, payload.model_dump())
    db.commit()
    return NotificationSettings(**values)
