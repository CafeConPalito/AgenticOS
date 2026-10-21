"""The tools that let an agent walk the knowledge graph (phase 15, block 4): `knowledge_map`,
`related_knowledge`, `explore_knowledge` and `knowledge_path`, plus the «neighbours» line that
`search_knowledge` adds under each result.

They only read, and only what the agent may read: the documents of its levels that are accepted,
ready and not switched off (the same rule as the search). Like the other tools they answer in words,
never with an error, and keep inside a budget of tokens so a big library cannot flood a context.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from agentic_os.models import KnowledgeDoc, KnowledgeScope, Origin, Run
from agentic_os.services.knowledge import graph_search as walk
from agentic_os.services.knowledge import search, topics
from agentic_os.services.knowledge.agent_tools import find_document, scope_of
from agentic_os.services.knowledge.context import GENERATED, LEVELS, is_generated, short_id

MAP_TOKENS = 2_000
EXPLORE_TOKENS = 3_000
MAX_DOCS = 30
NEIGHBORS_SHOWN = 4
NO_DOCS = "No hay documentos de conocimiento para este proyecto y este agente."
_KINDS = {
    "": None,
    "all": None,
    "todo": None,
    "todos": None,
    "derived": frozenset({walk.DERIVES_FROM, walk.SOURCE_OF}),
    "derivado": frozenset({walk.DERIVES_FROM, walk.SOURCE_OF}),
    "derivados": frozenset({walk.DERIVES_FROM, walk.SOURCE_OF}),
    "related": frozenset({walk.RELATED}),
    "relacionado": frozenset({walk.RELATED}),
    "relacionados": frozenset({walk.RELATED}),
}
_ORIGINS = {
    "": None,
    "all": None,
    "todo": None,
    "user": Origin.USER,
    "usuario": Origin.USER,
    "agent": Origin.AGENT,
    "agente": Origin.AGENT,
}
_LEVELS = {
    "": None,
    "general": KnowledgeScope.GENERAL,
    "project": KnowledgeScope.PROJECT,
    "proyecto": KnowledgeScope.PROJECT,
    "agent": KnowledgeScope.AGENT,
    "agente": KnowledgeScope.AGENT,
}


def tokens_of(text: str) -> int:
    return (len(text) + 3) // 4


@dataclass
class View:
    """The part of the library an agent may reach, and the links among its documents."""

    docs: list[KnowledgeDoc]
    by_id: dict[str, KnowledgeDoc]
    graph: walk.Adjacency
    has_meaning: bool  # at least one «related» link exists

    @classmethod
    def open(cls, db: Session, run: Run) -> View:
        project_id, agent_ids = scope_of(db, run)
        return cls.open_for(db, project_id, agent_ids)

    @classmethod
    def open_for(cls, db: Session, project_id: str | None, agent_ids: list[str]) -> View:
        docs = search.visible_docs(db, project_id, agent_ids)
        graph = walk.Adjacency.build(db, docs)
        return cls(docs, {d.id: d for d in docs}, graph, bool(graph.related))

    def title(self, doc_id: str) -> str:
        return self.by_id[doc_id].title


def describe(doc: KnowledgeDoc, summary: bool = True) -> str:
    facts = [LEVELS.get(doc.scope, doc.scope)]
    if is_generated(doc):
        facts.append(GENERATED)
    line = f"**{doc.title}** `[{short_id(doc)}]` · {' · '.join(facts)}"
    if summary and doc.summary:
        line += f"\n  {doc.summary}"
    return line


def _reason(link: walk.Link) -> str:
    if link.kind == walk.DERIVES_FROM:
        return "derivado de"
    if link.kind == walk.SOURCE_OF:
        return "origen de"
    return f"relacionado {link.weight:.2f}".replace(".", ",")


def _chain(view: View, reached: walk.Reached) -> str:
    """«A» —relacionado 0,46→ «B»: how a document was reached."""
    parts = [f"«{view.title(reached.chain[0][0])}»"]
    for node, link in reached.chain[1:]:
        parts.append(f"—{_reason(link)}→ «{view.title(node)}»")
    return " ".join(parts)


def _options(
    kinds: str, origin: str, level: str
) -> tuple[frozenset | None, Origin | None, str | None, str]:
    """(link kinds, origin, level, the problem in words — empty when the three are fine)."""
    if kinds.strip().lower() not in _KINDS:
        return None, None, None, "`kinds` debe ser «all», «derived» o «related»."
    if origin.strip().lower() not in _ORIGINS:
        return None, None, None, "`origin` debe ser «all», «user» o «agent»."
    if level.strip().lower() not in _LEVELS:
        return None, None, None, "`level` debe ser «general», «project» o «agent» (o vacío)."
    return (
        _KINDS[kinds.strip().lower()],
        _ORIGINS[origin.strip().lower()],
        _LEVELS[level.strip().lower()],
        "",
    )


def _allowed(view: View, origin: Origin | None, level: str | None) -> frozenset[str] | None:
    if origin is None and level is None:
        return None
    return frozenset(
        d.id
        for d in view.docs
        if (origin is None or d.origin == origin) and (level is None or d.scope == level)
    )


def neighbors_line(view: View, doc: KnowledgeDoc, limit: int = NEIGHBORS_SHOWN) -> str:
    """«Vecinos: A (derivado de), B (relacionado 0,52)» for a search result; empty when none."""
    found = [link for link in view.graph.of(doc.id) if link.other in view.by_id][:limit]
    if not found:
        return ""
    items = ", ".join(
        f"{view.title(link.other)} `[{short_id(view.by_id[link.other])}]` ({_reason(link)})"
        for link in found
    )
    return f"Vecinos: {items}"


# ----------------------------------------------------------------------------- the map
def knowledge_map(db: Session, run: Run, topic: str = "") -> tuple[str, str]:
    """(answer, detail): the topics of the library this agent reads, or the documents of one."""
    view = View.open(db, run)
    if not view.docs:
        return NO_DOCS, "sin documentos"
    titles = {d.id: d.title for d in view.docs}
    found = view.graph.topics(titles)
    note = (
        ""
        if view.has_meaning
        else "(Sin modelo de significado o sin documentos parecidos: el mapa solo muestra los "
        "vínculos «derivado de».)\n\n"
    )
    if topic.strip():
        chosen = _pick_topic(found, topic)
        if chosen is None:
            names = "\n".join(f"- {t.id + 1}. {t.name}" for t in found)
            return (
                f"No encuentro el tema «{topic}». Los que hay:\n{names}",
                f"{topic[:60]} → no existe",
            )
        lines = [
            f"## Tema {chosen.id + 1}: {chosen.name}",
            f"{len(chosen.doc_ids)} documentos.",
            "",
        ]
        lines += [describe(view.by_id[i]) for i in chosen.doc_ids]
        around = [found[n] for n in chosen.neighbors]
        if around:
            lines += ["", "Cerca de: " + "; ".join(f"{t.id + 1}. {t.name}" for t in around)]
        text = _fit(lines, MAP_TOKENS)
        return text + note, f"tema {chosen.name[:80]} · {len(chosen.doc_ids)} documentos"
    lines = [f"## Mapa del conocimiento: {len(view.docs)} documentos en {len(found)} temas", ""]
    for t in found:
        mark = f"{t.id + 1}. {t.name}"
        lines.append(f"### {mark} — {len(t.doc_ids)} documento{'s' if len(t.doc_ids) != 1 else ''}")
        main = ", ".join(
            f"{view.title(i)} `[{short_id(view.by_id[i])}]`"
            + (" (generado por agente)" if is_generated(view.by_id[i]) else "")
            for i in t.central
        )
        lines.append(f"Principales: {main}")
        if t.neighbors:
            lines.append(
                "Cerca de: " + "; ".join(f"{found[n].id + 1}. {found[n].name}" for n in t.neighbors)
            )
        lines.append("")
    lines.append(
        'Pide un tema con `knowledge_map(topic="2")` o recorre desde un documento con '
        "`explore_knowledge`."
    )
    return _fit(lines, MAP_TOKENS) + note, f"{len(view.docs)} documentos · {len(found)} temas"


def _pick_topic(found: Sequence[topics.Topic], wanted: str) -> topics.Topic | None:
    wanted = wanted.strip()
    if wanted.isdigit() and 1 <= int(wanted) <= len(found):
        return found[int(wanted) - 1]
    plain = search._plain(wanted)
    matches = [t for t in found if plain in search._plain(t.name)]
    return matches[0] if matches else None


def _fit(lines: list[str], budget: int) -> str:
    """The lines that fit in `budget` tokens; if some do not, a note says how many were left out."""
    out, used = [], 0
    for index, line in enumerate(lines):
        cost = tokens_of(line) + 1
        if used + cost > budget:
            left = len([x for x in lines[index:] if x.strip()])
            out.append(f"(… {left} líneas más; acota con los filtros para verlas)")
            break
        out.append(line)
        used += cost
    return "\n".join(out).strip()


# ------------------------------------------------------------------------ the neighbours
def related_knowledge(
    db: Session, run: Run, document: str, kinds: str = "all", origin: str = "all"
) -> tuple[str, str]:
    view = View.open(db, run)
    if not view.docs:
        return NO_DOCS, "sin documentos"
    doc, problem = find_document(view.docs, document)
    if doc is None:
        return problem, f"{document[:100]} → no encontrado"
    link_kinds, only_origin, _, bad = _options(kinds, origin, "")
    if bad:
        return bad, "opciones no válidas"
    found = [
        link
        for link in view.graph.of(doc.id)
        if (link_kinds is None or link.kind in link_kinds)
        and (only_origin is None or view.by_id[link.other].origin == only_origin)
    ]
    if not found:
        return (
            f"«{doc.title}» no tiene vecinos con esos filtros. Busca con `search_knowledge` o "
            "mira el mapa con `knowledge_map`.",
            f"{doc.title[:80]} → sin vecinos",
        )
    lines = [f"## Vecinos de «{doc.title}»", ""]
    for link in found[:MAX_DOCS]:
        other = view.by_id[link.other]
        lines.append(f"- {_reason(link)} → {describe(other)}")
    return _fit(
        lines, EXPLORE_TOKENS
    ), f"{doc.title[:80]} → {len(found)} vecinos ({kinds}, {origin})"


# ------------------------------------------------------------------------- exploring
def explore_knowledge(
    db: Session,
    service,
    run: Run,
    document: str = "",
    query: str = "",
    hops: int = 2,
    kinds: str = "all",
    origin: str = "all",
    level: str = "",
    max_docs: int = 15,
) -> tuple[str, str]:
    view = View.open(db, run)
    if not view.docs:
        return NO_DOCS, "sin documentos"
    link_kinds, only_origin, only_level, bad = _options(kinds, origin, level)
    if bad:
        return bad, "opciones no válidas"
    project_id, agent_ids = scope_of(db, run)
    starts, where = _starting_points(db, service, project_id, agent_ids, view, document, query)
    if isinstance(starts, str):
        return starts, where
    hops = max(1, min(int(hops), walk.MAX_HOPS))
    max_docs = max(1, min(int(max_docs), MAX_DOCS))
    reached = walk.explore(
        view.graph,
        [d.id for d in starts],
        hops=hops,
        kinds=link_kinds,
        allowed=_allowed(view, only_origin, only_level),
        max_docs=max_docs + len(starts),
    )
    options = ", ".join(
        part
        for part in (
            f"{hops} saltos",
            f"kinds={kinds}" if kinds.strip() not in ("", "all") else "",
            f"origin={origin}" if origin.strip() not in ("", "all") else "",
            f"level={level}" if level.strip() else "",
        )
        if part
    )
    detail = f"{where[:80]} → {len(reached)} documentos ({options})"
    return _render_exploration(view, reached, starts, where, hops), detail


def _starting_points(
    db, service, project_id: str | None, agent_ids: list[str], view: View, document: str, query: str
):
    """(documents to start from, how to call them) or (a refusal in words, detail)."""
    if document.strip():
        doc, problem = find_document(view.docs, document)
        if doc is not None:
            return [doc], f"«{doc.title}»"
        if not query.strip():  # with a question too, it is searched when no document has that name
            return problem, f"{document[:100]} → no encontrado"
    if query.strip():
        hits = service.search(db, query, project_id, agent_ids, 8, use_graph=False)
        starts = list(dict.fromkeys(h.doc.id for h in hits))[:3]
        if not starts:
            return (
                f"No encontré nada en el conocimiento para «{query}», así que no hay desde dónde "
                "explorar. Prueba con otras palabras o mira el mapa con `knowledge_map`.",
                f"{query[:100]} → nada",
            )
        return [view.by_id[i] for i in starts if i in view.by_id], f"la búsqueda «{query[:60]}»"
    return "Indica un `document` o una `query` desde donde explorar.", "sin punto de partida"


def _render_exploration(
    view: View, reached: list[walk.Reached], starts: list[KnowledgeDoc], where: str, hops: int
) -> str:
    others = [r for r in reached if r.depth > 0]
    lines = [
        f"## Exploración desde {where}: {len(others)} documento"
        f"{'s' if len(others) != 1 else ''} a {hops} salto{'s' if hops != 1 else ''} como máximo",
        "",
    ]
    for number, r in enumerate(reached, 1):
        doc = view.by_id[r.id]
        if r.depth == 0:
            lines.append(f"{number}. {describe(doc)} — punto de partida")
        else:
            lines.append(
                f"{number}. {describe(doc)} — a {r.depth} salto{'s' if r.depth != 1 else ''}, "
                f"fuerza {r.strength:.2f}".replace(".", ",")
            )
            lines.append(f"  camino: {_chain(view, r)}")
    if not others:
        lines += ["", "No hay vecinos con esos filtros."]
    lines += ["", "Lee uno con `read_knowledge` (su título o su identificador)."]
    return _fit(lines, EXPLORE_TOKENS)


def explore_text_for_results(db: Session, view: View, hit_doc_ids: list[str]) -> str:
    """The sub-graph around a search's best results, for `search_knowledge(graph="explore")`."""
    starts = [view.by_id[i] for i in list(dict.fromkeys(hit_doc_ids))[:3] if i in view.by_id]
    if not starts:
        return ""
    reached = walk.explore(view.graph, [d.id for d in starts], hops=2, max_docs=12)
    if all(r.depth == 0 for r in reached):
        return ""
    return _render_exploration(view, reached, starts, "los mejores resultados", 2).replace(
        "## Exploración", "### Grafo cercano a los resultados\nExploración", 1
    )


