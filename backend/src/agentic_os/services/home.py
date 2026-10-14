"""What Inicio shows and no other endpoint gives: the state of each agent with its sessions, the
projects with who works on them, and the counters of the top navigation (phase 09)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import (
    ACTIVE_STATUSES,
    FINISHED_TASK_STATUSES,
    Agent,
    AgentStatus,
    InboxItem,
    InboxStatus,
    Project,
    Run,
    Task,
    TaskStatus,
)
from agentic_os.schemas.home import (
    AgentState,
    HomeAgent,
    HomeCounts,
    HomeProject,
    HomeRead,
    HomeSession,
    HomeWorker,
)
from agentic_os.services import accounts as account_ops
from agentic_os.services.agent_target import target_for
from agentic_os.services.runs import resume

RESUMABLE_WINDOW = timedelta(days=14)
RESUMABLE_CANDIDATES = 100
_ACTIVE = [s.value for s in ACTIVE_STATUSES]
_FINISHED = [s.value for s in FINISHED_TASK_STATUSES]


def _state(agent: Agent, running: bool, waiting: bool) -> AgentState:
    if agent.status == AgentStatus.DRAFT:
        return AgentState.DRAFT
    if waiting:  # what needs the person comes before what is running
        return AgentState.WAITING
    return AgentState.RUNNING if running else AgentState.IDLE


def build(db: Session) -> HomeRead:
    agents = list(
        db.scalars(
            select(Agent).where(Agent.workspace_id == DEFAULT_WORKSPACE).order_by(Agent.created_at)
        )
    )
    agent_ids = [a.id for a in agents]
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.workspace_id == DEFAULT_WORKSPACE)
            .order_by(Project.created_at)
        )
    )
    projects_by_id = {p.id: p for p in projects}

    queued: dict[str, int] = {}
    waiting_tasks: set[str] = set()
    for agent_id, status, count in db.execute(
        select(Task.agent_id, Task.status, func.count())
        .where(Task.workspace_id == DEFAULT_WORKSPACE, Task.agent_id.in_(agent_ids))
        .group_by(Task.agent_id, Task.status)
    ):
        if status == TaskStatus.QUEUED:
            queued[agent_id] = count
        elif status == TaskStatus.WAITING_HUMAN:
            waiting_tasks.add(agent_id)

    pending = dict(
        db.execute(
            select(InboxItem.agent_id, func.count())
            .where(
                InboxItem.workspace_id == DEFAULT_WORKSPACE,
                InboxItem.status == InboxStatus.PENDING,
                InboxItem.agent_id.in_(agent_ids),
            )
            .group_by(InboxItem.agent_id)
        ).all()
    )

    # Live sessions: the agents' own runs (their subagents go with them).
    live = list(
        db.scalars(
            select(Run)
            .where(Run.status.in_(_ACTIVE), Run.parent_run_id.is_(None))
            .order_by(Run.created_at)
        )
    )
    candidates = db.scalars(
        select(Run)
        .where(
            Run.agent_id.in_(agent_ids),
            Run.status.in_([s.value for s in resume.RESUMABLE]),
            Run.cli_session_id.is_not(None),
            Run.parent_run_id.is_(None),
            Run.created_at > utcnow() - RESUMABLE_WINDOW,
        )
        .order_by(Run.created_at.desc())
        .limit(RESUMABLE_CANDIDATES)
    )
    resumable = resume.resumable_among(db, list(candidates))

    task_ids = {r.task_id for r in [*live, *resumable] if r.task_id}
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids)))}

    sessions: dict[str, list[HomeSession]] = {}
    for run, is_resumable in [(r, False) for r in live] + [(r, True) for r in resumable]:
        if run.agent_id is None:
            continue
        task = tasks.get(run.task_id) if run.task_id else None
        project = projects_by_id.get(run.project_id) if run.project_id else None
        sessions.setdefault(run.agent_id, []).append(
            HomeSession(
                run_id=run.id,
                task_id=task.id if task else None,
                task_code=task.code if task else None,
                task_title=task.title if task else None,
                project_id=run.project_id,
                project_name=run.project_name,
                project_color=project.color if project else None,
                status=run.status,
                resumable=is_resumable,
                started_at=run.started_at,
                created_at=run.created_at,
            )
        )

    running_agents = {r.agent_id for r in live if r.agent_id}
    home_agents = []
    index = account_ops.AccountIndex(db)
    for agent in agents:
        target = target_for(db, agent, index=index)
        agent_pending = pending.get(agent.id, 0)
        home_agents.append(
            HomeAgent(
                id=agent.id,
                name=agent.name,
                role=agent.role,
                color=agent.color,
                cli=target.cli,
                status=agent.status,
                team_id=agent.team_id,
                account_id=target.account.id if target.using_fallback else agent.account_id,
                using_fallback=target.using_fallback,
                state=_state(
                    agent,
                    agent.id in running_agents,
                    agent.id in waiting_tasks or agent_pending > 0,
                ),
                queued=queued.get(agent.id, 0),
                pending_requests=agent_pending,
                sessions=sessions.get(agent.id, []),
            )
        )

    open_by_project = dict(
        db.execute(
            select(Task.project_id, func.count())
            .where(Task.workspace_id == DEFAULT_WORKSPACE, Task.status.not_in(_FINISHED))
            .group_by(Task.project_id)
        ).all()
    )
    agent_names = {a.id: a.name for a in agents}
    workers: dict[str, list[HomeWorker]] = {}
    for task in db.scalars(
        select(Task)
        .where(Task.workspace_id == DEFAULT_WORKSPACE, Task.status == TaskStatus.RUNNING)
        .order_by(Task.number)
    ):
        if task.agent_id in agent_names:
            workers.setdefault(task.project_id, []).append(
                HomeWorker(
                    agent_id=task.agent_id,
                    agent_name=agent_names[task.agent_id],
                    task_code=task.code,
                    task_title=task.title,
                )
            )
    home_projects = [
        HomeProject(
            id=p.id,
            name=p.name,
            color=p.color,
            open_tasks=open_by_project.get(p.id, 0),
            workers=workers.get(p.id, []),
        )
        for p in projects
    ]

    active_runs = db.scalar(select(func.count()).select_from(Run).where(Run.status.in_(_ACTIVE)))
    return HomeRead(
        agents=home_agents,
        projects=home_projects,
        counts=HomeCounts(
            sessions=len(live),
            agents_working=len(running_agents),
            open_tasks=sum(open_by_project.values()),
            active_runs=active_runs or 0,
        ),
    )
