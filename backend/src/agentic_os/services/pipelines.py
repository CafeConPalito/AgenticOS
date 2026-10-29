"""A project's pipeline: validation, saving it without breaking the tasks in flight, and the
templates."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import (
    FINISHED_TASK_STATUSES,
    Agent,
    AgentStatus,
    CliAccount,
    Pipeline,
    Project,
    Stage,
    StageLink,
    Task,
    TaskStatus,
)
from agentic_os.schemas.pipeline import (
    GraphIssue,
    LinkWrite,
    PipelineTemplate,
    PipelineWrite,
    StageWrite,
)
from agentic_os.services import tasks as task_ops
from agentic_os.services.pipeline_graph import Edge, Graph, GraphErrorCode

BRANCH_BACKEND = "La tarea toca la API, la base de datos o el backend"
BRANCH_FRONTEND = "La tarea toca la interfaz de usuario o el frontend"


def _web() -> PipelineWrite:
    """«Desarrollo web»: Requisitos → Desarrollo → QA, and QA can send the task back."""
    return PipelineWrite(
        name="Desarrollo web",
        stages=[
            StageWrite(name="Requisitos", agent_id="analyst"),
            StageWrite(name="Desarrollo", agent_id="developer"),
            StageWrite(name="QA", agent_id="qa", reject_to=1),
        ],
    )


def _web_split() -> PipelineWrite:
    """Requisitos → (Dev backend | Dev frontend) → QA: the decider picks the branches, QA waits
    for the ones taken and can send the task back to whichever failed."""
    return PipelineWrite(
        name="Desarrollo web con backend y frontend",
        stages=[
            StageWrite(name="Requisitos", agent_id="analyst"),
            StageWrite(name="Dev backend", agent_id="developer"),
            StageWrite(name="Dev frontend", agent_id="developer"),
            StageWrite(name="QA", agent_id="qa", reject_to=1, reject_also=[2]),
        ],
        links=[
            LinkWrite(source=0, target=1, name="Backend", condition=BRANCH_BACKEND),
            LinkWrite(source=0, target=2, name="Frontend", condition=BRANCH_FRONTEND),
            LinkWrite(source=1, target=3),
            LinkWrite(source=2, target=3),
        ],
    )


# The `agent_id` of a template stage names an agent template: it gets the first active agent
# created from it, if any.
TEMPLATES = {PipelineTemplate.WEB: _web, PipelineTemplate.WEB_SPLIT: _web_split}


def active_tasks_by_stage(db: Session, stage_ids: list[str]) -> dict[str, int]:
    if not stage_ids:
        return {}
    rows = db.execute(
        select(Task.stage_id, func.count())
        .where(
            Task.stage_id.in_(stage_ids),
            Task.status.notin_([s.value for s in FINISHED_TASK_STATUSES]),
        )
        .group_by(Task.stage_id)
    ).all()
    return dict(rows)


# ------------------------------------------------------------------------------- the graph
def graph_of(pipeline: Pipeline) -> Graph:
    """The saved pipeline as a graph (to ask where a task goes next)."""
    ids = [s.id for s in pipeline.stages]
    edges = [
        Edge(link.id, link.from_stage_id, link.to_stage_id, link.position)
        for link in pipeline.links
    ]
    rejects = {
        s.id: [t for t in [s.reject_to_stage_id, *s.reject_extra_ids] if t] for s in pipeline.stages
    }
    return Graph(ids, edges, rejects)


def _links_of(payload: PipelineWrite) -> list[LinkWrite]:
    if payload.links is not None:
        return payload.links
    return [LinkWrite(source=i, target=i + 1) for i in range(len(payload.stages) - 1)]


def _node(index: int, stage: StageWrite) -> str:
    return stage.id or f"new:{index}"


def _payload_graph(payload: PipelineWrite) -> Graph:
    """The graph being saved; its ids are the stages' ids, or `new:<index>` for new stages."""
    nodes = [_node(i, s) for i, s in enumerate(payload.stages)]
    edges = [
        Edge(
            f"link:{i}",
            nodes[link.source],
            nodes[link.target],
            i,
        )
        for i, link in enumerate(_links_of(payload))
    ]
    rejects = {
        nodes[i]: [nodes[t] for t in [s.reject_to, *s.reject_also] if t is not None]
        for i, s in enumerate(payload.stages)
    }
    return Graph(nodes, edges, rejects)


