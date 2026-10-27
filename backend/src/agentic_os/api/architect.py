"""The Agent Architect (phase 19, plan §7): conversations, their messages and sheet, the live
events of one conversation, and Ajustes › Arquitecto."""

import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.api.proposals import read_proposal
from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.db.session import get_session
from agentic_os.models import ArchitectConversation, Proposal
from agentic_os.schemas.architect import (
    ArchitectSettingsRead,
    ArchitectSettingsWrite,
    ConversationCreate,
    ConversationRead,
    ConversationSummary,
    MessageRead,
    MessageWrite,
    ProposalRead,
    Reset,
    SheetPatch,
    SheetRead,
    Unlock,
)
from agentic_os.services.architect import config as architect_config
from agentic_os.services.architect import prompts
from agentic_os.services.architect.service import ArchitectService

router = APIRouter(tags=["architect"])
DbSession = Annotated[Session, Depends(get_session)]


def service(request: Request) -> ArchitectService:
    return request.app.state.architect


Architect = Annotated[ArchitectService, Depends(service)]


def _proposal_id(db: Session, conversation_id: str) -> str | None:
    return db.scalar(
        select(Proposal.id)
        .where(Proposal.conversation_id == conversation_id)
        .order_by(Proposal.created_at.desc())
    )


def _summary(db: Session, architect: ArchitectService, c: ArchitectConversation) -> dict:
    return {
        "id": c.id,
        "mode": c.mode,
        "title": c.title,
        "status": c.status,
        "state": architect.state(c.id),
        "agent_id": c.agent_id,
        "team_id": c.team_id,
        "project_id": c.project_id,
        "proposal_id": _proposal_id(db, c.id),
        "updated_at": c.updated_at,
    }


def _read(db: Session, architect: ArchitectService, c: ArchitectConversation) -> ConversationRead:
    return ConversationRead(
        **_summary(db, architect, c),
        cli=c.cli,
        model=c.model,
        run_id=c.run_id,
        messages=[MessageRead.model_validate(m) for m in architect.messages(db, c.id)],
        sheet=SheetRead(**architect.summary(db, c)),
    )


@router.get("/architect/conversations")
def list_conversations(db: DbSession, architect: Architect) -> list[ConversationSummary]:
    rows = db.scalars(
        select(ArchitectConversation)
        .where(ArchitectConversation.workspace_id == DEFAULT_WORKSPACE)
        .order_by(ArchitectConversation.updated_at.desc())
    )
    return [ConversationSummary(**_summary(db, architect, c)) for c in rows]


@router.post("/architect/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate, db: DbSession, architect: Architect
) -> ConversationRead:
    conversation = architect.create(
        db,
        payload.mode,
        agent_id=payload.agent_id,
        team_id=payload.team_id,
        project_id=payload.project_id,
        proposal_id=payload.proposal_id,
    )
    db.commit()
    return _read(db, architect, conversation)


@router.get("/architect/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: DbSession, architect: Architect) -> ConversationRead:
    return _read(db, architect, architect.get(db, conversation_id))


@router.delete("/architect/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, db: DbSession, architect: Architect) -> None:
    architect.delete(db, conversation_id)
    db.commit()


@router.post("/architect/conversations/{conversation_id}/messages", status_code=201)
def send_message(
    conversation_id: str, payload: MessageWrite, db: DbSession, architect: Architect
) -> MessageRead:
    """Writes the message into the conversation's CLI (starting or resuming it). The reply
    arrives through the events."""
    message = architect.send(db, conversation_id, payload.text)
    db.commit()
    return MessageRead.model_validate(message)


@router.post("/architect/conversations/{conversation_id}/interrupt")
def interrupt(conversation_id: str, architect: Architect) -> dict:
    return {"interrupted": architect.interrupt(conversation_id)}


@router.post("/architect/conversations/{conversation_id}/reset")
def reset(
    conversation_id: str, db: DbSession, architect: Architect, payload: Reset | None = None
) -> ConversationRead:
    architect.reset(db, conversation_id, clear_sheet=bool(payload and payload.clear_sheet))
    db.commit()
    return _read(db, architect, architect.get(db, conversation_id))


@router.post("/architect/conversations/{conversation_id}/sleep", status_code=204)
def sleep(conversation_id: str, architect: Architect) -> None:
    architect.sleep(conversation_id)


@router.patch("/architect/conversations/{conversation_id}/sheet")
def patch_sheet(
    conversation_id: str, payload: SheetPatch, db: DbSession, architect: Architect
) -> SheetRead:
    """An edit by hand: what passes is stored and locked for the Architect."""
    answer = architect.patch_sheet(db, conversation_id, payload.patch, payload.agent_ref)
    db.commit()
    return SheetRead(**answer)


@router.post("/architect/conversations/{conversation_id}/unlock")
def unlock(conversation_id: str, payload: Unlock, db: DbSession, architect: Architect) -> SheetRead:
    architect.unlock(db, conversation_id, payload.fields)
    db.commit()
    return SheetRead(**architect.summary(db, architect.get(db, conversation_id)))


@router.post("/architect/conversations/{conversation_id}/propose", status_code=201)
def propose(conversation_id: str, db: DbSession, architect: Architect) -> ProposalRead:
    """«Crear borrador» / «Crear propuesta»."""
    proposal = architect.propose(db, conversation_id)
    db.commit()
    return read_proposal(db, proposal)


@router.websocket("/architect/conversations/{conversation_id}/events")
async def events(websocket: WebSocket, conversation_id: str) -> None:
    """`message` (a whole message), `block` (a piece of the reply in progress), `sheet` (the
    sheet changed: sheet, issues, progress, locked) and `state` (starting · thinking · idle ·
    asleep), only those of this conversation."""
    await websocket.accept()
    hub = websocket.app.state.architect.events
    queue = hub.subscribe()
    listening = asyncio.ensure_future(websocket.receive_text())  # only to notice the client leaving
    try:
        while True:
            getting = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getting, listening}, return_when=asyncio.FIRST_COMPLETED)
            if listening in done:
                getting.cancel()
                listening.result()  # raises WebSocketDisconnect when the client left
                listening = asyncio.ensure_future(websocket.receive_text())
                continue
            event = getting.result()
            if event.get("conversation_id") == conversation_id:
                await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        listening.cancel()
        with contextlib.suppress(Exception):
            await websocket.close()


# --------------------------------------------------------------------------------- settings
def _settings_read(db: Session) -> ArchitectSettingsRead:
    settings = architect_config.load(db)
    return ArchitectSettingsRead(
        cli=settings.cli,
        account_id=settings.account_id,
        model=settings.model,
        instructions=settings.instructions,
        default_instructions=prompts.BASE,
        idle_minutes=settings.idle_minutes,
        max_live=settings.max_live,
    )


@router.get("/settings/architect")
def get_settings(db: DbSession) -> ArchitectSettingsRead:
    return _settings_read(db)


@router.put("/settings/architect")
def put_settings(payload: ArchitectSettingsWrite, db: DbSession) -> ArchitectSettingsRead:
    architect_config.save(db, payload.model_dump(exclude_none=True))
    db.commit()
    return _settings_read(db)
