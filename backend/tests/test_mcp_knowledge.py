"""The knowledge tools of the agentic-os MCP server, driven by the official MCP client against a
real backend (phase 14, block 6). No model of embeddings is downloaded here, so the search is by
words; the meaning is tested in test_knowledge_search.py."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from test_mcp_server import call, events, mcp_url, seed_run
from test_scheduler_e2e import wait_until

from agentic_os.config import Settings
from agentic_os.models import Agent, Project, Run

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
GENERAL = (
    "# Reglas\n\nToda factura lleva el prefijo FAC. El código ERR_9001 indica un NIF inválido."
)
SECRET = "# Secreto\n\nLa clave de la caja fuerte de Blog es ZULU-77."
PERSONAL = "# Estilo\n\nEl Redactor escribe siempre con tono cercano y frases cortas."
LONG = "# Libro\n\n" + "\n\n".join(
    f"## Capítulo {n}\n\n" + " ".join(f"palabra{n}_{i}" for i in range(450)) for n in range(1, 10)
)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def add(server: LiveServer, paths: list[Path], **level) -> list[str]:
    response = httpx.post(
        f"{server.url}/api/knowledge/docs/files",
        json={"scope": "general", "paths": [str(p) for p in paths], **level},
        timeout=30,
    )
    assert response.status_code == 201, response.text
    return [item["doc"]["id"] for item in response.json()]


def wait_ready(server: LiveServer) -> None:
    def states() -> set[str]:
        return {
            d["status"] for d in httpx.get(f"{server.url}/api/knowledge/docs", timeout=30).json()
        }

    assert wait_until(lambda: states() <= {"ready"}, timeout=120), states()


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / "library" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def library(server: LiveServer, tmp_path: Path) -> dict:
    """A run of the project «Web» and the agent «Dev», with documents at every level and in
    another project."""
    run_id, token = seed_run(server, tmp_path)
    with server.db() as db:
        run = db.get(Run, run_id)
        project_id, agent_id = run.project_id, run.agent_id
        blog = Project(name="Blog", path=str(tmp_path / "blog"), path_key=str(tmp_path / "blog"))
        other = Agent(name="Otro", role="R")
        db.add_all([blog, other])
        db.commit()
        blog_id, other_id = blog.id, other.id
    manual = tmp_path / "library" / "manual.pdf"
    manual.parent.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "manual.pdf", manual)
    add(server, [write(tmp_path, "reglas.md", GENERAL)])
    add(server, [manual, write(tmp_path, "libro.md", LONG)], scope="project", project_id=project_id)
    add(server, [write(tmp_path, "secreto.md", SECRET)], scope="project", project_id=blog_id)
    add(server, [write(tmp_path, "estilo.md", PERSONAL)], scope="agent", agent_id=agent_id)
    add(
        server,
        [write(tmp_path, "ajeno.md", "# Ajeno\n\nTexto de otro agente.")],
        scope="agent",
        agent_id=other_id,
    )
    wait_ready(server)
    return {"run": run_id, "url": mcp_url(server, token), "agent": agent_id, "project": project_id}


# ---------------------------------------------------------------------------- search
def test_search_returns_the_passages_the_agent_may_see(server: LiveServer, library: dict):
    answer = call(library["url"], "search_knowledge", {"query": "cancelar la suscripción"})
    assert answer.startswith("## Resultados para «cancelar la suscripción»")
    assert "manual.pdf" in answer and "Cancelación de la suscripción" in answer
    assert "(Búsqueda solo por palabras" in answer  # no model downloaded here
    assert "`[" in answer  # the short id to read it later
    # What belongs to another project or another agent is not there.
    hidden = call(library["url"], "search_knowledge", {"query": "caja fuerte ZULU-77"})
    assert "secreto.md" not in hidden and "La clave de la caja fuerte" not in hidden
    other = call(library["url"], "search_knowledge", {"query": "Texto de otro agente"})
    assert "ajeno.md" not in other
    own = call(library["url"], "search_knowledge", {"query": "tono cercano frases cortas"})
    assert "estilo.md" in own and "tono cercano" in own


def test_an_exact_code_is_found_and_the_event_says_what_was_asked(
    server: LiveServer, library: dict
):
    answer = call(library["url"], "search_knowledge", {"query": "ERR_9001"})
    assert "reglas.md" in answer and "NIF inválido" in answer
    detail = [d for n, d in events(server, library["run"]) if n == "search_knowledge"][-1]
    assert detail.startswith("ERR_9001 → 1 resultados") and "reglas.md" in detail


def test_nothing_found_is_answered_in_words(server: LiveServer, library: dict):
    nothing = call(library["url"], "search_knowledge", {"query": "zzqx wwvk"})
    assert "No encontré nada" in nothing and "read_knowledge" in nothing
    detail = [d for n, d in events(server, library["run"]) if n == "search_knowledge"][-1]
    assert detail.endswith("→ nada")


def test_an_agent_with_no_documents_is_told_so(server: LiveServer, tmp_path: Path):
    _, token = seed_run(server, tmp_path)  # a library with nothing in it
    url = mcp_url(server, token)
    assert call(url, "search_knowledge", {"query": "lo que sea"}).startswith(
        "No hay documentos de conocimiento"
    )
    assert call(url, "read_knowledge", {"document": "x"}).startswith(
        "No hay documentos de conocimiento"
    )
    assert "## Conocimiento" not in call(url, "get_context")  # and no empty section


# ----------------------------------------------------------------------------- read
def test_a_document_is_read_by_title_or_by_its_short_id(server: LiveServer, library: dict):
    by_title = call(library["url"], "read_knowledge", {"document": "reglas"})
    assert by_title.startswith("# reglas.md") and "prefijo FAC" in by_title
    short = by_title.split("`[")[1].split("]`")[0]
    assert call(library["url"], "read_knowledge", {"document": short}) == by_title


def test_a_page_a_heading_and_parts_of_a_long_document(server: LiveServer, library: dict):
    page = call(library["url"], "read_knowledge", {"document": "manual.pdf", "location": "p. 2"})
    assert page.startswith("# manual.pdf — p. 2") and "<!--" not in page
    two_pages = call(library["url"], "read_knowledge", {"document": "manual", "location": "1-2"})
    assert "p. 1-2" in two_pages.splitlines()[0]
    section = call(
        library["url"], "read_knowledge", {"document": "libro", "location": "capítulo 4"}
    )
    assert "palabra4_0" in section and "palabra3_0" not in section and "palabra5_0" not in section

    first = call(library["url"], "read_knowledge", {"document": "libro"})
    assert "parte 1 de" in first and "pide `part=2`" in first and "palabra1_0" in first
    second = call(library["url"], "read_knowledge", {"document": "libro", "part": 2})
    assert "parte 2 de" in second and second != first


def test_wrong_requests_say_what_is_available(server: LiveServer, library: dict):
    nope = call(library["url"], "read_knowledge", {"document": "inexistente"})
    assert "No encuentro un documento llamado «inexistente»" in nope and "reglas.md" in nope
    assert "secreto.md" not in nope and "ajeno.md" not in nope  # only what it may read
    ambiguous = call(library["url"], "read_knowledge", {"document": ".md"})
    assert "varios documentos" in ambiguous and "usa el identificador" in ambiguous
    nowhere = call(library["url"], "read_knowledge", {"document": "manual.pdf", "location": "zzz"})
    assert "no tiene «zzz»" in nowhere and "páginas: 1 a 5" in nowhere
    assert "Indica qué documento" in call(library["url"], "read_knowledge", {"document": " "})
    names = [n for n, _ in events(server, library["run"])]
    assert names.count("read_knowledge") == 4


# ---------------------------------------------------------------------- the context
def test_the_context_lists_every_document_and_carries_the_ones_that_fit(
    server: LiveServer, library: dict
):
    context = call(library["url"], "get_context")
    assert "## Conocimiento" in context and "search_knowledge" in context
    assert "**reglas.md**" in context and "**estilo.md**" in context
    assert "ZULU-77" not in context and "ajeno.md" not in context
    # Small documents go whole; the long book and the manual are for searching.
    assert "### reglas.md" in context and "prefijo FAC" in context
    assert (
        "**libro.md**" in context
        and "solo búsqueda" in context.split("**libro.md**")[1].split("\n")[0]
    )
    assert "palabra1_0" not in context


def test_a_subagent_also_reads_what_its_parent_agent_has(
    server: LiveServer, library: dict, tmp_path: Path
):
    with server.db() as db:
        parent = db.get(Run, library["run"])
        child_agent = Agent(name="Hijo", role="R")
        db.add(child_agent)
        db.flush()
        child = Run(
            agent_id=child_agent.id,
            project_id=parent.project_id,
            parent_run_id=parent.id,
            agent_name="Hijo",
            agent_color="#fff",
            project_name="Web",
            cli="claude",
            prompt="parte del trabajo",
            cwd=str(tmp_path),
        )
        db.add(child)
        db.commit()
        child_id = child.id
    url = mcp_url(server, server.manager.tokens.issue(child_id))
    answer = call(url, "search_knowledge", {"query": "tono cercano frases cortas"})
    assert "estilo.md" in answer  # the parent's own document