def explore_data(
    db: Session,
    service,
    project_id: str | None,
    agent_ids: list[str],
    *,
    document: str = "",
    query: str = "",
    hops: int = 2,
    kinds: str = "all",
    origin: str = "all",
    level: str = "",
    max_docs: int = 15,
) -> tuple[list[dict], str]:
    """(the documents reached, a refusal in words — empty when it went well): the same
    exploration the agents get, as data, for the search tester."""
    view = View.open_for(db, project_id, agent_ids)
    if not view.docs:
        return [], NO_DOCS
    link_kinds, only_origin, only_level, bad = _options(kinds, origin, level)
    if bad:
        return [], bad
    starts, _ = _starting_points(db, service, project_id, agent_ids, view, document, query)
    if isinstance(starts, str):
        return [], starts
    reached = walk.explore(
        view.graph,
        [d.id for d in starts],
        hops=max(1, min(int(hops), walk.MAX_HOPS)),
        kinds=link_kinds,
        allowed=_allowed(view, only_origin, only_level),
        max_docs=max(1, min(int(max_docs), MAX_DOCS)) + len(starts),
    )
    return [
        {
            "id": r.id,
            "title": view.title(r.id),
            "depth": r.depth,
            "strength": round(r.strength, 3),
            "path": [view.title(node) for node, _ in r.chain],
            "reasons": [_reason(link) for _, link in r.chain[1:] if link is not None],
        }
        for r in reached
    ], ""


