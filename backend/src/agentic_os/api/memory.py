from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from agentic_os.api.projects import get_project_or_404
from agentic_os.db.session import get_session
from agentic_os.errors import NotFound
from agentic_os.models import AuthorKind, MemoryNote
from agentic_os.schemas.memory import MemoryRead, NoteRead, NoteWrite
from agentic_os.services.memory import MEMORY_LIMIT, list_notes, memory_size

router = APIRouter(tags=["memory"])
DbSession = Annotated[Session, Depends(get_session)]


def _note(session: Session, project_id: str, note_id: str) -> MemoryNote:
    get_project_or_404(session, project_id)
    note = session.get(MemoryNote, note_id)
    if note is None or note.project_id != project_id:
        raise NotFound("note")
    return note


@router.get("/projects/{project_id}/memory")
def get_memory(project_id: str, session: DbSession) -> MemoryRead:
    get_project_or_404(session, project_id)
    notes = list_notes(session, project_id)
    return MemoryRead(
        notes=[NoteRead.model_validate(n) for n in notes],
        size=memory_size(notes),
        limit=MEMORY_LIMIT,
    )


@router.post("/projects/{project_id}/memory", status_code=status.HTTP_201_CREATED)
def add_note(project_id: str, payload: NoteWrite, session: DbSession) -> NoteRead:
    get_project_or_404(session, project_id)
    note = MemoryNote(project_id=project_id, author_kind=AuthorKind.USER, text=payload.text)
    session.add(note)
    session.commit()
    return NoteRead.model_validate(note)


@router.patch("/projects/{project_id}/memory/{note_id}")
def edit_note(project_id: str, note_id: str, payload: NoteWrite, session: DbSession) -> NoteRead:
    note = _note(session, project_id, note_id)
    note.text = payload.text
    session.commit()
    return NoteRead.model_validate(note)


@router.delete("/projects/{project_id}/memory/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(project_id: str, note_id: str, session: DbSession) -> None:
    session.delete(_note(session, project_id, note_id))
    session.commit()
