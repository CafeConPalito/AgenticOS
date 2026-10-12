import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.api.agents import _get as get_agent_row
from agentic_os.api.projects import get_project_or_404, open_in_file_manager
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    ACTIVE_STATUSES,
    Agent,
    Cli,
    Project,
    Run,
    RunEvent,
    Stage,
    Task,
    TaskEvent,
    TaskEventKind,
    TaskStatus,
)
from agentic_os.schemas.task import (
    AgentQueue,
    CompleteRequest,
    QueueOrder,
    ReviewAction,
    ReviewRequest,
    SchedulerState,
    TaskCreate,
    TaskEventRead,
    TaskRead,
    TaskUpdate,
    TreeNode,
)
from agentic_os.schemas.usage import UsageTotals
from agentic_os.services import tasks as task_ops
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.scheduler import Scheduler, blocked_reason
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.usage.stats import task_usage

router = APIRouter(tags=["tasks"])
DbSession = Annotated[Session, Depends(get_session)]


def get_scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler


def get_manager(request: Request) -> RunManager:
    return request.app.state.run_manager


SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]
ManagerDep = Annotated[RunManager, Depends(get_manager)]


def _get(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.workspace_id != DEFAULT_WORKSPACE:
        raise NotFound("task")
    return task


def read_tasks(db: Session, tasks: list[Task]) -> list[TaskRead]:
    """TaskRead for many tasks with a handful of queries (lists, board, queues)."""
    if not tasks:
        return []
    ids = [t.id for t in tasks]
    project_ids = {t.project_id for t in tasks}
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(project_ids)))}
    agent_ids = {t.agent_id for t in tasks if t.agent_id}
    agents = {a.id: a for a in db.scalars(select(Agent).where(Agent.id.in_(agent_ids)))}
    stages: dict[str, list[Stage]] = {}
    for project_id in projects:
        stages[project_id] = task_ops.stages_of(db, project_id)
    active = dict(
        db.execute(
            select(Run.task_id, Run.id).where(
                Run.task_id.in_(ids),
                Run.parent_run_id.is_(None),  # the task's own runs, not its subagents
                Run.status.in_([s.value for s in ACTIVE_STATUSES]),
            )
        ).all()
    )
    last_rows = db.execute(
        select(Run.task_id, Run.id, Run.created_at)
        .where(Run.task_id.in_(ids), Run.parent_run_id.is_(None))
        .order_by(Run.created_at)
    ).all()
    last = {task_id: run_id for task_id, run_id, _ in last_rows}
    parents = {
        t.id: t.code
        for t in db.scalars(
            select(Task).where(Task.id.in_({t.parent_task_id for t in tasks if t.parent_task_id}))
        )
    }
    subtask_rows = db.execute(
        select(Task.parent_task_id, Task.status, func.count())
        .where(Task.parent_task_id.in_(ids))
        .group_by(Task.parent_task_id, Task.status)
    ).all()
    subtasks: dict[str, list[int]] = {}
    for parent_id, sub_status, count in subtask_rows:
        done_total = subtasks.setdefault(parent_id, [0, 0])
        done_total[1] += count
        if sub_status == TaskStatus.DONE:
            done_total[0] += count

    usage = task_usage(db, ids)
    # Queued tasks of a CLI over its daily limit or out of quota wait (phase 07).
    gates: dict[str, str | None] = {}
    if any(t.status == TaskStatus.QUEUED for t in tasks):
        gates = {cli.value: usage_limits.blocked(db, cli) for cli in Cli}
    result = []
    for task in tasks:
        project = projects[task.project_id]
        project_stages = stages.get(task.project_id, [])
        stage = next((s for s in project_stages if s.id == task.stage_id), None)
        agent = agents.get(task.agent_id) if task.agent_id else None
        blocked = None
        if task.status == TaskStatus.QUEUED:
            gate = gates.get(agent.cli) if agent else None
            blocked = blocked_reason(db, task, project) or (f"{gate}_{agent.cli}" if gate else None)
        result.append(
            TaskRead(
                id=task.id,
                code=task.code,
                number=task.number,
                project_id=project.id,
                project_name=project.name,
                project_color=project.color,
                title=task.title,
                description=task.description,
                priority=task.priority,
                status=task.status,
                stage_id=task.stage_id,
                stage_name=stage.name if stage else None,
                stage_index=(project_stages.index(stage) + 1) if stage else 0,
                stage_count=len(project_stages),
                requires_review=bool(stage and stage.requires_review),
                agent_id=task.agent_id,
                agent_name=agent.name if agent else None,
                agent_color=agent.color if agent else None,
                queue_position=task.queue_position,
                rejections=task.rejections,
                waiting_reason=task.waiting_reason,
                waiting_detail=task.waiting_detail,
                worktree_path=task.worktree_path,
                branch=task.branch,
                blocked=blocked,
                active_run_id=active.get(task.id),
                last_run_id=last.get(task.id),
                queued_at=task.queued_at,
                started_at=task.started_at,
                finished_at=task.finished_at,
                created_at=task.created_at,
                updated_at=task.updated_at,
                parent_task_id=task.parent_task_id,
                parent_code=parents.get(task.parent_task_id) if task.parent_task_id else None,
                subtasks_done=subtasks.get(task.id, [0, 0])[0],
                subtasks_total=subtasks.get(task.id, [0, 0])[1],
                usage=usage.get(task.id, UsageTotals()),
            )
        )
    return result


