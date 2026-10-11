"""A project's pipeline: validation, saving it without breaking the tasks in flight, and the
«Desarrollo web» template."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_os.errors import ApiError
from agentic_os.models import (
    FINISHED_TASK_STATUSES,
    Agent,
    AgentStatus,
    Pipeline,
    Project,
    Stage,
    Task,
    TaskStatus,
)
from agentic_os.schemas.pipeline import PipelineTemplate, PipelineWrite, StageWrite
from agentic_os.services import tasks as task_ops

# «Desarrollo web»: Requisitos → Desarrollo → QA, and QA can send the task back to Desarrollo.
# Each stage gets the first active agent created from the matching agent template, if any.
TEMPLATES: dict[PipelineTemplate, tuple[str, list[tuple[str, str, int | None]]]] = {
    PipelineTemplate.WEB: (
        "Desarrollo web",
        [("Requisitos", "analyst", None), ("Desarrollo", "developer", None), ("QA", "qa", 1)],
    ),
}


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


def _validate(db: Session, payload: PipelineWrite, existing: dict[str, Stage]) -> None:
    for index, stage in enumerate(payload.stages):
        if stage.id is not None and stage.id not in existing:
            raise ApiError(422, "unknown_stage", "the stage is not in this pipeline", "stages")
        if stage.reject_to is not None and not 0 <= stage.reject_to < index:
            raise ApiError(
                422,
                "invalid_reject_to",
                "a stage can only send tasks back to an earlier one",
                "stages",
            )
        if stage.agent_id is not None and db.get(Agent, stage.agent_id) is None:
            raise ApiError(422, "unknown_agent", "the agent does not exist", "stages")
    ids = [s.id for s in payload.stages if s.id]
    if len(ids) != len(set(ids)):
        raise ApiError(422, "duplicate_stage", "a stage appears twice", "stages")


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

    pipeline.name = payload.name
    pipeline.max_rejections = payload.max_rejections
    for stage in removed:
        pipeline.stages.remove(stage)
    db.flush()

    rows: list[Stage] = []
    for position, data in enumerate(payload.stages):
        stage = existing.get(data.id) if data.id else None
        if stage is None:
            stage = Stage(pipeline_id=pipeline.id, position=position, name=data.name)
            pipeline.stages.append(stage)
        old_agent = stage.agent_id
        stage.position = position
        stage.name = data.name
        stage.agent_id = data.agent_id
        stage.requires_review = data.requires_review
        rows.append(stage)
        if stage.id and old_agent != data.agent_id:
            _move_queued(db, stage)
    db.flush()
    for stage, data in zip(rows, payload.stages, strict=True):
        stage.reject_to_stage_id = rows[data.reject_to].id if data.reject_to is not None else None
    db.flush()
    db.expire(pipeline, ["stages"])
    return pipeline


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
    name, stages = TEMPLATES[template]
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.workspace_id == project.workspace_id, Agent.status == AgentStatus.ACTIVE)
            .order_by(Agent.created_at)
        )
    )

    def agent_for(template_id: str) -> str | None:
        return next((a.id for a in agents if a.template == template_id), None)

    payload = PipelineWrite(
        name=name,
        stages=[
            StageWrite(name=stage, agent_id=agent_for(template_id), reject_to=reject_to)
            for stage, template_id, reject_to in stages
        ],
    )
    return save(db, project, payload)
