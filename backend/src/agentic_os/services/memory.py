"""The project memory: notes the agents (write_project_memory) and the user write, injected
into every run of the project."""

from __future__ import annotations

from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from agentic_os.models import AuthorKind, MemoryNote

# What the agents see of the memory: the most recent notes, up to this many characters. The UI
# warns when the memory is longer (older notes are left out of the context).
MEMORY_LIMIT = 12_000
USER_AUTHOR = "Tú"


def list_notes(db: Session, project_id: str) -> list[MemoryNote]:
    query = (
        select(MemoryNote)
        .where(MemoryNote.project_id == project_id)
        # Two notes in the same clock tick (15 ms on Windows) keep the order they were written
        # in: the random id put them either way (phase 21, a flaky test). SQLite's rowid.
        .order_by(MemoryNote.created_at, literal_column("rowid"))
    )
    return list(db.scalars(query))


def add_agent_note(
    db: Session, project_id: str, agent_id: str | None, agent_name: str, text: str
) -> MemoryNote:
    note = MemoryNote(
        project_id=project_id,
        author_kind=AuthorKind.AGENT,
        author_name=agent_name,
        agent_id=agent_id,
        text=text.strip(),
    )
    db.add(note)
    return note


def render_note(note: MemoryNote) -> str:
    author = note.author_name if note.author_kind == AuthorKind.AGENT else USER_AUTHOR
    stamp = note.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
    return f"### {stamp} · {author}\n{note.text.strip()}"


def render_memory(notes: list[MemoryNote], limit: int = MEMORY_LIMIT) -> str:
    """The notes, oldest first, keeping the most recent ones that fit in `limit`."""
    blocks: list[str] = []
    size = 0
    for note in reversed(notes):
        block = render_note(note)
        if blocks and size + len(block) > limit:
            blocks.append("[…] (hay notas más antiguas que no se muestran)")
            break
        if not blocks and len(block) > limit:  # a single huge note: keep its end
            block = "[…] " + block[-limit:]
        blocks.append(block)
        size += len(block) + 2
    return "\n\n".join(reversed(blocks))


def memory_size(notes: list[MemoryNote]) -> int:
    return sum(len(render_note(n)) + 2 for n in notes)
