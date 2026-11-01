import json
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.api.agents import _get as get_agent_row
from agentic_os.api.projects import get_project_or_404
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.errors import ApiError, NotFound
from agentic_os.models import (
    ACTIVE_STATUSES,
    Agent,
    BranchDecision,
    Project,
    Run,
    RunEvent,
    RunKind,
    Stage,
    StageLink,
    Task,
    TaskEvent,
    TaskStatus,
)
from agentic_os.schemas.task import (
    AddLaneRequest,
    AgentQueue,
    CompleteRequest,
    DecisionRead,
    DecisionRequest,
    LaneRead,
    QueueOrder,
    ReviewAction,
    ReviewRequest,
    SchedulerState,
    TaskCreate,
    TaskEventRead,
    TaskRead,
    TaskUpdate,
    TreeNode,
    WorkModeRequest,
)
from agentic_os.schemas.usage import UsageTotals
from agentic_os.services import accounts as account_ops
from agentic_os.services import lanes as lane_ops
from agentic_os.services import tasks as task_ops
from agentic_os.services.proc import open_in_file_manager
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.scheduler import Scheduler, blocked_reason
from agentic_os.services.usage import limits as usage_limits
from agentic_os.services.usage import switching
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
                Run.kind == RunKind.AGENT,
                Run.parent_run_id.is_(None),  # the task's own runs, not its subagents
                Run.status.in_([s.value for s in ACTIVE_STATUSES]),
            )
        ).all()
    )
    last_rows = db.execute(
        select(Run.task_id, Run.id, Run.created_at)
        .where(Run.task_id.in_(ids), Run.kind == RunKind.AGENT, Run.parent_run_id.is_(None))
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
    lane_rows = list(db.scalars(select(Task).where(Task.lane_of_id.in_(ids))))
    link_ids = {x.lane_link_id for x in [*tasks, *lane_rows] if x.lane_link_id}
    link_names = {
        link.id: link.name
        for link in db.scalars(select(StageLink).where(StageLink.id.in_(link_ids)))
    }
    lane_agents = {
        a.id: a
        for a in db.scalars(
            select(Agent).where(Agent.id.in_({x.agent_id for x in lane_rows if x.agent_id}))
        )
    }
    stage_names = {
        st.id: st.name
        for st in db.scalars(
            select(Stage).where(Stage.id.in_({x.stage_id for x in lane_rows if x.stage_id}))
        )
    }
    lanes_by_parent: dict[str, list[LaneRead]] = {}
    for lane in sorted(lane_rows, key=lambda x: x.created_at):
        lane_agent = lane_agents.get(lane.agent_id) if lane.agent_id else None
        lanes_by_parent.setdefault(lane.lane_of_id or "", []).append(
            LaneRead(
                id=lane.id,
                code=lane.code,
                lane_key=lane.lane_key,
                name=link_names.get(lane.lane_link_id or "", lane.lane_key),
                status=lane.status,
                stage_id=lane.stage_id,
                stage_name=stage_names.get(lane.stage_id or ""),
                agent_id=lane_agent.id if lane_agent else None,
                agent_name=lane_agent.name if lane_agent else None,
                agent_color=lane_agent.color if lane_agent else None,
                waiting_reason=lane.waiting_reason,
                link_id=lane.lane_link_id,
                fork_stage_id=lane.fork_stage_id,
            )
        )
    # Queued tasks of an account over its daily limit, out of quota or logged out wait
    # (phases 07 and 10).
    gates: dict[str, str | None] = {}
    index = None
    deciding: set[str] = set()
    if any(t.status == TaskStatus.QUEUED for t in tasks):
        gates = usage_limits.blocked_all(db)
        index = account_ops.AccountIndex(db)
        deciding = switching.decisions_pending(db)
    # Phase 24: a lane works the way its root does.
    modes: dict[str, tuple[str | None, str | None, str | None]] = {}
    for task in tasks:
        root = lane_ops.root_of(db, task) if task.lane_of_id else task
        modes[task.id] = (root.work_mode, root.work_mode_reason, root.spec_path)
    result = []
    for task in tasks:
        project = projects[task.project_id]
        project_stages = stages.get(task.project_id, [])
        stage = next((s for s in project_stages if s.id == task.stage_id), None)
        ended_at = next((s for s in project_stages if s.id == task.exit_stage_id), None)
        agent = agents.get(task.agent_id) if task.agent_id else None
        blocked = blocked_by = None
        if task.status == TaskStatus.QUEUED:
            account = index.of(agent) if agent and index else None
            gate = gates.get(account.id) if account else None
            decision = "decision" if agent is not None and agent.id in deciding else None
            blocked = blocked_reason(db, task, project) or decision or gate
            if gate is not None and blocked == gate and account is not None:
                blocked_by = account_ops.display_name(account)
        shown, phase = lane_ops.view_status(db, task)
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
                status=shown,
                phase=phase,
                lane_of_id=task.lane_of_id,
                lane_name=link_names.get(task.lane_link_id or ""),
                fork_stage_id=task.fork_stage_id,
                lanes=lanes_by_parent.get(task.id, []),
                stage_exit_condition=stage.exit_condition if stage else None,
                exit_stage_id=task.exit_stage_id,
                exit_stage_name=ended_at.name if ended_at else None,
                work_mode=modes.get(task.id, (None, None, None))[0],
                work_mode_reason=modes.get(task.id, (None, None, None))[1],
                spec_path=modes.get(task.id, (None, None, None))[2],
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
                blocked_by=blocked_by,
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


DEFAULT_SEARCH = 20
MAX_SEARCH = 50


def _fold(text: str) -> str:
    """Lower case without accents: «Diseño» finds «diseno»."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _search(tasks: list[Task], q: str) -> list[Task]:
    """Tasks whose title contains `q`; for `T-n` or `n`, the task with that number comes first."""
    needle = _fold(q.strip())
    match = re.fullmatch(r"(?:t-)?(\d+)", needle)
    number = int(match.group(1)) if match else None
    exact = [t for t in tasks if t.number == number]
    titled = [t for t in tasks if t.number != number and needle in _fold(t.title)]
    return exact + titled


# ---------------------------------------------------------------------- tasks
@router.get("/tasks")
def list_tasks(
    db: DbSession,
    project_id: str | None = None,
    agent_id: str | None = None,
    status_: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    parent_task_id: str | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_SEARCH)] = None,
    lanes: Annotated[Literal["include"] | None, Query()] = None,
) -> list[TaskRead]:
    """The lanes of a forked task are tasks too, but they only show on their own with
    `?lanes=include` or when asking for an agent's tasks."""
    query = select(Task).where(Task.workspace_id == DEFAULT_WORKSPACE)
    if lanes != "include" and not agent_id:
        query = query.where(Task.lane_of_id.is_(None))
    if parent_task_id:
        query = query.where(Task.parent_task_id == parent_task_id)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if agent_id:
        query = query.where(Task.agent_id == agent_id)
    if status_:
        query = query.where(Task.status.in_([s.value for s in status_]))
    query = query.order_by(Task.number.desc())
    tasks = list(db.scalars(query))
    if q and q.strip():
        tasks = _search(tasks, q)[: limit or DEFAULT_SEARCH]
    elif limit:
        tasks = tasks[:limit]
    return read_tasks(db, tasks)


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
        preset_lanes=payload.preset_lanes,
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
    for lane in lane_ops.descendants(db, task):  # the lanes read their task's text and priority
        lane.title, lane.description = task.title, task.description
        task_ops.change_priority(db, lane, task.priority)
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
        db.scalars(
            select(Run)
            .where(Run.task_id == task_id, Run.kind == RunKind.AGENT)
            .order_by(Run.created_at.desc())
        )
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


@router.get("/tasks/{task_id}/decisions")
def task_decisions(task_id: str, db: DbSession) -> list[DecisionRead]:
    _get(db, task_id)
    rows = db.scalars(
        select(BranchDecision).where(BranchDecision.task_id == task_id).order_by(BranchDecision.at)
    )
    return [DecisionRead.model_validate(r) for r in rows]


# ---------------------------------------------------------------------- actions
@router.post("/tasks/{task_id}/decision")
def decide_branches(
    task_id: str, payload: DecisionRequest, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    """The person picks the branches of a task that waits at a fork."""
    task = _get(db, task_id)
    lane_ops.decide(db, task, payload.chosen)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.put("/tasks/{task_id}/work-mode")
def change_work_mode(
    task_id: str, payload: WorkModeRequest, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    """Phase 24: the person changes the mode; the task goes back to its first stage."""
    task = _get(db, task_id)
    task_ops.change_work_mode(db, task, payload.mode)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.post("/tasks/{task_id}/continue")
def continue_task(task_id: str, db: DbSession, scheduler: SchedulerDep) -> TaskRead:
    """Phase 24: «Seguir con el pipeline» for a task that ended at an exit."""
    task = _get(db, task_id)
    lane_ops.continue_after_exit(db, task)
    db.commit()
    scheduler.poke()
    return read_task(db, task)


@router.post("/tasks/{task_id}/lanes", status_code=status.HTTP_201_CREATED)
def add_lane(
    task_id: str, payload: AddLaneRequest, db: DbSession, scheduler: SchedulerDep
) -> TaskRead:
    """Adds a branch to a task that already forked: it starts now and the join waits for it."""
    task = _get(db, task_id)
    lane = lane_ops.add_lane(db, task, payload.link_id)
    db.commit()
    scheduler.poke()
    return read_task(db, lane)


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
    if task.status == TaskStatus.DONE:  # retrying a join can finish the task
        scheduler.release_finished(db, task)
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
    if task.waiting_reason in lane_ops.FORK_WAITS:
        raise ApiError(409, "task_status", "the task waits at a fork: choose or retry", "status")
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
    """Cancels the task and, if it forked, its lanes. Cancelling a lane leaves the others: the
    join stops waiting for it."""
    task = _get(db, task_id)
    task_ops.check_status(task, task_ops.CAN_CANCEL, "cancel")
    if task.lane_of_id is not None:
        cancelled = lane_ops.cancel_lane(db, task)
    else:
        cancelled = lane_ops.cancel_tree(db, task)
    runs = {t.id: _active_run(db, t) for t in cancelled}
    # Committed before the runs are stopped: their end (on the scheduler thread) must find the
    # tasks cancelled, and the API must not hold the SQLite write lock meanwhile.
    db.commit()
    for item in cancelled:
        run = runs[item.id]
        if run is None or not manager.stop(run.id):
            scheduler.release_finished(db, item)
        # else: its workspace is released when the run has ended (Scheduler._handle_run_end)
    db.commit()
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
