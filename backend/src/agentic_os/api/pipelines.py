from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.projects import get_project_or_404
from agentic_os.api.tasks import SchedulerDep
from agentic_os.db.session import get_session
from agentic_os.models import Agent, Pipeline
from agentic_os.schemas.pipeline import (
    GraphIssue,
    LinkRead,
    PipelineRead,
    PipelineWrite,
    PreviewBranchResult,
    PreviewRead,
    PreviewRequest,
    StageRead,
    TemplateRequest,
)
from agentic_os.services import decider, pipelines
from agentic_os.services import tasks as task_ops

router = APIRouter(tags=["pipelines"])
DbSession = Annotated[Session, Depends(get_session)]


def read_pipeline(db: Session, pipeline: Pipeline) -> PipelineRead:
    db.refresh(pipeline)
    stages = list(pipeline.stages)
    agent_ids = {s.agent_id for s in stages if s.agent_id}
    agents = {a.id: a for a in db.scalars(select(Agent).where(Agent.id.in_(agent_ids)))}
    active = pipelines.active_tasks_by_stage(db, [s.id for s in stages])
    graph = pipelines.graph_of(pipeline)
    graph.validate()  # fills the forks and joins (an invalid graph just has none)
    return PipelineRead(
        id=pipeline.id,
        project_id=pipeline.project_id,
        name=pipeline.name,
        max_rejections=pipeline.max_rejections,
        decider_cli=pipeline.decider_cli,
        decider_account_id=pipeline.decider_account_id,
        decider_model=pipeline.decider_model,
        links=[
            LinkRead(
                id=x.id,
                from_stage_id=x.from_stage_id,
                to_stage_id=x.to_stage_id,
                name=x.name,
                condition=x.condition,
                always=x.always,
                position=x.position,
            )
            for x in pipeline.links
        ],
        stages=[
            StageRead(
                id=s.id,
                position=s.position,
                name=s.name,
                agent_id=s.agent_id,
                agent_name=agents[s.agent_id].name if s.agent_id in agents else None,
                agent_color=agents[s.agent_id].color if s.agent_id in agents else None,
                requires_review=s.requires_review,
                reject_to_stage_id=s.reject_to_stage_id,
                reject_extra_stage_ids=list(s.reject_extra_ids),
                x=s.x,
                y=s.y,
                confirm_decision=s.confirm_decision,
                exit_condition=s.exit_condition,
                exit_x=s.exit_x,
                exit_y=s.exit_y,
                join_stage_id=graph.join_of(s.id),
                active_tasks=active.get(s.id, 0),
            )
            for s in stages
        ],
    )


@router.get("/projects/{project_id}/pipeline")
def get_pipeline(project_id: str, db: DbSession) -> PipelineRead | None:
    get_project_or_404(db, project_id)
    pipeline = task_ops.pipeline_of(db, project_id)
    return read_pipeline(db, pipeline) if pipeline is not None else None


@router.put("/projects/{project_id}/pipeline")
def save_pipeline(
    project_id: str, payload: PipelineWrite, db: DbSession, scheduler: SchedulerDep
) -> PipelineRead:
    project = get_project_or_404(db, project_id)
    pipeline = pipelines.save(db, project, payload)
    db.commit()
    scheduler.poke()  # queued tasks may have moved to another agent
    return read_pipeline(db, pipeline)


@router.post("/projects/{project_id}/pipeline/validate")
def validate_pipeline(project_id: str, payload: PipelineWrite, db: DbSession) -> list[GraphIssue]:
    """The problems of a pipeline as edited, without saving it."""
    get_project_or_404(db, project_id)
    return pipelines.check(payload)


@router.post("/projects/{project_id}/pipeline/decide-preview")
def preview_decision(
    project_id: str, payload: PreviewRequest, db: DbSession, request: Request
) -> PreviewRead:
    """«Probar»: what the decider would choose for an example task. It costs a real call."""
    project = get_project_or_404(db, project_id)
    transient = Pipeline(
        decider_cli=payload.decider_cli,
        decider_account_id=payload.decider_account_id,
        decider_model=payload.decider_model,
    )
    views = [
        decider.BranchView(id=str(i), name=b.name, condition=b.condition)
        for i, b in enumerate(payload.branches)
    ]
    result, asked = decider.preview(
        db,
        project,
        transient,
        views,
        payload.title,
        payload.description,
        request.app.state.settings.cli_command_overrides,
    )
    db.commit()
    return PreviewRead(
        branches=[
            PreviewBranchResult(
                name=b.name, take=result.taken.get(b.id, False), reason=result.reasons.get(b.id, "")
            )
            for b in views
        ],
        cli=asked.cli.value if asked else None,
        model=result.model or (asked.model if asked else None),
        cost_usd=result.usage.cost_usd,
        seconds=round(result.seconds, 1),
        error=result.error,
    )


@router.post("/projects/{project_id}/pipeline/template", status_code=status.HTTP_201_CREATED)
def pipeline_from_template(
    project_id: str, payload: TemplateRequest, db: DbSession
) -> PipelineRead:
    project = get_project_or_404(db, project_id)
    pipeline = pipelines.from_template(db, project, payload.template)
    db.commit()
    return read_pipeline(db, pipeline)


@router.delete("/projects/{project_id}/pipeline", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(project_id: str, db: DbSession) -> None:
    pipelines.delete(db, get_project_or_404(db, project_id))
    db.commit()
