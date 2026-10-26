"""Proposals of the Architect and of `propose_agent` (phase 19, plan §7): what they change, and
approving (whole or in part) or rejecting them."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.models import Proposal, ProposalKind
from agentic_os.schemas.architect import (
    Applied,
    Approve,
    FieldChangeRead,
    ProposalRead,
    Reject,
    SkillDraftRead,
)
from agentic_os.services import proposals

router = APIRouter(tags=["proposals"])
DbSession = Annotated[Session, Depends(get_session)]


def read_proposal(db: Session, proposal: Proposal) -> ProposalRead:
    changes = []
    if proposal.kind == ProposalKind.AGENT_CHANGES and proposal.target_agent_id:
        changes = [FieldChangeRead(**vars(c)) for c in proposals.changes(db, proposal)]
    return ProposalRead(
        id=proposal.id,
        kind=proposal.kind,
        origin=proposal.origin,
        status=proposal.status,
        reason=proposal.reason,
        conversation_id=proposal.conversation_id,
        source_agent_id=proposal.source_agent_id,
        source_run_id=proposal.source_run_id,
        source_task_id=proposal.source_task_id,
        target_agent_id=proposal.target_agent_id,
        target_team_id=proposal.target_team_id,
        target_project_id=proposal.target_project_id,
        sheet=proposal.payload.get("sheet"),
        changes=changes,
        new_skills=[
            SkillDraftRead(id=s.id, name=s.name, description=s.description)
            for s in proposals.new_skills(db, proposal)
        ],
        applied_fields=list(proposal.applied_fields or []),
        created_at=proposal.created_at,
        decided_at=proposal.decided_at,
    )


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: DbSession) -> ProposalRead:
    return read_proposal(db, proposals.get(db, proposal_id))


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, payload: Approve, request: Request, db: DbSession) -> Applied:
    proposal = proposals.get(db, proposal_id)
    applied = proposals.approve(
        db,
        request.app.state.run_manager.skill_library,
        proposal,
        fields=payload.fields,
        choices=payload.choices,
        skip_skills=payload.skip_skills,
    )
    db.commit()
    knowledge = getattr(request.app.state, "knowledge", None)
    if knowledge is not None:  # linked documents wait to be processed
        knowledge.poke()
    return Applied(proposal=read_proposal(db, proposal), notes=applied.notes)


@router.post("/proposals/{proposal_id}/reject")
def reject(
    proposal_id: str, request: Request, db: DbSession, payload: Reject | None = None
) -> ProposalRead:
    proposal = proposals.get(db, proposal_id)
    proposals.reject(
        db,
        request.app.state.run_manager.skill_library,
        proposal,
        archive=bool(payload and payload.archive),
    )
    db.commit()
    return read_proposal(db, proposal)
