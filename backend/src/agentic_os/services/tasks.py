"""Task state machine and agent queues (ADR 0009). Plain functions on a DB session: the
scheduler thread and the API call them; whoever calls them commits.

Queue order of an agent: its `queued` tasks by priority, then `queue_position`. A task enters at
the end of its priority (new task, next stage) or at the front (rejected, retried), so a task
that comes back does not wait for the whole queue again.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    PRIORITY_RANK,
    Agent,
    Pipeline,
    Priority,
    Project,
    Stage,
    Task,
    TaskEvent,
    TaskEventKind,
    TaskStatus,
    WaitingReason,
)

# Statuses from which the user can act on a task, per action.
CAN_ENQUEUE = (TaskStatus.BACKLOG,)
CAN_RETRY = (TaskStatus.WAITING_HUMAN,)
CAN_COMPLETE = (TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN)
CAN_REVIEW = (TaskStatus.REVIEW,)
CAN_CANCEL = (
    TaskStatus.BACKLOG,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.WAITING_HUMAN,
    TaskStatus.REVIEW,
)


def priority_rank():
    return case(*((Task.priority == p.value, rank) for p, rank in PRIORITY_RANK.items()), else_=1)


def check_status(task: Task, allowed: tuple[TaskStatus, ...], action: str) -> None:
    if task.status not in allowed:
        raise ApiError(
            409, "task_status", f"cannot {action} a task in status {task.status}", "status"
        )


# ---------------------------------------------------------------- pipeline helpers
def pipeline_of(db: Session, project_id: str) -> Pipeline | None:
    return db.scalar(select(Pipeline).where(Pipeline.project_id == project_id))


def stages_of(db: Session, project_id: str) -> list[Stage]:
    pipeline = pipeline_of(db, project_id)
    return list(pipeline.stages) if pipeline is not None else []


def next_stage(db: Session, stage: Stage) -> Stage | None:
    return db.scalar(
        select(Stage)
        .where(Stage.pipeline_id == stage.pipeline_id, Stage.position > stage.position)
        .order_by(Stage.position)
        .limit(1)
    )


# ---------------------------------------------------------------- events
def add_event(
    db: Session,
    task: Task,
    kind: TaskEventKind,
    detail: str = "",
    run_id: str | None = None,
    stage: Stage | None = None,
) -> TaskEvent:
    stage = (
        stage if stage is not None else (db.get(Stage, task.stage_id) if task.stage_id else None)
    )
    agent = db.get(Agent, task.agent_id) if task.agent_id else None
    last = db.scalar(select(func.max(TaskEvent.seq)).where(TaskEvent.task_id == task.id))
    event = TaskEvent(
        task_id=task.id,
        seq=(last or 0) + 1,
        kind=kind,
        stage_name=stage.name if stage else None,
        agent_name=agent.name if agent else None,
        run_id=run_id,
        detail=detail,
    )
    db.add(event)
    return event


# ---------------------------------------------------------------- creation and queues
def next_number(db: Session, workspace_id: str) -> int:
    current = db.scalar(select(func.max(Task.number)).where(Task.workspace_id == workspace_id))
    return (current or 0) + 1


def create_task(
    db: Session,
    project: Project,
    title: str,
    description: str = "",
    priority: Priority = Priority.NORMAL,
    agent_id: str | None = None,
    enqueue_now: bool = True,
) -> Task:
    """With a pipeline the task starts at its first stage (and that stage's agent); without
    one it goes to `agent_id`."""
    stages = stages_of(db, project.id)
    if stages:
        stage_id, agent_id = stages[0].id, stages[0].agent_id
    else:
        if agent_id is None:
            raise ApiError(
                422, "agent_required", "a project without pipeline needs an agent", "agent_id"
            )
        stage_id = None
    task = Task(
        workspace_id=project.workspace_id,
        number=next_number(db, project.workspace_id),
        project_id=project.id,
        title=title,
        description=description,
        priority=priority,
        stage_id=stage_id,
        agent_id=agent_id,
    )
    db.add(task)
    db.flush()
    add_event(db, task, TaskEventKind.CREATED)
    if enqueue_now:
        enqueue(db, task)
    return task


def enqueue(db: Session, task: Task, front: bool = False) -> None:
    """Puts the task in the queue of its agent: at the end of its priority, or at the front."""
    edge = func.min if front else func.max
    current = db.scalar(
        select(edge(Task.queue_position)).where(
            Task.agent_id == task.agent_id,
            Task.status == TaskStatus.QUEUED,
            Task.priority == task.priority,
            Task.id != task.id,
        )
    )
    if current is None:
        task.queue_position = 0
    else:
        task.queue_position = current - 1 if front else current + 1
    task.status = TaskStatus.QUEUED
    task.queued_at = utcnow()
    task.waiting_reason = task.waiting_detail = None
    add_event(db, task, TaskEventKind.QUEUED)


def queue_of(db: Session, agent_id: str) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.agent_id == agent_id, Task.status == TaskStatus.QUEUED)
            .order_by(priority_rank(), Task.queue_position, Task.queued_at)
        )
    )


def reorder(db: Session, agent_id: str, task_ids: list[str]) -> None:
    """Rewrites the positions of an agent's queue. Every queued task of the agent must be
    listed once; priorities stay as they are (positions only order within a priority)."""
    queue = queue_of(db, agent_id)
    if sorted(task_ids) != sorted(t.id for t in queue):
        raise ApiError(409, "queue_changed", "the queue changed meanwhile: reload it", "task_ids")
    by_id = {t.id: t for t in queue}
    for position, task_id in enumerate(task_ids):
        by_id[task_id].queue_position = position


def change_priority(db: Session, task: Task, priority: Priority) -> None:
    if task.priority == priority:
        return
    task.priority = priority
    if task.status == TaskStatus.QUEUED:  # it goes to the end of its new priority
        task.status = TaskStatus.BACKLOG
        enqueue(db, task)


def set_agent(db: Session, task: Task, agent_id: str) -> None:
    """Only for tasks without pipeline (with one, the stage decides) and not running."""
    if task.stage_id is not None:
        raise ApiError(409, "task_has_pipeline", "the stage decides the agent", "agent_id")
    if task.status == TaskStatus.RUNNING:
        raise ApiError(409, "task_status", "cannot reassign a running task", "agent_id")
    if task.agent_id == agent_id:
        return
    task.agent_id = agent_id
    if task.status == TaskStatus.QUEUED:
        task.status = TaskStatus.BACKLOG
        enqueue(db, task)


# ---------------------------------------------------------------- lifecycle
def mark_running(db: Session, task: Task, run_id: str) -> None:
    task.status = TaskStatus.RUNNING
    task.started_at = task.started_at or utcnow()
    add_event(db, task, TaskEventKind.STAGE_STARTED, run_id=run_id)


def wait_for_human(
    db: Session, task: Task, reason: WaitingReason, detail: str = "", run_id: str | None = None
) -> None:
    task.status = TaskStatus.WAITING_HUMAN
    task.waiting_reason = reason
    task.waiting_detail = detail or None
    add_event(db, task, TaskEventKind.WAITING_HUMAN, f"{reason}: {detail}".rstrip(": "), run_id)


def _move_to_stage(db: Session, task: Task, stage: Stage, front: bool) -> None:
    task.stage_id = stage.id
    task.agent_id = stage.agent_id
    if stage.agent_id is None:
        wait_for_human(db, task, WaitingReason.NO_AGENT, stage.name)
        return
    enqueue(db, task, front=front)


def finish(
    db: Session, task: Task, status: TaskStatus, kind: TaskEventKind, detail: str = ""
) -> None:
    task.status = status
    task.finished_at = utcnow()
    task.waiting_reason = task.waiting_detail = None
    add_event(db, task, kind, detail)


def advance(db: Session, task: Task) -> None:
    """The current stage is approved: next stage (end of its agent's queue), or done."""
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    following = next_stage(db, stage) if stage is not None else None
    if following is None:
        finish(db, task, TaskStatus.DONE, TaskEventKind.DONE)
        return
    _move_to_stage(db, task, following, front=False)


def stage_completed(
    db: Session, task: Task, summary: str, run_id: str | None, manual: bool = False
) -> None:
    """A stage ended approved (by its agent's complete_task, or by the user): review gate,
    next stage or done."""
    kind = TaskEventKind.COMPLETED_MANUALLY if manual else TaskEventKind.STAGE_COMPLETED
    add_event(db, task, kind, summary, run_id)
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    if stage is not None and stage.requires_review:
        task.status = TaskStatus.REVIEW
        return
    advance(db, task)


@dataclass(frozen=True)
class RejectOutcome:
    back_to: Stage | None
    exceeded: bool


def stage_rejected(db: Session, task: Task, reason: str, run_id: str | None) -> RejectOutcome:
    """The stage's agent rejected (complete_task with verdict "rejected")."""
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    target = db.get(Stage, stage.reject_to_stage_id) if stage and stage.reject_to_stage_id else None
    add_event(db, task, TaskEventKind.REJECTED, reason, run_id)
    if target is None:  # the stage lost its reject target meanwhile
        wait_for_human(
            db, task, WaitingReason.RUN_EXITED, "rejected without a target stage", run_id
        )
        return RejectOutcome(None, False)
    task.rejections += 1
    pipeline = db.get(Pipeline, stage.pipeline_id)
    if pipeline is not None and task.rejections > pipeline.max_rejections:
        wait_for_human(db, task, WaitingReason.MAX_REJECTIONS, reason, run_id)
        return RejectOutcome(target, True)
    _move_to_stage(db, task, target, front=True)
    return RejectOutcome(target, False)


def review(
    db: Session, task: Task, approve: bool, reason: str = "", target_stage_id: str | None = None
) -> None:
    """The user's decision on a stage that requires review."""
    check_status(task, CAN_REVIEW, "review")
    if approve:
        add_event(db, task, TaskEventKind.REVIEW_APPROVED, reason)
        advance(db, task)
        return
    if not reason.strip():
        raise ApiError(422, "reason_required", "a rejection needs a reason", "reason")
    current = db.get(Stage, task.stage_id) if task.stage_id else None
    target = current
    if target_stage_id:
        target = db.get(Stage, target_stage_id)
        if target is None or current is None or target.pipeline_id != current.pipeline_id:
            raise ApiError(
                422, "invalid_stage", "the stage is not in this pipeline", "target_stage_id"
            )
    add_event(db, task, TaskEventKind.REVIEW_REJECTED, reason.strip())
    if target is None:  # no pipeline: the same agent does it again
        enqueue(db, task, front=True)
        return
    _move_to_stage(db, task, target, front=True)


def retry(db: Session, task: Task) -> None:
    check_status(task, CAN_RETRY, "retry")
    add_event(db, task, TaskEventKind.RETRIED)
    if task.agent_id is None:
        wait_for_human(db, task, WaitingReason.NO_AGENT)
        return
    enqueue(db, task, front=True)


# ---------------------------------------------------------------- context for a run
@dataclass(frozen=True)
class TaskContext:
    code: str
    title: str
    description: str
    stage_name: str | None
    stage_index: int  # 1-based; 0 without pipeline
    stage_count: int
    can_reject: bool
    history: tuple[str, ...]  # summaries of earlier stages, oldest first
    rejection: str | None  # why the task came back to this stage, if it did
    branch: str | None


HISTORY_KINDS = (
    TaskEventKind.STAGE_COMPLETED,
    TaskEventKind.COMPLETED_MANUALLY,
    TaskEventKind.REJECTED,
    TaskEventKind.REVIEW_REJECTED,
)
HISTORY_LIMIT = 8_000


def task_context(db: Session, task: Task) -> TaskContext:
    stages = stages_of(db, task.project_id)
    stage = next((s for s in stages if s.id == task.stage_id), None)
    events = list(
        db.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task.id, TaskEvent.kind.in_([k.value for k in HISTORY_KINDS])
            )
            .order_by(TaskEvent.seq)
        )
    )
    labels = {
        TaskEventKind.STAGE_COMPLETED: "terminó",
        TaskEventKind.COMPLETED_MANUALLY: "terminó (a mano)",
        TaskEventKind.REJECTED: "rechazó",
        TaskEventKind.REVIEW_REJECTED: "rechazada en revisión",
    }
    history: list[str] = []
    size = 0
    for event in reversed(events):  # the most recent ones fit first
        who = " · ".join(x for x in (event.stage_name, event.agent_name) if x)
        line = f"- {who} {labels[TaskEventKind(event.kind)]}: {event.detail.strip()}"
        if history and size + len(line) > HISTORY_LIMIT:
            break
        history.append(line)
        size += len(line)
    last = events[-1] if events else None
    rejection = (
        last.detail.strip()
        if last is not None and last.kind in (TaskEventKind.REJECTED, TaskEventKind.REVIEW_REJECTED)
        else None
    )
    return TaskContext(
        code=task.code,
        title=task.title,
        description=task.description,
        stage_name=stage.name if stage else None,
        stage_index=(stages.index(stage) + 1) if stage else 0,
        stage_count=len(stages),
        can_reject=bool(stage and stage.reject_to_stage_id),
        history=tuple(reversed(history)),
        rejection=rejection,
        branch=task.branch,
    )


def task_prompt(task: Task) -> str:
    """The run's initial message: the first line names the task (agy only gets that line typed;
    the whole task is in its plugin rules)."""
    first = f"{task.code} · {task.title}"
    return f"{first}\n\n{task.description.strip()}" if task.description.strip() else first