def layout_of(payload: PipelineWrite) -> dict[int, tuple[int, int]]:
    """Where the editor would place each stage, by index (phase 19: the Architect's preview).
    Empty if the links point outside the stages."""
    try:
        places = _payload_graph(payload).layout()
    except (IndexError, KeyError):
        return {}
    return {i: places[_node(i, s)] for i, s in enumerate(payload.stages)}


def check(payload: PipelineWrite) -> list[GraphIssue]:
    """The problems of a pipeline as edited, without saving it (the editor shows them live)."""
    _check_indexes(payload)
    graph = _payload_graph(payload)
    index = {_node(i, s): i for i, s in enumerate(payload.stages)}
    return [
        GraphIssue(
            code=error.code,
            stage=index.get(error.stage) if error.stage else None,
            link=int(error.link.split(":")[1]) if error.link else None,
        )
        for error in graph.validate()
    ]


def _check_indexes(payload: PipelineWrite) -> None:
    count = len(payload.stages)
    for stage in payload.stages:
        for target in [stage.reject_to, *stage.reject_also]:
            if target is not None and not 0 <= target < count:
                raise ApiError(
                    422, "invalid_reject_to", "a rejection goes back to a stage of the pipeline"
                )
        if stage.reject_to is None and stage.reject_also:
            raise ApiError(422, "invalid_reject_to", "other rejection targets need a main one")
    seen: set[tuple[int, int]] = set()
    for link in _links_of(payload):
        if not (0 <= link.source < count and 0 <= link.target < count):
            raise ApiError(422, "invalid_link", "a link joins two stages of the pipeline", "links")
        if link.source == link.target or (link.source, link.target) in seen:
            raise ApiError(422, "invalid_link", "a link is repeated or joins a stage to itself")
        seen.add((link.source, link.target))


def _validate(db: Session, payload: PipelineWrite, existing: dict[str, Stage]) -> None:
    for stage in payload.stages:
        if stage.id is not None and stage.id not in existing:
            raise ApiError(422, "unknown_stage", "the stage is not in this pipeline", "stages")
        if stage.agent_id is not None and db.get(Agent, stage.agent_id) is None:
            raise ApiError(422, "unknown_agent", "the agent does not exist", "stages")
    ids = [s.id for s in payload.stages if s.id]
    if len(ids) != len(set(ids)):
        raise ApiError(422, "duplicate_stage", "a stage appears twice", "stages")
    if payload.decider_account_id and db.get(CliAccount, payload.decider_account_id) is None:
        raise ApiError(422, "unknown_account", "the account does not exist", "decider_account_id")
    issues = check(payload)
    if issues:
        reject_codes = (GraphErrorCode.REJECT_NOT_BACKWARDS, GraphErrorCode.REJECT_OUTSIDE_PATH)
        code = "invalid_reject_to" if issues[0].code in reject_codes else "invalid_graph"
        message = (
            "a stage can only send tasks back to an earlier one of its path"
            if code == "invalid_reject_to"
            else "the pipeline is not well built"
        )
        raise ApiError(
            422,
            code,
            message,
            "stages",
            extra={"issues": [issue.model_dump() for issue in issues]},
        )


def save(db: Session, project: Project, payload: PipelineWrite) -> Pipeline:
    """Replaces the pipeline. Stages keep their ids; a stage with unfinished tasks cannot be
    removed. Queued tasks of a stage whose agent changes move to the new agent's queue."""
    pipeline = task_ops.pipeline_of(db, project.id)
    if pipeline is None:
        pipeline = Pipeline(project_id=project.id)
        db.add(pipeline)
        db.flush()
    existing = {s.id: s for s in pipeline.stages}
    _validate(db, payload, existing)

    kept = {s.id for s in payload.stages if s.id}
    removed = [s for s in pipeline.stages if s.id not in kept]
    in_use = active_tasks_by_stage(db, [s.id for s in removed])
    if any(in_use.values()):
        raise ApiError(409, "stage_in_use", "a removed stage still has tasks", "stages")

    _check_links_in_use(db, pipeline, payload)
    pipeline.name = payload.name
    pipeline.max_rejections = payload.max_rejections
    pipeline.decider_cli = payload.decider_cli
    pipeline.decider_account_id = payload.decider_account_id
    pipeline.decider_model = payload.decider_model or None
    gone = {s.id for s in removed}
    for link in [x for x in pipeline.links if x.from_stage_id in gone or x.to_stage_id in gone]:
        pipeline.links.remove(link)
    for stage in removed:
        pipeline.stages.remove(stage)
    db.flush()

    places = _payload_graph(payload).layout()
    rows: list[Stage] = []
    for position, data in enumerate(payload.stages):
        stage = existing.get(data.id) if data.id else None
        if stage is None:
            stage = Stage(pipeline_id=pipeline.id, position=position, name=data.name)
            pipeline.stages.append(stage)
            stage.x, stage.y = places[_node(position, data)]
        old_agent = stage.agent_id
        stage.position = position
        stage.name = data.name
        stage.agent_id = data.agent_id
        stage.requires_review = data.requires_review
        stage.confirm_decision = data.confirm_decision
        if data.x is not None and data.y is not None:
            stage.x, stage.y = data.x, data.y
        rows.append(stage)
        if stage.id and old_agent != data.agent_id:
            _move_queued(db, stage)
    db.flush()
    for stage, data in zip(rows, payload.stages, strict=True):
        stage.reject_to_stage_id = rows[data.reject_to].id if data.reject_to is not None else None
        stage.reject_extra_ids = [rows[t].id for t in data.reject_also]
    _save_links(db, pipeline, rows, _links_of(payload))
    db.flush()
    db.expire(pipeline, ["stages", "links"])
    return pipeline


