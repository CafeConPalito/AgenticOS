"""What an agent knows about the library when its run starts (phase 14, block 6): an index of the
documents it may read, the whole text of the ones that fit in the context budget, and where to
find the pictures.

Who sees what: the general documents, the project's and the agent's own (a subagent also sees its
parent's). The documents that go whole are the ones marked «always in context» and the small
«automatic» ones, smallest first, while the budget lasts; the rest are for `search_knowledge`.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_os.models import (
    KnowledgeDoc,
    KnowledgeImage,
    KnowledgeMode,
    KnowledgeScope,
    Origin,
)
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import search

_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(kimg:(?P<n>\d+)\)")
LEVELS = {
    KnowledgeScope.GENERAL: "general",
    KnowledgeScope.PROJECT: "del proyecto",
    KnowledgeScope.AGENT: "de agente",
}
HEADER = """\
## Conocimiento
Documentos que la persona ha puesto a tu alcance. Los marcados «completo» los tienes más abajo. \
Para los demás, o para comprobar un dato, usa `search_knowledge` (busca por significado y por \
códigos exactos) y `read_knowledge` (lee un documento, una página, una hoja o un apartado). \
Las imágenes salen como rutas de fichero que puedes abrir."""
GENERATED = "generado por agente"
GENERATED_NOTE = (
    "Los marcados «generado por agente» son síntesis que otro agente propuso y la persona "
    "aceptó: fíate más de las fuentes originales."
)
PROPOSE_NOTE = (
    "Si aprendes algo nuevo y comprobado que aquí no está, puedes proponerlo con "
    "`propose_knowledge` (nunca modifica un documento: crea otro vinculado, y la persona lo "
    "revisa antes de que nadie lo use)."
)


GRAPH_NOTE = (
    "Los documentos están enlazados (derivados de otros, o parecidos): `knowledge_map` muestra "
    "los temas, `explore_knowledge` recorre los vecinos de un documento o de una búsqueda y "
    "`related_knowledge` lista los de uno."
)
TOPICS_SHOWN = 8
TOPIC_NAME_MAX = 40


def topics_line(db: Session, docs: list[KnowledgeDoc]) -> str:
    """«Temas: Celery (4), Docker (3)…» for the index; empty when nothing is linked."""
    from agentic_os.services.knowledge import graph_search  # it imports this package's search

    graph = graph_search.Adjacency.build(db, docs)
    if not graph.related and not graph.derived:
        return ""
    found = [t for t in graph.topics({d.id: d.title for d in docs}) if not t.loose]
    if not found:
        return ""
    shown = ", ".join(
        f"{t.name.split(' · ')[0][:TOPIC_NAME_MAX]} ({len(t.doc_ids)})"
        for t in found[:TOPICS_SHOWN]
    )
    more = f" y {len(found) - TOPICS_SHOWN} más" if len(found) > TOPICS_SHOWN else ""
    return f"Temas: {shown}{more}."


def is_generated(doc: KnowledgeDoc) -> bool:
    return doc.origin == Origin.AGENT


def images_folder(data_dir: Path) -> Path:
    return Path(data_dir) / "knowledge" / "images"


def run_images_folder(data_dir: Path, run_id: str) -> Path:
    return Path(data_dir) / "knowledge" / "run-images" / run_id


def prepare_folders(data_dir: Path, run_id: str) -> tuple[Path, Path]:
    """The two folders a run may need to read pictures from, created so the CLIs can be given
    them (`--add-dir`): the stored pictures and this run's own copies."""
    stored, copies = images_folder(data_dir), run_images_folder(data_dir, run_id)
    stored.mkdir(parents=True, exist_ok=True)
    copies.mkdir(parents=True, exist_ok=True)
    return stored, copies


def clean_run(data_dir: Path, run_id: str) -> None:
    shutil.rmtree(run_images_folder(data_dir, run_id), ignore_errors=True)


def clean_all(data_dir: Path) -> None:
    """At start-up no run is alive: every copy left over is garbage."""
    shutil.rmtree(Path(data_dir) / "knowledge" / "run-images", ignore_errors=True)


