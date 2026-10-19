"""What an agent knows about the library when its run starts (phase 14, block 6)."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.models import KnowledgeDoc
from agentic_os.services.context import build_instructions
from agentic_os.services.knowledge import config as knowledge_config
from agentic_os.services.knowledge import context as kc

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
DOCS = "/api/knowledge/docs"


def doc(tokens: int, mode: str = "auto", minutes: int = 0) -> KnowledgeDoc:
    return KnowledgeDoc(
        id=f"d{tokens}-{mode}",
        title=f"doc {tokens}",
        mode=mode,
        md_tokens=tokens,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes),
    )


def add(client: TestClient, path: Path, **level) -> dict:
    response = client.post(
        f"{DOCS}/files", json={"scope": "general", "paths": [str(path)], **level}
    )
    return response.json()[0]["doc"]


def md(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "docs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def section(client: TestClient, run_id: str = "run1", project: str | None = None, agents=()) -> str:
    data_dir = Path(client.app.state.settings.data_dir)
    with client.app.state.sessionmaker() as db:
        return kc.knowledge_section(db, data_dir, run_id, project, list(agents))


def process(client: TestClient) -> None:
    client.app.state.knowledge.run_pending()


# ------------------------------------------------------------------------- the budget
def test_always_in_context_first_then_the_small_ones_smallest_first_while_they_fit():
    docs = [
        doc(600, "context"),
        doc(300, minutes=1),
        doc(100, minutes=2),
        doc(250, minutes=3),
        doc(500, minutes=4),  # bigger than «small»: for searching
        doc(50, "search", minutes=5),  # never whole
        doc(10, "off", minutes=6),
    ]
    chosen = kc.plan(docs, context_budget=1000, small_doc_tokens=400)
    # 600 (always) + 100 + 250 = 950; the 300 would take it to 1250.
    assert chosen == {"d600-context", "d100-auto", "d250-auto"}


def test_an_always_document_goes_in_even_over_the_budget_and_leaves_no_room():
    docs = [doc(5000, "context"), doc(10)]
    assert kc.plan(docs, context_budget=1000, small_doc_tokens=400) == {"d5000-context"}


def test_ties_go_to_the_oldest():
    first, second = doc(100, minutes=1), doc(100, minutes=2)
    second.id = "d100-b"
    assert kc.plan([second, first], context_budget=150, small_doc_tokens=400) == {first.id}


# ------------------------------------------------------------------------- the section
def test_no_documents_no_section(client: TestClient):
    assert section(client) == ""


def test_the_index_says_what_each_document_is_and_the_small_ones_come_whole(
    client: TestClient, tmp_path: Path
):
    add(client, md(tmp_path, "reglas.md", "# Reglas\n\nToda factura lleva el prefijo FAC."))
    big = add(client, md(tmp_path, "libro.md", "# Libro\n\n" + "palabra " * 1500))
    forced = add(client, md(tmp_path, "guia.md", "# Guía\n\nUsa siempre tono cercano."))
    client.patch(
        f"{DOCS}/{forced['id']}", json={"mode": "context", "description": "Tono de la marca"}
    )
    hidden = add(client, md(tmp_path, "nube.md", "# Nube\n\nsolo para buscar"))
    client.patch(f"{DOCS}/{hidden['id']}", json={"mode": "search"})
    off = add(client, md(tmp_path, "off.md", "# Off\n\napagado"))
    client.patch(f"{DOCS}/{off['id']}", json={"mode": "off"})
    add(client, md(tmp_path, "vacio.md", "   "))  # fails
    process(client)
    add(client, md(tmp_path, "pendiente.md", "# P\n\nno procesado"))  # still queued

    text = section(client)
    assert text.startswith("## Conocimiento") and "search_knowledge" in text
    lines = [line for line in text.splitlines() if line.startswith("- **")]
    assert [line.split("**")[1] for line in lines] == [
        "reglas.md",
        "libro.md",
        "guia.md",
        "nube.md",
    ]
    by_name = {line.split("**")[1]: line for line in lines}
    assert "(general, completo, ~" in by_name["reglas.md"]
    assert "solo búsqueda" in by_name["libro.md"]  # bigger than the «small» limit
    assert "solo búsqueda" in by_name["nube.md"]  # asked never to go whole
    assert "— Tono de la marca" in by_name["guia.md"] and "completo" in by_name["guia.md"]
    assert f"`[{big['id'][:8]}]`" in by_name["libro.md"]
    # Whole text only for the ones that go whole.
    assert "### reglas.md" in text and "prefijo FAC" in text
    assert "### guia.md" in text and "tono cercano" in text
    assert "### libro.md" not in text and "palabra palabra" not in text
    assert "### nube.md" not in text and "solo para buscar" not in text
    for absent in ("off.md", "vacio.md", "pendiente.md"):
        assert absent not in text


def test_a_small_budget_leaves_the_rest_for_searching(client: TestClient, tmp_path: Path):
    for number in range(4):
        add(client, md(tmp_path, f"d{number}.md", f"# D{number}\n\n" + "texto " * (100 + number)))
    process(client)
    with client.app.state.sessionmaker() as db:
        knowledge_config.save(db, {"context_budget": 500})
        db.commit()
    text = section(client)
    whole = [line for line in text.splitlines() if line.startswith("### ")]
    assert 0 < len(whole) < 4  # not all fit
    assert text.count("solo búsqueda") == 4 - len(whole)


def test_each_level_only_for_its_owner(client: TestClient, tmp_path: Path):
    web = client.post("/api/projects", json={"name": "Web", "path": str(tmp_path / "w")})
    (tmp_path / "w").mkdir(exist_ok=True)
    web = client.post("/api/projects", json={"name": "Web", "path": str(tmp_path / "w")}).json()
    writer = client.post("/api/agents", json={"name": "R", "role": "R", "cli": "claude"}).json()
    add(client, md(tmp_path, "general.md", "# G\n\ngeneral"))
    add(client, md(tmp_path, "web.md", "# W\n\nweb"), scope="project", project_id=web["id"])
    add(client, md(tmp_path, "mio.md", "# M\n\nmio"), scope="agent", agent_id=writer["id"])
    process(client)
    assert "web.md" not in section(client) and "mio.md" not in section(client)
    mine = section(client, project=web["id"], agents=[writer["id"]])
    assert "**web.md**" in mine and "(del proyecto," in mine
    assert "**mio.md**" in mine and "(de agente," in mine


# ------------------------------------------------------------------------- pictures
def test_a_documents_pictures_become_the_path_of_the_stored_file(
    client: TestClient, tmp_path: Path
):
    path = tmp_path / "docs" / "informe.docx"
    path.parent.mkdir()
    shutil.copy(FIXTURES / "informe.docx", path)
    add(client, path)
    process(client)
    text = section(client)
    assert "(general, completo" in text and "1 imagen" in text and "kimg:" not in text
    link = next(line for line in text.splitlines() if "knowledge" in line and "![" in line)
    stored = Path(link[link.index("](") + 2 : link.rindex(")")].strip("<>"))
    assert stored.is_file() and stored.parent.name == "images" and stored.suffix == ".png"


def test_a_picture_the_user_added_is_copied_for_the_run_and_cleaned_after(
    client: TestClient, tmp_path: Path
):
    path = tmp_path / "docs" / "captura.png"
    path.parent.mkdir()
    shutil.copy(FIXTURES / "captura_error.png", path)
    record = add(client, path)
    process(client)
    data_dir = Path(client.app.state.settings.data_dir)
    text = section(client, run_id="r-42")
    copy = data_dir / "knowledge" / "run-images" / "r-42" / f"{record['id'][:8]}-0.png"
    assert copy.is_file() and str(copy) in text
    assert copy.read_bytes() == path.read_bytes()
    kc.clean_run(data_dir, "r-42")
    assert not copy.exists() and not copy.parent.exists()
    # The original is gone: the agent is told, not given a broken link.
    path.unlink()
    assert "[captura.png: no disponible]" in section(client, run_id="r-43")


def test_the_folders_for_the_cli_exist_and_are_cleaned_at_start(tmp_path: Path):
    stored, copies = kc.prepare_folders(tmp_path, "r1")
    assert stored.is_dir() and copies.is_dir() and copies.name == "r1"
    (copies / "x.png").write_bytes(b"1")
    kc.prepare_folders(tmp_path, "r2")
    kc.clean_all(tmp_path)  # a restart: no run is alive
    assert not (tmp_path / "knowledge" / "run-images").exists()
    assert stored.is_dir()  # the stored pictures are not run garbage


# ----------------------------------------------------------------- the instructions
def test_the_section_sits_between_the_memory_and_the_task():
    from agentic_os.models import Agent, Project

    text = build_instructions(
        Agent(name="Dev", role="Dev", instructions="Escribe tests."),
        Project(name="Web"),
        "C:/w",
        memory="Usa pnpm.",
        knowledge="## Conocimiento\n- **manual.pdf**",
    )
    assert text.index("## Memoria del proyecto") < text.index("## Conocimiento")
    assert text.index("## Conocimiento") < text.index("# Cómo trabajar con Agentic OS")
    assert "`search_knowledge` y `read_knowledge`" in text  # the rules say how to use them
    without = build_instructions(
        Agent(name="Dev", role="Dev", instructions=""), Project(name="Web"), "C:/w"
    )
    assert "## Conocimiento" not in without


@pytest.mark.parametrize("name", ["Redactor", "Comercial", "Analista"])
def test_the_agent_templates_mention_the_knowledge(client: TestClient, name: str):
    templates = {t["name"]: t for t in client.get("/api/agent-templates").json()}
    assert "search_knowledge" in templates[name]["instructions"]
