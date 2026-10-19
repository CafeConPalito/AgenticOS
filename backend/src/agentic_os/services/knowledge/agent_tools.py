"""The two tools of the `agentic-os` MCP server that read the library (phase 14, block 6).

`search_knowledge(query)` returns the passages that best answer the question, and
`read_knowledge(document)` returns a document (or a page, a sheet, a slide or a section of it).
Both answer in Markdown the agent can read directly, and both answer *in words* when something
is wrong (no such document, nothing found) instead of failing, so the agent can adjust.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from agentic_os.models import KnowledgeDoc, Run
from agentic_os.services.knowledge import search
from agentic_os.services.knowledge.context import LEVELS, resolve_images, short_id
from agentic_os.services.knowledge.search import _plain  # accent-blind comparison

PART_TOKENS = 6_000  # a document longer than this is read in parts
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)
_MARKER = re.compile(r"<!--\s*(page|Slide number|sheet):\s*([^>]*?)\s*-->")
_PAGE = re.compile(r"^(?:p\.?|pág\.?|página|pagina|page)?\s*(\d+)(?:\s*[-\u2013]\s*(\d+))?$", re.I)
_SLIDE = re.compile(r"^(?:diapositiva|slide|filmina)\s*(\d+)$", re.I)
_SHEET = re.compile(r"^(?:hoja|sheet)\s+(.+)$", re.I)


def scope_of(db: Session, run: Run) -> tuple[str | None, list[str]]:
    """(project, agents) a run reads for: its own agent and, for a subagent, its parent's."""
    agents = [run.agent_id] if run.agent_id else []
    if run.parent_run_id:
        parent = db.get(Run, run.parent_run_id)
        if parent is not None and parent.agent_id:
            agents.append(parent.agent_id)
    return run.project_id, agents


# ------------------------------------------------------------------------------- search
def search_knowledge(
    db: Session,
    service,
    data_dir: Path,
    run: Run,
    query: str,
    limit: int = search.DEFAULT_LIMIT,
) -> tuple[str, str]:
    """(the answer for the agent, a one-line detail for the run's events)."""
    project_id, agents = scope_of(db, run)
    if not search.visible_docs(db, project_id, agents):
        return (
            "No hay documentos de conocimiento para este proyecto y este agente.",
            "sin documentos",
        )
    hits = service.search(db, query, project_id, agents, limit)
    if not hits:
        return (
            f"No encontré nada en el conocimiento para «{query}». Prueba con otras palabras, "
            "con un código exacto, o lee un documento con `read_knowledge`.",
            f"{query[:100]} → nada",
        )
    parts = [f"## Resultados para «{query}»"]
    if service.embedding_model() is None:
        parts.append("(Búsqueda solo por palabras: no hay un modelo de significado descargado.)")
    for number, hit in enumerate(hits, 1):
        place = " · ".join(x for x in (hit.chunk.heading, hit.chunk.location) if x)
        body = resolve_images(db, data_dir, run.id, hit.doc, hit.text)
        parts.append(
            f"### {number}. {hit.doc.title}"
            + (f" — {place}" if place else "")
            + f"\n`[{short_id(hit.doc)}]` · {LEVELS.get(hit.doc.scope, hit.doc.scope)}\n\n{body}"
        )
    names = ", ".join(dict.fromkeys(h.doc.title for h in hits))
    return "\n\n".join(parts), f"{query[:100]} → {len(hits)} resultados: {names}"[:300]


# -------------------------------------------------------------------------------- read
def find_document(docs: Sequence[KnowledgeDoc], reference: str) -> tuple[KnowledgeDoc | None, str]:
    """The document `reference` names (its short id, its title, or a word of the title), or the
    reason it cannot be told."""
    wanted = reference.strip().strip("`[]")
    if not wanted:
        return None, "Indica qué documento quieres leer (su título o su identificador)."
    lowered = wanted.lower()
    by_id = [d for d in docs if len(lowered) >= 4 and d.id.lower().startswith(lowered)]
    if len(by_id) == 1:
        return by_id[0], ""
    plain = _plain(wanted)
    exact = [d for d in docs if _plain(d.title) == plain]
    candidates = exact or [d for d in docs if plain in _plain(d.title)]
    if len(candidates) == 1:
        return candidates[0], ""
    listing = "\n".join(f"- {d.title} `[{short_id(d)}]`" for d in (candidates or docs)[:30])
    if candidates:
        return None, f"«{wanted}» puede ser varios documentos; usa el identificador:\n{listing}"
    return None, f"No encuentro un documento llamado «{wanted}». Los que puedes leer:\n{listing}"


def _sections(markdown: str) -> list[tuple[str, str, int, int]]:
    """(kind, name, start, end) of every marked page, slide and sheet."""
    marks = list(_MARKER.finditer(markdown))
    found = []
    for position, mark in enumerate(marks):
        same = [m for m in marks[position + 1 :] if m.group(1) == mark.group(1)]
        end = same[0].start() if same else len(markdown)
        found.append((mark.group(1), mark.group(2), mark.end(), end))
    return found