def short_id(doc: KnowledgeDoc) -> str:
    return doc.id[:8]


# ------------------------------------------------------------------------------ pictures
def resolve_images(
    db: Session, data_dir: Path, run_id: str, doc: KnowledgeDoc, markdown: str
) -> str:
    """Turns `![…](kimg:N)` into the path of the picture. A picture the user added is read from
    where they keep it, so it is copied for this run (the agents' folders do not include it)."""
    if "kimg:" not in markdown:
        return markdown
    rows = {
        image.ord: image
        for image in db.scalars(select(KnowledgeImage).where(KnowledgeImage.doc_id == doc.id))
    }

    def replace(match: re.Match[str]) -> str:
        image = rows.get(int(match.group("n")))
        alt = match.group("alt")
        if image is None:
            return ""
        path = _path_of(data_dir, run_id, doc, image)
        if path is None:
            return f"[{alt or 'imagen'}: no disponible]"
        shown = str(path)
        return f"![{alt}](<{shown}>)" if " " in shown else f"![{alt}]({shown})"

    return _IMAGE.sub(replace, markdown)


def _path_of(data_dir: Path, run_id: str, doc: KnowledgeDoc, image: KnowledgeImage) -> Path | None:
    if image.file:
        stored = images_folder(data_dir) / image.file
        return stored if stored.is_file() else None
    if not doc.path or not Path(doc.path).is_file():
        return None
    folder = run_images_folder(data_dir, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{doc.id[:8]}-{image.ord}{Path(doc.path).suffix.lower()}"
    if not copy.exists():
        shutil.copyfile(doc.path, copy)
    return copy


# ------------------------------------------------------------------------------- section
def plan(docs: list[KnowledgeDoc], context_budget: int, small_doc_tokens: int) -> set[str]:
    """Which documents go whole into the context: «always» ones first, then the small «automatic»
    ones from the smallest, while they fit in the budget."""
    whole = [d for d in docs if d.mode == KnowledgeMode.CONTEXT]
    used = sum(d.md_tokens for d in whole)
    small = sorted(
        (d for d in docs if d.mode == KnowledgeMode.AUTO and d.md_tokens <= small_doc_tokens),
        key=lambda d: (d.md_tokens, d.created_at or datetime.min),
    )
    for doc in small:
        if used + doc.md_tokens <= context_budget:
            whole.append(doc)
            used += doc.md_tokens
    return {d.id for d in whole}


def knowledge_section(
    db: Session,
    data_dir: Path,
    run_id: str,
    project_id: str | None,
    agent_ids: list[str],
) -> str:
    """The «Conocimiento» block of the instructions; empty when there is nothing to read."""
    docs = search.visible_docs(db, project_id, agent_ids)
    if not docs:
        return ""
    limits = knowledge_config.load(db)
    whole = plan(docs, limits.context_budget, limits.small_doc_tokens)
    header = HEADER
    if any(is_generated(d) for d in docs):
        header += " " + GENERATED_NOTE
    if limits.proposals_enabled:
        header += " " + PROPOSE_NOTE
    topics = topics_line(db, docs)
    if topics:
        header += " " + GRAPH_NOTE + " " + topics
    lines = [header, ""]
    for doc in docs:
        facts = [
            LEVELS.get(doc.scope, doc.scope),
            "completo" if doc.id in whole else "solo búsqueda",
            f"~{doc.md_tokens} tokens",
        ]
        if is_generated(doc):
            facts.insert(1, GENERATED)
        if doc.image_count:
            facts.append("1 imagen" if doc.image_count == 1 else f"{doc.image_count} imágenes")
        extra = f" — {doc.description}" if doc.description else ""
        lines.append(f"- **{doc.title}** `[{short_id(doc)}]` ({', '.join(facts)}){extra}")
    for doc in docs:
        if doc.id in whole:
            body = resolve_images(db, data_dir, run_id, doc, doc.markdown)
            lines += ["", f"### {doc.title}", "", body.strip()]
    return "\n".join(lines)