def read_task(db: Session, task: Task) -> TaskRead:
    return read_tasks(db, [task])[0]


# ---------------------------------------------------------------------- tasks
@router.get("/tasks")
def list_tasks(
    db: DbSession,
    project_id: str | None = None,
    agent_id: str | None = None,
    status_: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    parent_task_id: str | None = None,
) -> list[TaskRead]:
    query = select(Task).where(Task.workspace_id == DEFAULT_WORKSPACE)
    if parent_task_id:
        query = query.where(Task.parent_task_id == parent_task_id)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if agent_id:
        query = query.where(Task.agent_id == agent_id)
    if status_:
        query = query.where(Task.status.in_([s.value for s in status_]))
    query = query.order_by(Task.number.desc())
    return read_tasks(db, list(db.scalars(query)))


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: DbSession, scheduler: SchedulerDep) -> TaskRead:
    project = get_project_or_404(db, payload.project_id)
    if payload.agent_id is not None:
        get_agent_row(db, payload.agent_id)
    task = task_ops.create_task(
        db,
        project,
        payload.title,
        payload.description,
        payload.priority,
        payload.agent_id,
        enqueue_now=payload.enqueue,
    )
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: DbSession) -> TaskRead:
    return read_task(db, _get(db, task_id))


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str, payload: TaskUpdate, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    task = _get(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        task.title = changes["title"]
    if "description" in changes:
        task.description = changes["description"]
    if "priority" in changes:
        task_ops.change_priority(db, task, changes["priority"])
    if "agent_id" in changes:
        get_agent_row(db, changes["agent_id"])
        task_ops.set_agent(db, task, changes["agent_id"])
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: DbSession, scheduler: SchedulerDep) -> None:
    """Only finished tasks or tasks in the backlog: anything else is cancelled first. A
    worktree whose removal failed earlier gets another try (the row is its only record)."""
    task = _get(db, task_id)
    if task.status not in (TaskStatus.BACKLOG, TaskStatus.DONE, TaskStatus.CANCELLED):
        raise ApiError(409, "task_status", "cancel the task before deleting it", "status")
    scheduler.release_finished(db, task)
    db.delete(task)
    db.commit()


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str, db: DbSession) -> list[TaskEventRead]:
    _get(db, task_id)
    query = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq)
    return [TaskEventRead.model_validate(e) for e in db.scalars(query)]


