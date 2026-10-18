"""Forks, lanes and joins (phase 13, ADR 0020).

A task that reaches a stage with several links *forks*: the branches taken become **lanes**,
tasks of their own (children of the one that forked, same number) that go through the stages of
their branch with the queues, runs, reviews and workspaces every task already has. The task
that forked waits (`forked`) until all its lanes have arrived at the join, then goes on from
there. Lanes nest: a lane that reaches a fork is the parent of its own lanes.

Plain functions on a DB session, like `tasks`; whoever calls them commits.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.db.base import utcnow
from agentic_os.errors import ApiError
from agentic_os.models import (
    FINISHED_TASK_STATUSES,
    BranchDecision,
    DecisionBy,
    Pipeline,
    Project,
    Resolution,
    Stage,
    StageLink,
    Task,
    TaskEventKind,
    TaskStatus,
    WaitingReason,
    WorkspaceMode,
)
from agentic_os.services import inbox
from agentic_os.services import tasks as task_ops
from agentic_os.services.pipeline_graph import Graph

# Waiting reasons of a task that has forked (or is about to): only choosing or retrying helps.
FORK_WAITS = (
    WaitingReason.CHOOSE_BRANCH,
    WaitingReason.JOIN_CONFLICT,
    WaitingReason.LANES_CANCELLED,
)

# A lane in one of these is working or waiting for someone: the fork is not over.
IDLE_LANE = (TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.BACKLOG)

# Who picks the branches when they are not all fixed. Set by the decider service (block 3);
# without it the task waits for the person. Receives the task at its fork stage, the fork's
# links that need a decision and the ids of the «always» ones.
DecisionHook = Callable[[Session, Task, Stage, list[StageLink], list[str]], None]
request_decision: DecisionHook | None = None

# Brings the git branches of the lanes together before the task goes on (block 4). Returns
# why it could not (conflicts), or None.
JoinHook = Callable[[Session, Task, list[Task]], str | None]
integrate_lanes: JoinHook | None = None


# ----------------------------------------------------------------------------- the graph
def pipeline_graph(db: Session, task: Task) -> tuple[Pipeline, Graph] | None:
    from agentic_os.services import pipelines

    pipeline = task_ops.pipeline_of(db, task.project_id)
    if pipeline is None:
        return None
    graph = pipelines.graph_of(pipeline)
    graph.validate()  # fills the forks, joins and paths
    return pipeline, graph


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:30] or "rama"


def root_of(db: Session, task: Task) -> Task:
    while task.lane_of_id is not None:
        parent = db.get(Task, task.lane_of_id)
        if parent is None:
            break
        task = parent
    return task


def lanes_of(db: Session, parent: Task, fork_stage_id: str | None = None) -> list[Task]:
    """The lanes a task started, in the order of their branches."""
    query = (
        select(Task)
        .outerjoin(StageLink, StageLink.id == Task.lane_link_id)
        .where(Task.lane_of_id == parent.id)
        .order_by(StageLink.position, Task.created_at)
    )
    if fork_stage_id is not None:
        query = query.where(Task.fork_stage_id == fork_stage_id)
    return list(db.scalars(query))


def descendants(db: Session, task: Task) -> list[Task]:
    found: list[Task] = []
    for lane in lanes_of(db, task):
        found.append(lane)
        found += descendants(db, lane)
    return found


def view_status(db: Session, task: Task) -> tuple[str, str | None]:
    """(status, phase) as the person sees it. A task that forked has no state of its own: it
    shows the most pressing one of its lanes; `phase` says it is deciding or has lanes."""
    if task.status not in (TaskStatus.DECIDING, TaskStatus.FORKED):
        return task.status, None
    phase = "deciding" if task.status == TaskStatus.DECIDING else "forked"
    if task.status == TaskStatus.DECIDING:
        return TaskStatus.RUNNING, phase
    active = [
        t.status
        for t in descendants(db, task)
        if t.status not in (*FINISHED_TASK_STATUSES, TaskStatus.DECIDING, TaskStatus.FORKED)
    ]
    for status in (
        TaskStatus.WAITING_HUMAN,
        TaskStatus.REVIEW,
        TaskStatus.RUNNING,
        TaskStatus.QUEUED,
        TaskStatus.BACKLOG,
    ):
        if status in active:
            return status, phase
    return TaskStatus.RUNNING, phase  # every lane arrived: the join is happening


# ------------------------------------------------------------------------------ moving on
def advance(db: Session, task: Task) -> None:
    """The task's current stage is approved: the next stage, a fork, the end of its lane, or
    done."""
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    found = pipeline_graph(db, task) if stage is not None else None
    if stage is None or found is None:
        _end(db, task)
        return
    _, graph = found
    outs = graph.out.get(stage.id, [])
    if len(outs) > 1:
        start_fork(db, task, stage)
        return
    following = outs[0].dst if outs else None
    if task.lane_of_id is not None:
        fork = graph.join_of(task.fork_stage_id) if task.fork_stage_id else None
        if following is None or following == fork:
            arrive(db, task)
            return
    if following is None:
        _end(db, task)
        return
    nxt = db.get(Stage, following)
    assert nxt is not None
    task_ops.move_to_stage(db, task, nxt, front=False)


def _end(db: Session, task: Task) -> None:
    if task.lane_of_id is not None:
        arrive(db, task)
    else:
        task_ops.finish(db, task, TaskStatus.DONE, TaskEventKind.DONE)


def arrive(db: Session, lane: Task) -> None:
    """A lane reached the join (or its end): done, and its parent may go on."""
    summary = task_ops.last_summary(db, lane) or ""
    lane.status = TaskStatus.DONE
    lane.finished_at = utcnow()
    lane.waiting_reason = lane.waiting_detail = None
    task_ops.add_event(db, lane, TaskEventKind.LANE_FINISHED, summary)
    inbox.resolve_pending(db, Resolution.DISMISSED, task_id=lane.id)
    parent = db.get(Task, lane.lane_of_id) if lane.lane_of_id else None
    if parent is None:
        return
    task_ops.add_event(db, parent, TaskEventKind.LANE_FINISHED, f"{lane.lane_key}: {summary}")
    _start_next_in_line(db, parent)
    try_join(db, parent)


def try_join(db: Session, parent: Task) -> None:
    """When every lane of the fork has arrived (or been cancelled), the task goes on."""
    if parent.status != TaskStatus.FORKED or parent.stage_id is None:
        return
    lanes = lanes_of(db, parent, parent.stage_id)
    live = [lane for lane in lanes if lane.status != TaskStatus.CANCELLED]
    if not live:
        task_ops.wait_for_human(db, parent, WaitingReason.LANES_CANCELLED)
        return
    if any(lane.status != TaskStatus.DONE for lane in live):
        return
    if integrate_lanes is not None:
        problem = integrate_lanes(db, parent, live)
        if problem is not None:
            task_ops.wait_for_human(db, parent, WaitingReason.JOIN_CONFLICT, problem)
            return
    found = pipeline_graph(db, parent)
    join_id = found[1].join_of(parent.stage_id) if found else None
    summaries = "\n".join(
        f"- {lane.lane_key}: {task_ops.last_summary(db, lane) or ''}" for lane in live
    )
    task_ops.add_event(db, parent, TaskEventKind.JOINED, summaries)
    join = db.get(Stage, join_id) if join_id else None
    if join is None:
        _end(db, parent)
    else:
        task_ops.move_to_stage(db, parent, join, front=False)


# --------------------------------------------------------------------------------- forks
def start_fork(db: Session, task: Task, fork: Stage) -> None:
    """The task reached a stage with several links: fix the branches that are fixed, and ask
    for the rest."""
    task.status = TaskStatus.DECIDING
    task.stage_id = fork.id
    task.agent_id = None
    task.waiting_reason = task.waiting_detail = None
    links = list(db.scalars(select(StageLink).where(StageLink.from_stage_id == fork.id)))
    links.sort(key=lambda link: link.position)
    always = [link.id for link in links if link.always]
    preset = root_of(db, task).preset_lanes.get(fork.id)
    if preset:
        chosen = {*preset, *always}
        take(db, task, fork, [link.id for link in links if link.id in chosen], DecisionBy.PRESET)
        return
    undecided = [link for link in links if not link.always]
    if not undecided:
        take(db, task, fork, always, DecisionBy.ALWAYS)
        return
    if request_decision is not None:
        request_decision(db, task, fork, undecided, always)
        return
    task_ops.wait_for_human(db, task, WaitingReason.CHOOSE_BRANCH, fork.name)


def take(
    db: Session,
    task: Task,
    fork: Stage,
    link_ids: list[str],
    by: DecisionBy,
    reasons: dict[str, str] | None = None,
    run_id: str | None = None,
) -> None:
    """Records the decision and starts the lanes it chose."""
    links = {
        link.id: link
        for link in db.scalars(select(StageLink).where(StageLink.from_stage_id == fork.id))
    }
    if not link_ids or any(i not in links for i in link_ids):
        raise ApiError(422, "invalid_branches", "choose at least one branch of the fork")
    reasons = reasons or {}
    db.add(
        BranchDecision(
            task_id=task.id,
            fork_stage_id=fork.id,
            run_id=run_id,
            decided_by=by,
            chosen=list(link_ids),
            reasons=reasons,
        )
    )
    lines = []
    for link in sorted(links.values(), key=lambda x: x.position):
        mark = "✓" if link.id in link_ids else "✗"
        why = reasons.get(link.id)
        lines.append(f"{mark} {link.name}" + (f": {why}" if why else ""))
    task_ops.add_event(db, task, TaskEventKind.DECISION, f"[{by}]\n" + "\n".join(lines), run_id)
    inbox.resolve_pending(db, Resolution.DISMISSED, task_id=task.id, kinds=task_ops.ATTENTION_KINDS)
    _fork_into(db, task, fork, [links[i] for i in link_ids])


def decide(db: Session, task: Task, link_ids: list[str]) -> None:
    """The person picks the branches of a task that waits for it."""
    if (
        task.status != TaskStatus.WAITING_HUMAN
        or task.waiting_reason != WaitingReason.CHOOSE_BRANCH
    ):
        raise ApiError(409, "task_status", "the task is not waiting for a branch", "status")
    fork = db.get(Stage, task.stage_id) if task.stage_id else None
    if fork is None:
        raise ApiError(409, "task_status", "the task is not at a fork", "status")
    take(db, task, fork, link_ids, DecisionBy.USER)


def _fork_into(db: Session, task: Task, fork: Stage, chosen: list[StageLink]) -> None:
    task.status = TaskStatus.FORKED
    task.stage_id = fork.id
    task.agent_id = None
    wanted = {link.id for link in chosen}
    existing = {lane.lane_link_id: lane for lane in lanes_of(db, task, fork.id)}
    for link_id, lane in existing.items():  # branches of an earlier round not taken now
        if link_id not in wanted and lane.status != TaskStatus.CANCELLED:
            lane.status = TaskStatus.CANCELLED
            lane.finished_at = utcnow()
    for link in chosen:
        lane = existing.get(link.id) or _new_lane(db, task, fork, link, existing.values())
        _run_lane(db, task, lane, link)


def _new_lane(db: Session, parent: Task, fork: Stage, link: StageLink, siblings) -> Task:
    taken = {s.lane_key for s in siblings} | {
        s.lane_key for s in db.scalars(select(Task).where(Task.lane_of_id == parent.id))
    }
    base = _slug(link.name)
    key, n = base, 2
    while (f"{parent.lane_key}.{key}" if parent.lane_key else key) in taken:
        key, n = f"{base}-{n}", n + 1
    lane = Task(
        workspace_id=parent.workspace_id,
        number=parent.number,
        project_id=parent.project_id,
        title=parent.title,
        description=parent.description,
        priority=parent.priority,
        lane_of_id=parent.id,
        lane_link_id=link.id,
        fork_stage_id=fork.id,
        lane_key=f"{parent.lane_key}.{key}" if parent.lane_key else key,
    )
    db.add(lane)
    db.flush()
    task_ops.add_event(db, lane, TaskEventKind.CREATED, link.name)
    return lane


def _serial(db: Session, task: Task) -> bool:
    """In a direct folder only one task of the project runs at a time: the lanes go one after
    the other, in the order of their branches."""
    project = db.get(Project, task.project_id)
    return project is not None and project.workspace_mode == WorkspaceMode.DIRECT


def _run_lane(db: Session, parent: Task, lane: Task, link: StageLink, reason: str = "") -> None:
    """(Re)starts a lane at the first stage of its branch."""
    first = db.get(Stage, link.to_stage_id)
    assert first is not None
    task_ops.add_event(db, parent, TaskEventKind.LANE_STARTED, lane.lane_key)
    _restart(db, parent, lane, first, reason, front=False)


def _restart(db: Session, parent: Task, lane: Task, stage: Stage, reason: str, front: bool) -> None:
    lane.finished_at = None
    lane.waiting_reason = lane.waiting_detail = None
    if reason:
        task_ops.add_event(db, lane, TaskEventKind.REJECTED, reason, stage=stage)
    busy = _serial(db, parent) and any(
        s.id != lane.id and s.status not in IDLE_LANE
        for s in lanes_of(db, parent, lane.fork_stage_id)
    )
    if busy:  # it waits for the lane before it
        lane.status = TaskStatus.BACKLOG
        lane.stage_id = stage.id
        lane.agent_id = stage.agent_id
        return
    task_ops.move_to_stage(db, lane, stage, front=front)


def _start_next_in_line(db: Session, parent: Task) -> None:
    if not _serial(db, parent):
        return
    lanes = lanes_of(db, parent, parent.stage_id)
    if any(lane.status not in IDLE_LANE for lane in lanes):
        return
    waiting = next((lane for lane in lanes if lane.status == TaskStatus.BACKLOG), None)
    if waiting is not None:
        task_ops.requeue(db, waiting)


# ------------------------------------------------------------------- rejections and edits
def send_back(db: Session, task: Task, target: Stage, reason: str = "") -> None:
    """Moves a task back to an earlier stage of its path, or, after a join, into one of the
    branches it came from: that lane is reopened and the task waits for it again."""
    stage = db.get(Stage, task.stage_id) if task.stage_id else None
    found = pipeline_graph(db, task)
    if stage is None or found is None:
        task_ops.move_to_stage(db, task, target, front=True)
        return
    graph = found[1]
    if not graph.can_send_back(stage.id, target.id):
        raise ApiError(422, "invalid_stage", "the task cannot go back to that stage", "target")
    mine, theirs = graph.path_of(stage.id), graph.path_of(target.id)
    if theirs == mine:
        task_ops.move_to_stage(db, task, target, front=True)
        return
    _reopen(db, task, graph, theirs[len(mine) :], target, reason)


def _reopen(db: Session, parent: Task, graph: Graph, path, target: Stage, reason: str) -> None:
    fork_id, branch = path[0]
    link_id = graph.out[fork_id][branch].id
    link = db.get(StageLink, link_id)
    fork = db.get(Stage, fork_id)
    assert link is not None and fork is not None
    parent.status = TaskStatus.FORKED
    parent.stage_id = fork_id
    parent.agent_id = None
    lane = next((x for x in lanes_of(db, parent, fork_id) if x.lane_link_id == link_id), None)
    if lane is None:
        lane = _new_lane(db, parent, fork, link, [])
    task_ops.add_event(db, parent, TaskEventKind.LANE_STARTED, f"{lane.lane_key} (reabierta)")
    if len(path) == 1:
        _restart(db, parent, lane, target, reason, front=True)
        return
    lane.status = TaskStatus.FORKED
    lane.finished_at = None
    lane.stage_id = path[1][0]
    lane.agent_id = None
    _reopen(db, lane, graph, path[1:], target, reason)


def add_lane(db: Session, parent: Task, link_id: str) -> Task:
    """The person adds a branch the decision left out: it starts now and the join waits."""
    if parent.status != TaskStatus.FORKED or parent.stage_id is None:
        raise ApiError(409, "task_status", "the task has not forked", "status")
    link = db.get(StageLink, link_id)
    fork = db.get(Stage, parent.stage_id)
    if link is None or fork is None or link.from_stage_id != fork.id:
        raise ApiError(422, "invalid_branches", "that branch is not part of this fork", "link_id")
    lane = next((x for x in lanes_of(db, parent, fork.id) if x.lane_link_id == link.id), None)
    if lane is not None and lane.status not in (TaskStatus.DONE, TaskStatus.CANCELLED):
        raise ApiError(409, "lane_active", "that branch is already running", "link_id")
    if lane is None:
        lane = _new_lane(db, parent, fork, link, [])
    task_ops.add_event(db, parent, TaskEventKind.LANE_ADDED, lane.lane_key)
    _run_lane(db, parent, lane, link)
    return lane


def cancel_tree(db: Session, task: Task) -> list[Task]:
    """Cancels a task and every lane under it; returns the ones that were still alive (their
    runs must be stopped)."""
    alive = [t for t in [task, *descendants(db, task)] if t.status not in FINISHED_TASK_STATUSES]
    for item in reversed(alive):  # the deepest first
        task_ops.finish(db, item, TaskStatus.CANCELLED, TaskEventKind.CANCELLED)
    return alive


def cancel_lane(db: Session, lane: Task) -> list[Task]:
    """Cancels one branch of a running fork; the join stops waiting for it."""
    if lane.lane_of_id is None:
        raise ApiError(409, "not_a_lane", "the task is not a branch of another", "status")
    cancelled = cancel_tree(db, lane)
    parent = db.get(Task, lane.lane_of_id)
    if parent is not None:
        task_ops.add_event(db, parent, TaskEventKind.LANE_CANCELLED, lane.lane_key)
        _start_next_in_line(db, parent)
        try_join(db, parent)
    return cancelled
