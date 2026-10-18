"""Task state machine and agent queues (ADR 0009). Plain functions on a DB session: the
scheduler thread and the API call them; whoever calls them commits.

Queue order of an agent: its `queued` tasks by priority, then `queue_position`. A task enters at
the end of its priority (new task, next stage) or at the front (rejected, retried), so a task
that comes back does not wait for the whole queue again.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    PRIORITY_RANK,
    Agent,
    InboxKind,
    Pipeline,
    Priority,
    Project,
    Resolution,
    Stage,
    StageLink,
    Task,
    TaskEvent,
    TaskEventKind,
    TaskStatus,
    WaitingReason,
)
from agentic_os.services import inbox

# Waiting reasons with the CLI still alive (the agent asked, or its CLI asks permission):
# the task keeps its agent's slot and its folder, and resumes by itself.
LIVE_WAIT = (WaitingReason.HUMAN_REQUEST, WaitingReason.PERMISSION, WaitingReason.QUOTA)


def occupies_agent():
    """SQL condition: the task holds a live run (running, or waiting with its CLI alive)."""
    return or_(
        Task.status == TaskStatus.RUNNING,
        and_(Task.status == TaskStatus.WAITING_HUMAN, Task.waiting_reason.in_(LIVE_WAIT)),
    )


def is_live(task: Task) -> bool:
    return task.status == TaskStatus.RUNNING or (
        task.status == TaskStatus.WAITING_HUMAN and task.waiting_reason in LIVE_WAIT
    )


def resume(db: Session, task: Task) -> None:
    """A live wait is over (the question was answered, the dialog is gone): running again."""
    if task.status == TaskStatus.WAITING_HUMAN and task.waiting_reason in LIVE_WAIT:
        task.status = TaskStatus.RUNNING
        task.waiting_reason = task.waiting_detail = None


# Inbox items that only describe why a task waits: dismissed once it moves again.
ATTENTION_KINDS = (InboxKind.ATTENTION, InboxKind.STALLED)

# What «Esperando humano» means, for the Inbox (the UI has the same texts in i18n).
WAITING_TEXT = {
    WaitingReason.RUN_EXITED: "El agente terminó sin dar la tarea por acabada",
    WaitingReason.RUN_FAILED: "La ejecución falló",
    WaitingReason.RUN_STOPPED: "Se paró la ejecución",
    WaitingReason.INTERRUPTED: "Agentic OS se cerró mientras trabajaba",
    WaitingReason.MAX_REJECTIONS: "Se superó el máximo de rechazos",
    WaitingReason.LAUNCH_FAILED: "No se pudo lanzar el agente",
    WaitingReason.NO_AGENT: "La etapa no tiene agente",
    WaitingReason.WORKSPACE_FAILED: "No se pudo preparar el worktree",
    WaitingReason.QUESTION_PENDING: "Tiene una pregunta sin responder",
    WaitingReason.QUOTA: "El CLI se quedó sin cuota",
    WaitingReason.CHOOSE_BRANCH: "Hay que elegir la rama",
    WaitingReason.JOIN_CONFLICT: "Conflictos al unir las ramas",
    WaitingReason.LANES_CANCELLED: "Se cancelaron todas las ramas",
}

# Statuses from which the user can act on a task, per action.
CAN_ENQUEUE = (TaskStatus.BACKLOG,)
CAN_RETRY = (TaskStatus.WAITING_HUMAN,)
CAN_COMPLETE = (TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN)
CAN_REVIEW = (TaskStatus.REVIEW,)
CAN_CANCEL = (
    TaskStatus.DECIDING,
    TaskStatus.FORKED,
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
    """The stage after this one: where its first link goes. A pipeline with no links at all
    (rows made by hand) is a chain by position."""
    link = db.scalar(
        select(StageLink)
        .where(StageLink.from_stage_id == stage.id)
        .order_by(StageLink.position)
        .limit(1)
    )
    if link is not None:
        return db.get(Stage, link.to_stage_id)
    if db.scalar(
        select(func.count())
        .select_from(StageLink)
        .where(StageLink.pipeline_id == stage.pipeline_id)
    ):
        return None
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
    parent_task_id: str | None = None,
    preset_lanes: dict[str, list[str]] | None = None,
) -> Task:
    """With a pipeline the task starts at its first stage (and that stage's agent); without
    one it goes to `agent_id`."""
    stages = stages_of(db, project.id)
    _check_presets(db, preset_lanes or {})
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
        parent_task_id=parent_task_id,
        preset_lanes=preset_lanes or {},
    )
    db.add(task)
    db.flush()
    add_event(db, task, TaskEventKind.CREATED)
    if enqueue_now:
        requeue(db, task)
    return task


def _check_presets(db: Session, presets: dict[str, list[str]]) -> None:
    for stage_id, link_ids in presets.items():
        links = list(db.scalars(select(StageLink).where(StageLink.from_stage_id == stage_id)))
        if len(links) < 2 or not link_ids or any(i not in {x.id for x in links} for i in link_ids):
            raise ApiError(
                422, "invalid_branches", "those branches are not part of that fork", "preset_lanes"
            )


def requeue(db: Session, task: Task, front: bool = False) -> None:
    """Queues the task on the agent of its *current* stage (the pipeline may have changed since
    the task got there); with no agent there, it waits for the user."""
    if task.stage_id:
        stage = db.get(Stage, task.stage_id)
        if stage is not None:
            move_to_stage(db, task, stage, front=front)
            return
    if task.agent_id is None:
        wait_for_human(db, task, WaitingReason.NO_AGENT)
        return
    enqueue(db, task, front=front)


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
    # Back in a queue: what it was waiting for (a failure, being idle) no longer applies.
    inbox.resolve_pending(db, Resolution.DISMISSED, task_id=task.id, kinds=ATTENTION_KINDS)


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
    if reason not in (
        WaitingReason.HUMAN_REQUEST,
        WaitingReason.PERMISSION,
        WaitingReason.QUESTION_PENDING,  # its question is still in the Inbox
        WaitingReason.QUOTA,
    ):
        # Those bring their own Inbox item (the question, the approval, «Cuota agotada»).
        inbox.resolve_pending(db, Resolution.DISMISSED, task_id=task.id, kinds=ATTENTION_KINDS)
        inbox.create(
            db,
            InboxKind.ATTENTION,
            f"{task.code} · {task.title}",
            WAITING_TEXT.get(reason, str(reason)) + (f": {detail}" if detail else ""),
            task=task,
        )


def move_to_stage(db: Session, task: Task, stage: Stage, front: bool) -> None:
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
    # Nothing of a finished task waits for the person any more.
    inbox.resolve_pending(db, Resolution.DISMISSED, task_id=task.id)
    if status == TaskStatus.DONE:
        inbox.create(
            db,
            InboxKind.DELIVERY,
            f"{task.code} · {task.title}",
            last_summary(db, task) or "",
            task=task,
        )


def last_summary(db: Session, task: Task) -> str | None:
    """What the last stage of the task said it had done."""
    return db.scalar(
        select(TaskEvent.detail)
        .where(
            TaskEvent.task_id == task.id,
            TaskEvent.kind.in_(
                [TaskEventKind.STAGE_COMPLETED.value, TaskEventKind.COMPLETED_MANUALLY.value]
            ),
        )
        .order_by(TaskEvent.seq.desc())
        .limit(1)
    )


def advance(db: Session, task: Task) -> None:
    """The current stage is approved: next stage (end of its agent's queue), a fork, or done."""
    from agentic_os.services import lanes

    lanes.advance(db, task)


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
        inbox.create(db, InboxKind.REVIEW, f"{task.code} · {task.title}", summary, task=task)
        return
    advance(db, task)


@dataclass(frozen=True)
class RejectOutcome:
    back_to: Stage | None
    exceeded: bool


def stage_rejected(
    db: Session,
    task: Task,
    reason: str,
    run_id: str | None,
    target_stage_id: str | None = None,
) -> RejectOutcome:
    """The stage's agent rejected (complete_task with verdict "rejected"). A stage that can
    send the task back to several stages is told which one; the first is the default."""
    from agentic_os.services import lanes

    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    allowed = [stage.reject_to_stage_id, *stage.reject_extra_ids] if stage else []
    wanted = target_stage_id or (stage.reject_to_stage_id if stage else None)
    target = db.get(Stage, wanted) if wanted and wanted in allowed else None
    add_event(db, task, TaskEventKind.REJECTED, reason, run_id)
    if stage is None or target is None:  # the stage lost its reject target meanwhile
        wait_for_human(
            db, task, WaitingReason.RUN_EXITED, "rejected without a target stage", run_id
        )
        return RejectOutcome(None, False)
    root = lanes.root_of(db, task)  # the counter is the whole task's, lanes included
    root.rejections += 1
    pipeline = db.get(Pipeline, stage.pipeline_id)
    if pipeline is not None and root.rejections > pipeline.max_rejections:
        wait_for_human(db, task, WaitingReason.MAX_REJECTIONS, reason, run_id)
        return RejectOutcome(target, True)
    lanes.send_back(db, task, target, reason)
    return RejectOutcome(target, False)


def review(
    db: Session, task: Task, approve: bool, reason: str = "", target_stage_id: str | None = None
) -> None:
    """The user's decision on a stage that requires review."""
    from agentic_os.services import lanes

    check_status(task, CAN_REVIEW, "review")
    proposal = lanes.pending_proposal(db, task)
    if proposal is not None:  # the review is of the branches a fork chose, not of a stage
        if not approve and not reason.strip():
            raise ApiError(422, "reason_required", "a rejection needs a reason", "reason")
        lanes.review_proposal(db, task, proposal, approve, reason.strip())
        return
    if approve:
        add_event(db, task, TaskEventKind.REVIEW_APPROVED, reason)
        inbox.resolve_pending(db, Resolution.APPROVED, task_id=task.id, kinds=(InboxKind.REVIEW,))
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
    inbox.resolve_pending(
        db, Resolution.REJECTED, task_id=task.id, kinds=(InboxKind.REVIEW,), response=reason
    )
    if target is None:  # no pipeline: the same agent does it again
        requeue(db, task, front=True)
        return
    lanes.send_back(db, task, target, reason.strip())


def retry(db: Session, task: Task) -> None:
    """Back to the queue (front). After too many rejections the retry restarts the loop: the
    task goes back to the stage that has to fix it, with the counter at zero. Not while its CLI
    is alive (a question or a permission waits): that would start a second run."""
    from agentic_os.services import lanes

    check_status(task, CAN_RETRY, "retry")
    if is_live(task):
        raise ApiError(409, "task_live", "the task's agent is still running", "status")
    add_event(db, task, TaskEventKind.RETRIED)
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    forking = task.waiting_reason in (WaitingReason.CHOOSE_BRANCH, WaitingReason.LANES_CANCELLED)
    if forking and stage is not None:
        lanes.start_fork(db, task, stage)  # decide again
        return
    if task.waiting_reason == WaitingReason.JOIN_CONFLICT:
        task.status = TaskStatus.FORKED
        task.waiting_reason = task.waiting_detail = None
        lanes.try_join(db, task)
        return
    if task.waiting_reason == WaitingReason.MAX_REJECTIONS and stage is not None:
        target = db.get(Stage, stage.reject_to_stage_id) if stage.reject_to_stage_id else None
        lanes.root_of(db, task).rejections = 0
        if target is not None:
            lanes.send_back(db, task, target)
            return
    requeue(db, task, front=True)


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
    TaskEventKind.HUMAN_REQUEST,
    TaskEventKind.HUMAN_ANSWERED,
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
        TaskEventKind.HUMAN_REQUEST: "preguntó a la persona",
        TaskEventKind.HUMAN_ANSWERED: "la persona respondió",
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