def _check_links_in_use(db: Session, pipeline: Pipeline, payload: PipelineWrite) -> None:
    """A branch a lane is going through (or will come back to) cannot lose its link."""
    ids = [s.id for s in payload.stages]
    kept = {
        (ids[link.source], ids[link.target])
        for link in _links_of(payload)
        if ids[link.source] and ids[link.target]
    }
    dropped = [x.id for x in pipeline.links if (x.from_stage_id, x.to_stage_id) not in kept]
    if not dropped:
        return
    busy = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.lane_link_id.in_(dropped),
            Task.status.notin_([s.value for s in FINISHED_TASK_STATUSES]),
        )
    )
    if busy:
        raise ApiError(409, "link_in_use", "a branch still has a lane in progress", "links")


def _save_links(db: Session, pipeline: Pipeline, rows: list[Stage], links: list[LinkWrite]) -> None:
    """Links keep their ids when their two ends stay (tasks in a branch point at them)."""
    wanted = {(rows[link.source].id, rows[link.target].id): link for link in links}
    current = {(x.from_stage_id, x.to_stage_id): x for x in pipeline.links}
    for key, link in list(current.items()):
        if key not in wanted:
            pipeline.links.remove(link)
    db.flush()
    per_source: dict[str, int] = {}
    for link in links:
        source = rows[link.source].id
        key = (source, rows[link.target].id)
        row = current.get(key)
        if row is None:
            row = StageLink(pipeline_id=pipeline.id, from_stage_id=key[0], to_stage_id=key[1])
            pipeline.links.append(row)
        row.name = link.name or rows[link.target].name
        row.condition = link.condition
        row.always = link.always
        row.position = per_source.get(source, 0)
        per_source[source] = row.position + 1


def _move_queued(db: Session, stage: Stage) -> None:
    tasks = db.scalars(
        select(Task).where(Task.stage_id == stage.id, Task.status == TaskStatus.QUEUED)
    )
    for task in tasks:
        task.agent_id = stage.agent_id
        task.status = TaskStatus.BACKLOG
        if stage.agent_id is None:
            task_ops.wait_for_human(db, task, task_ops.WaitingReason.NO_AGENT, stage.name)
        else:
            task_ops.enqueue(db, task)


def delete(db: Session, project: Project) -> None:
    pipeline = task_ops.pipeline_of(db, project.id)
    if pipeline is None:
        return
    in_use = active_tasks_by_stage(db, [s.id for s in pipeline.stages])
    if any(in_use.values()):
        raise ApiError(409, "stage_in_use", "the pipeline still has unfinished tasks", "stages")
    db.delete(pipeline)


def from_template(db: Session, project: Project, template: PipelineTemplate) -> Pipeline:
    if task_ops.pipeline_of(db, project.id) is not None:
        raise ApiError(409, "pipeline_exists", "the project already has a pipeline")
    payload = TEMPLATES[template]()
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.workspace_id == project.workspace_id, Agent.status == AgentStatus.ACTIVE)
            .order_by(Agent.created_at)
        )
    )

    def agent_for(template_id: str | None) -> str | None:
        if template_id is None:
            return None
        return next((a.id for a in agents if a.template == template_id), None)

    for stage in payload.stages:
        stage.agent_id = agent_for(stage.agent_id)
    return save(db, project, payload)