# --------------------------------------------------------------------------- the path
def knowledge_path(
    db: Session, run: Run, source: str, target: str, max_hops: int = 4
) -> tuple[str, str]:
    view = View.open(db, run)
    if not view.docs:
        return NO_DOCS, "sin documentos"
    first, problem = find_document(view.docs, source)
    if first is None:
        return f"En `source`: {problem}", f"{source[:80]} → no encontrado"
    last, problem = find_document(view.docs, target)
    if last is None:
        return f"En `target`: {problem}", f"{target[:80]} → no encontrado"
    max_hops = max(1, min(int(max_hops), walk.MAX_PATH_HOPS))
    if first.id == last.id:
        return "Son el mismo documento.", f"{first.title[:80]} → mismo"
    found = walk.shortest_path(view.graph, first.id, last.id, max_hops)
    if found is None:
        return (
            f"No hay camino entre «{first.title}» y «{last.title}» en {max_hops} saltos o menos "
            "(probablemente no tienen que ver). Prueba con `search_knowledge` para cada uno.",
            f"{first.title[:40]} ↔ {last.title[:40]} → sin camino",
        )
    lines = [f"## Camino de «{first.title}» a «{last.title}» ({found.depth} saltos)", ""]
    lines.append(_chain(view, found))
    lines.append("")
    for node, _ in found.chain:
        lines.append(f"- {describe(view.by_id[node])}")
    return _fit(
        lines, EXPLORE_TOKENS
    ), f"{first.title[:40]} → {last.title[:40]} · {found.depth} saltos"