@router.get("/tasks/{task_id}/tree")
def task_tree(task_id: str, db: DbSession) -> list[TreeNode]:
    """The task's runs (one per stage and retry, newest first), each with its subagents of
    Agentic OS (runs) and the CLI's native subagents (from the hooks, ADR 0010)."""
    _get(db, task_id)
    runs = list(
        db.scalars(select(Run).where(Run.task_id == task_id).order_by(Run.created_at.desc()))
    )
    stages = {
        s.id: s.name
        for s in db.scalars(select(Stage).where(Stage.id.in_({r.stage_id for r in runs})))
    }
    events = list(
        db.scalars(
            select(RunEvent)
            .where(
                RunEvent.run_id.in_([r.id for r in runs]),
                RunEvent.name.in_(["subagent_start", "subagent_stop"]),
            )
            .order_by(RunEvent.at)
        )
    )

    def natives(run: Run) -> list[TreeNode]:
        nodes: dict[str, TreeNode] = {}
        for event in events:
            if event.run_id != run.id:
                continue
            try:
                data = json.loads(event.detail)
            except ValueError:
                continue
            if event.name == "subagent_start":
                nodes[data["id"]] = TreeNode(
                    kind="native",
                    id=data["id"],
                    label=data.get("description") or "Subagente",
                    status="running",
                    started_at=event.at,
                )
            elif data.get("id") in nodes:
                nodes[data["id"]].status, nodes[data["id"]].ended_at = "done", event.at
        if run.status not in [s.value for s in ACTIVE_STATUSES]:
            for node in nodes.values():  # agy never says when its subagents end
                if node.status == "running":
                    node.status, node.ended_at = "done", run.ended_at
        return list(nodes.values())

    def node(run: Run) -> TreeNode:
        children = [node(child) for child in runs[::-1] if child.parent_run_id == run.id]
        return TreeNode(
            kind="run",
            id=run.id,
            label=run.agent_name,
            color=run.agent_color,
            stage_name=stages.get(run.stage_id) if run.stage_id else None,
            status=run.status,
            started_at=run.started_at,
            ended_at=run.ended_at,
            children=children + natives(run),
        )

    return [node(run) for run in runs if run.parent_run_id is None]


# ---------------------------------------------------------------------- actions
@router.post("/tasks/{task_id}/enqueue")
def enqueue_task(task_id: str, db: DbSession, scheduler: SchedulerDep) -> TaskRead:
    task = _get(db, task_id)
    task_ops.check_status(task, task_ops.CAN_ENQUEUE, "enqueue")
    task_ops.requeue(db, task)  # its current stage's agent, or «Esperando humano» if none
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.post("/tasks/{task_id}/open-worktree", status_code=status.HTTP_204_NO_CONTENT)
def open_worktree(task_id: str, db: DbSession) -> None:
    task = _get(db, task_id)
    if not task.worktree_path or not Path(task.worktree_path).is_dir():
        raise ApiError(409, "no_worktree", "the task has no worktree", "worktree_path")
    open_in_file_manager(task.worktree_path)


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: str, db: DbSession, scheduler: SchedulerDep) -> TaskRead:
    task = _get(db, task_id)
    task_ops.retry(db, task)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


def _active_run(db: Session, task: Task) -> Run | None:
    """The task's own live run (never one of its subagents)."""
    return db.scalar(
        select(Run).where(
            Run.task_id == task.id,
            Run.parent_run_id.is_(None),
            Run.status.in_([s.value for s in ACTIVE_STATUSES]),
        )
    )


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    payload: CompleteRequest,
    db: DbSession,
    scheduler: SchedulerDep,
    manager: ManagerDep,
) -> TaskRead:
    """«Dar por terminada»: the stage counts as approved with the user's summary. A live run
    is closed first; the task moves on when it has ended."""
    task = _get(db, task_id)
    task_ops.check_status(task, task_ops.CAN_COMPLETE, "complete")
    run = _active_run(db, task)
    if run is not None and manager.get(run.id) is not None:
        # Tied to this run: if it ends on its own first, the summary is not applied elsewhere.
        scheduler.complete_manually(run.id, payload.summary)
        if not manager.stop(run.id):
            scheduler.discard_manual(run.id)
            raise ApiError(409, "task_status", "the run has just ended: reload the task", "status")
        return read_task(db, task)
    task_ops.stage_completed(db, task, payload.summary, None, manual=True)
    if task.status == TaskStatus.DONE:
        scheduler.release_finished(db, task)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.post("/tasks/{task_id}/review")