def _by_heading(markdown: str, wanted: str) -> tuple[str, str] | None:
    plain = _plain(wanted)
    headings = list(_HEADING.finditer(markdown))
    for position, heading in enumerate(headings):
        if plain in _plain(heading.group(2)):
            level = len(heading.group(1))
            end = len(markdown)
            for later in headings[position + 1 :]:
                if len(later.group(1)) <= level:
                    end = later.start()
                    break
            return heading.group(2), markdown[heading.start() : end]
    return None


def select(markdown: str, location: str) -> tuple[str, str] | None:
    """(label, text) of the part of a document `location` names, or None. A page («12», «p. 12»,
    «12-14»), a slide («diapositiva 3»), a sheet («hoja Ventas») or a section title."""
    location = location.strip()
    sections = _sections(markdown)
    if match := _PAGE.match(location):
        first = int(match.group(1))
        last = int(match.group(2) or first)
        pages = [s for s in sections if s[0] == "page" and first <= int(s[1] or 0) <= last]
        if pages:
            label = f"p. {first}" if first == last else f"p. {first}-{last}"
            return label, "\n\n".join(markdown[s[2] : s[3]].strip() for s in pages)
    if match := _SLIDE.match(location):
        slides = [s for s in sections if s[0] == "Slide number" and s[1] == match.group(1)]
        if slides:
            return f"diapositiva {match.group(1)}", markdown[slides[0][2] : slides[0][3]].strip()
    if match := _SHEET.match(location):
        sheets = [s for s in sections if s[0] == "sheet" and _plain(s[1]) == _plain(match.group(1))]
        if sheets:
            return f"hoja {sheets[0][1]}", markdown[sheets[0][2] : sheets[0][3]].strip()
    if found := _by_heading(markdown, location):
        return found
    return None


def available(markdown: str) -> str:
    """What `location` can name in this document, for the agent that guessed wrong."""
    sections = _sections(markdown)
    lines = []
    pages = [s[1] for s in sections if s[0] == "page"]
    if pages:
        lines.append(f"- páginas: {pages[0]} a {pages[-1]}")
    slides = [s[1] for s in sections if s[0] == "Slide number"]
    if slides:
        lines.append(f"- diapositivas: {slides[0]} a {slides[-1]}")
    sheets = [s[1] for s in sections if s[0] == "sheet"]
    if sheets:
        lines.append("- hojas: " + ", ".join(sheets))
    headings = [h.group(2) for h in _HEADING.finditer(markdown)][:25]
    if headings:
        lines.append("- apartados: " + "; ".join(headings))
    return "\n".join(lines) or "- (el documento no tiene páginas ni apartados)"


def split_parts(text: str, size: int = PART_TOKENS * 4) -> list[str]:
    """The text in parts of about `PART_TOKENS`, cut at a blank line when there is one near."""
    if len(text) <= size:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n\n", start + size // 2, end)
            end = cut + 2 if cut != -1 else end
        parts.append(text[start:end])
        start = end
    return parts


def read_knowledge(
    db: Session,
    data_dir: Path,
    run: Run,
    document: str,
    location: str = "",
    part: int = 1,
) -> tuple[str, str]:
    """(the answer for the agent, a one-line detail for the run's events)."""
    project_id, agents = scope_of(db, run)
    docs = search.visible_docs(db, project_id, agents)
    if not docs:
        return (
            "No hay documentos de conocimiento para este proyecto y este agente.",
            "sin documentos",
        )
    doc, problem = find_document(docs, document)
    if doc is None:
        return problem, f"{document[:100]} → no encontrado"
    label, text = "", doc.markdown
    if location.strip():
        chosen = select(doc.markdown, location)
        if chosen is None:
            return (
                f"«{doc.title}» no tiene «{location}». Puedes pedir:\n{available(doc.markdown)}",
                f"{doc.title} · {location[:60]} → no encontrado",
            )
        label, text = chosen
    parts = split_parts(text)
    part = max(1, min(part, len(parts)))
    body = resolve_images(db, data_dir, run.id, doc, parts[part - 1])
    head = f"# {doc.title}" + (f" — {label}" if label else "")
    note = f"`[{short_id(doc)}]` · {LEVELS.get(doc.scope, doc.scope)}"
    if len(parts) > 1:
        note += f" · parte {part} de {len(parts)}"
        if part < len(parts):
            note += f" (pide `part={part + 1}` para seguir)"
    detail = (
        doc.title
        + (f" · {label}" if label else "")
        + (f" · parte {part}" if len(parts) > 1 else "")
    )
    return f"{head}\n{note}\n\n{body.strip()}", detail[:300]
