"""A project's pipeline: validation, saving it without breaking the tasks in flight, and the
templates."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.errors import ApiError
from agentic_os.models import (
    FINISHED_TASK_STATUSES,
    Agent,
    AgentStatus,
    CliAccount,
    McpExclusion,
    Pipeline,
    Project,
    SkillMode,
    Stage,
    StageLink,
    Task,
    TaskStatus,
    Team,
)
from agentic_os.schemas.pipeline import (
    CopyWarning,
    GraphIssue,
    LinkWrite,
    NewAgents,
    PipelineTemplate,
    PipelineWrite,
    StageWrite,
    TemplatePlanStage,
)
from agentic_os.services import tasks as task_ops
from agentic_os.services.pipeline_graph import Edge, Graph, GraphErrorCode

# Phase 24: the conditions of the «Desarrollo» template (its branches and exits).
BRANCH_FRONTEND = "La tarea toca la interfaz de usuario o el frontend"
BRANCH_BACKEND = "La tarea toca la API, la base de datos, la lógica de negocio o el backend"
BRANCH_DATA = "La tarea pide análisis de datos, modelos, métricas o informes"
EXIT_REQUIREMENTS = "La tarea solo pide definir o revisar requisitos"
EXIT_ARCHITECTURE = "La tarea solo pide definir o revisar la arquitectura"
EXIT_NO_DEPLOY = "La tarea no necesita despliegue"

# Where a new «Fin» node goes when the editor does not say: under its stage.
EXIT_OFFSET = 110


def _development() -> PipelineWrite:
    """«Desarrollo» (phase 24): requirements → their validation → architecture → (frontend |
    backend | data) → QA → IT. Requirements, architecture and QA can end the task early; the
    reviews are at the validation, the architecture and the end."""
    return PipelineWrite(
        name="Desarrollo",
        stages=[
            StageWrite(name="Toma de requisitos", agent_id="analyst"),
            StageWrite(
                name="Validación de requisitos",
                agent_id="requirements_validator",
                requires_review=True,
                reject_to=0,
                exit_condition=EXIT_REQUIREMENTS,
            ),
            StageWrite(
                name="Arquitectura",
                agent_id="software_architect",
                requires_review=True,
                reject_to=0,
                exit_condition=EXIT_ARCHITECTURE,
            ),
            StageWrite(name="Frontend", agent_id="frontend_developer"),
            StageWrite(name="Backend", agent_id="backend_developer"),
            StageWrite(name="Datos", agent_id="data_scientist"),
            StageWrite(
                name="QA",
                agent_id="qa",
                reject_to=3,
                reject_also=[4, 5],
                exit_condition=EXIT_NO_DEPLOY,
            ),
            StageWrite(
                name="IT / despliegue", agent_id="devops", requires_review=True, reject_to=6
            ),
        ],
        links=[
            LinkWrite(source=0, target=1),
            LinkWrite(source=1, target=2),
            LinkWrite(source=2, target=3, name="Frontend", condition=BRANCH_FRONTEND),
            LinkWrite(source=2, target=4, name="Backend", condition=BRANCH_BACKEND),
            LinkWrite(source=2, target=5, name="Datos", condition=BRANCH_DATA),
            LinkWrite(source=3, target=6),
            LinkWrite(source=4, target=6),
            LinkWrite(source=5, target=6),
            LinkWrite(source=6, target=7),
        ],
    )


# The `agent_id` of a template stage names an agent template: it gets the first active agent
# created from it, if any.
TEMPLATES = {PipelineTemplate.DEVELOPMENT: _development}


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
    exits = {s.id: s.exit_condition for s in pipeline.stages if s.exit_condition is not None}
    return Graph(ids, edges, rejects, exits)


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
    exits = {
        nodes[i]: s.exit_condition
        for i, s in enumerate(payload.stages)
        if s.exit_condition is not None
    }
    return Graph(nodes, edges, rejects, exits)


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
        stage.exit_condition = data.exit_condition
        if data.exit_condition is None:
            stage.exit_x = stage.exit_y = None
        elif data.exit_x is not None and data.exit_y is not None:
            stage.exit_x, stage.exit_y = data.exit_x, data.exit_y
        elif stage.exit_x is None or stage.exit_y is None:
            stage.exit_x, stage.exit_y = stage.x, stage.y + EXIT_OFFSET
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
        # One way of saying «always» (phase 21): no condition. A flagged link drops its text.
        row.condition = "" if link.always else link.condition
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


def _active_agents(db: Session, workspace_id: str) -> list[Agent]:
    return list(
        db.scalars(
            select(Agent)
            .where(
                Agent.workspace_id == workspace_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.archived_at.is_(None),
            )
            .order_by(Agent.created_at)
        )
    )


def template_plan(
    db: Session, template: PipelineTemplate, workspace_id: str = DEFAULT_WORKSPACE
) -> list[TemplatePlanStage]:
    """Phase 24: each stage of a template with the active agent made from its agent template
    (the one it would get), or none (one would be created)."""
    from agentic_os.services.templates import BY_ID

    agents = _active_agents(db, workspace_id)
    plan = []
    for index, stage in enumerate(TEMPLATES[template]().stages):
        template_id = stage.agent_id or ""
        agent = next((a for a in agents if a.template == template_id), None)
        plan.append(
            TemplatePlanStage(
                index=index,
                name=stage.name,
                template_id=template_id,
                template_name=BY_ID[template_id].name if template_id in BY_ID else template_id,
                agent_id=agent.id if agent else None,
                agent_name=agent.name if agent else None,
            )
        )
    return plan


def _team_for(db: Session, workspace_id: str, create: NewAgents) -> Team:
    if create.team_id:
        team = db.get(Team, create.team_id)
        if team is None or team.workspace_id != workspace_id:
            raise ApiError(422, "team_not_found", "the team does not exist", "create.team_id")
        return team
    team = Team(workspace_id=workspace_id, name=create.team_name or "Desarrollo")
    db.add(team)
    db.flush()
    return team


def _agent_from_template(db: Session, template_id: str, create: NewAgents, team: Team) -> Agent:
    """A new active agent made from a fixed agent template, with the chosen CLI and account."""
    from agentic_os.services.templates import BY_ID

    template = BY_ID[template_id]
    values = template.model_dump(exclude={"id", "own", "skills", "connections", "documents"})
    model = create.model or (template.model if template.cli == create.cli else "")
    values.update(
        cli=create.cli,
        model=model,
        account_id=create.account_id,
        team_id=team.id,
        template=template.id,
        status=AgentStatus.ACTIVE,
    )
    agent = Agent(workspace_id=team.workspace_id, **values)
    db.add(agent)
    db.flush()
    return agent


def from_template(
    db: Session,
    project: Project,
    template: PipelineTemplate,
    assign: dict[int, str | None] | None = None,
    create: NewAgents | None = None,
) -> Pipeline:
    """The template's pipeline for the project. Each stage gets the agent chosen by hand
    (`assign`), else an active agent made from its agent template, else (with `create`) a new
    one made from it, in one team. Whoever calls it commits once: all or nothing."""
    if task_ops.pipeline_of(db, project.id) is not None:
        raise ApiError(409, "pipeline_exists", "the project already has a pipeline")
    payload = TEMPLATES[template]()
    assign = assign or {}
    agents = _active_agents(db, project.workspace_id)
    if create is not None and create.account_id:
        account = db.get(CliAccount, create.account_id)
        if account is None:
            raise ApiError(
                422, "account_not_found", "the account does not exist", "create.account_id"
            )
        if account.cli != create.cli:
            raise ApiError(
                422, "account_cli_mismatch", "the account is of another CLI", "create.account_id"
            )
    team: Team | None = None
    for index, stage in enumerate(payload.stages):
        template_id = stage.agent_id
        if index in assign and assign[index] is not None:
            chosen = db.get(Agent, assign[index])
            if chosen is None or chosen.status != AgentStatus.ACTIVE or chosen.archived_at:
                raise ApiError(
                    422, "unknown_agent", "the agent does not exist or is not active", "assign"
                )
            stage.agent_id = chosen.id
            continue
        found = next((a for a in agents if a.template == template_id), None)
        if found is not None:
            stage.agent_id = found.id
        elif create is not None and template_id:
            team = team or _team_for(db, project.workspace_id, create)
            made = _agent_from_template(db, template_id, create, team)
            agents.append(made)
            stage.agent_id = made.id
        else:
            stage.agent_id = None
    return save(db, project, payload)


def _write_of(
    pipeline: Pipeline, agents: dict[str, Agent]
) -> tuple[PipelineWrite, list[CopyWarning]]:
    """A saved pipeline as a new payload (no ids), with its agents kept if they still work."""
    stages = list(pipeline.stages)
    index = {s.id: i for i, s in enumerate(stages)}
    warnings: list[CopyWarning] = []
    rows = []
    for s in stages:
        agent = agents.get(s.agent_id or "")
        usable = agent is not None and agent.status == AgentStatus.ACTIVE and not agent.archived_at
        if agent is not None and not usable:
            warnings.append(CopyWarning(stage=s.name, agent=agent.name))
        rows.append(
            StageWrite(
                name=s.name,
                agent_id=agent.id if usable and agent else None,
                requires_review=s.requires_review,
                reject_to=index.get(s.reject_to_stage_id) if s.reject_to_stage_id else None,
                reject_also=[index[x] for x in s.reject_extra_ids if x in index],
                x=s.x,
                y=s.y,
                confirm_decision=s.confirm_decision,
                exit_condition=s.exit_condition,
                exit_x=s.exit_x,
                exit_y=s.exit_y,
            )
        )
    links = [
        LinkWrite(
            source=index[x.from_stage_id],
            target=index[x.to_stage_id],
            name=x.name,
            condition=x.condition,
            always=x.always,
        )
        for x in pipeline.links
    ]
    payload = PipelineWrite(
        name=pipeline.name,
        max_rejections=pipeline.max_rejections,
        stages=rows,
        links=links,
        decider_cli=pipeline.decider_cli,  # type: ignore[arg-type]
        decider_account_id=pipeline.decider_account_id,
        decider_model=pipeline.decider_model,
    )
    return payload, warnings


def copy_from(db: Session, project: Project, source: Project) -> tuple[Pipeline, list[CopyWarning]]:
    """Phase 24: the pipeline of another project, with the same agents and the skills and
    connections set on each stage; no tasks, history or usage. A stage whose agent is archived
    or a draft is left without one, with a warning."""
    if task_ops.pipeline_of(db, project.id) is not None:
        raise ApiError(409, "pipeline_exists", "the project already has a pipeline")
    original = task_ops.pipeline_of(db, source.id)
    if original is None or source.id == project.id:
        raise ApiError(
            422, "no_pipeline", "that project has no pipeline to copy", "from_project_id"
        )
    ids = {s.agent_id for s in original.stages if s.agent_id}
    agents = {a.id: a for a in db.scalars(select(Agent).where(Agent.id.in_(ids)))}
    payload, warnings = _write_of(original, agents)
    old_ids = [s.id for s in original.stages]
    pipeline = save(db, project, payload)
    db.refresh(pipeline)
    new_ids = dict(zip(old_ids, [s.id for s in pipeline.stages], strict=True))
    for mode in db.scalars(select(SkillMode).where(SkillMode.stage_id.in_(old_ids))):
        db.add(SkillMode(skill_id=mode.skill_id, stage_id=new_ids[mode.stage_id], mode=mode.mode))
    for gone in db.scalars(select(McpExclusion).where(McpExclusion.stage_id.in_(old_ids))):
        db.add(McpExclusion(connection_id=gone.connection_id, stage_id=new_ids[gone.stage_id]))
    db.flush()
    return pipeline, warnings