def review_task(
    task_id: str, payload: ReviewRequest, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    task = _get(db, task_id)
    task_ops.review(
        db, task, payload.action == ReviewAction.APPROVE, payload.reason, payload.target_stage_id
    )
    if task.status == TaskStatus.DONE:
        scheduler.release_finished(db, task)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str, db: DbSession, scheduler: SchedulerDep, manager: ManagerDep
) -> TaskRead:
    task = _get(db, task_id)
    task_ops.check_status(task, task_ops.CAN_CANCEL, "cancel")
    run = _active_run(db, task)
    task_ops.finish(db, task, TaskStatus.CANCELLED, TaskEventKind.CANCELLED)
    # Committed before the run is stopped: its end (on the scheduler thread) must find the task
    # cancelled, and the API must not hold the SQLite write lock meanwhile.
    db.commit()
    if run is None or not manager.stop(run.id):
        scheduler.release_finished(db, task)
        db.commit()
    # else: its workspace is released when the run has ended (Scheduler._handle_run_end)
    scheduler.poke()
    return read_task(db, task)


# ---------------------------------------------------------------------- queues
def _queue(db: Session, agent_id: str) -> AgentQueue:
    running = list(
        db.scalars(
            select(Task)
            .where(Task.agent_id == agent_id, Task.status == TaskStatus.RUNNING)
            .order_by(Task.started_at)
        )
    )
    return AgentQueue(
        agent_id=agent_id,
        running=read_tasks(db, running),
        queued=read_tasks(db, task_ops.queue_of(db, agent_id)),
    )


@router.get("/agents/{agent_id}/queue")
def get_queue(agent_id: str, db: DbSession) -> AgentQueue:
    get_agent_row(db, agent_id)
    return _queue(db, agent_id)


@router.put("/agents/{agent_id}/queue")
def reorder_queue(
    agent_id: str, payload: QueueOrder, db: DbSession, scheduler: SchedulerDep
) -> AgentQueue:
    get_agent_row(db, agent_id)
    task_ops.reorder(db, agent_id, payload.task_ids)
    db.commit()
    scheduler.poke()
    return _queue(db, agent_id)


# ---------------------------------------------------------------------- scheduler
def _scheduler_state(db: Session, scheduler: Scheduler) -> SchedulerState:
    counts = dict(
        db.execute(
            select(Task.status, func.count())
            .where(Task.workspace_id == DEFAULT_WORKSPACE)
            .group_by(Task.status)
        ).all()
    )
    return SchedulerState(
        paused=scheduler.paused,
        queued=counts.get(TaskStatus.QUEUED, 0),
        running=counts.get(TaskStatus.RUNNING, 0),
        waiting_human=counts.get(TaskStatus.WAITING_HUMAN, 0),
        review=counts.get(TaskStatus.REVIEW, 0),
    )


@router.get("/scheduler")
def scheduler_state(db: DbSession, scheduler: SchedulerDep) -> SchedulerState:
    return _scheduler_state(db, scheduler)


@router.post("/scheduler/pause")
def pause_scheduler(db: DbSession, scheduler: SchedulerDep) -> SchedulerState:
    scheduler.set_paused(True)
    return _scheduler_state(db, scheduler)


@router.post("/scheduler/resume")
def resume_scheduler(db: DbSession, scheduler: SchedulerDep) -> SchedulerState:
    scheduler.set_paused(False)
    return _scheduler_state(db, scheduler)
