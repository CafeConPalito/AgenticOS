"""The tools that walk the graph and the help it gives the search (phase 15, block 4)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_helpers import FakeEmbedWorker, install_fake_model

from agentic_os.models import Agent, KnowledgeDoc, KnowledgeSource, Project, Run
from agentic_os.services.knowledge import agent_tools, graph_tools, proposals

DOCS = "/api/knowledge/docs"
MANUAL = "Celery cola tareas worker broker productor " * 10
RETRIES = "Celery reintentos idempotente backoff " * 10
CANCEL = "cancelar baja suscripción cobro pagar " * 10
BACKUP = "respaldo copia seguridad backup restaurar " * 10


class World:
    """A run, a library and shortcuts to build it."""

    def __init__(self, client: TestClient, run_id: str, tmp: Path, project_id: str) -> None:
        self.client, self.run_id, self.tmp, self.project_id = client, run_id, tmp, project_id
        self.titles: dict[str, str] = {}

    @property
    def service(self):
        return self.client.app.state.knowledge

    def process(self) -> None:
        self.service.run_pending(FakeEmbedWorker())
        self.service.refresh_graph_now()

    def user_doc(self, key: str, text: str, **level) -> str:
        path = self.tmp / "docs" / f"{key}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"# {key}\n\n{text}", encoding="utf-8")
        body = {"scope": "general", "paths": [str(path)], **level}
        doc = self.client.post(f"{DOCS}/files", json=body).json()[0]["doc"]
        self.client.patch(f"{DOCS}/{doc['id']}", json={"title": key})
        self.titles[key] = key
        self.process()
        return doc["id"]

    def agent_doc(self, key: str, text: str, based_on: list[str], **options) -> str:
        """A document an agent proposed and the person accepted (so it is in the library)."""
        with self.client.app.state.sessionmaker() as db:
            run = db.get(Run, self.run_id)
            answer, _ = proposals.propose(
                db,
                self.service,
                run,
                title=key,
                markdown=f"# {key}\n\n{text}",
                based_on=[self.titles[b] for b in based_on],
            )
        assert answer.startswith("Propuesta registrada"), answer
        [found] = [
            d
            for d in self.client.get(DOCS, params={"review": "proposed"}).json()
            if d["title"] == key
        ]
        accepted = self.client.post(f"{DOCS}/{found['id']}/accept", json=options)
        assert accepted.status_code == 200, accepted.text
        self.titles[key] = key
        self.process()
        return found["id"]

    def many_agent_docs(self, parent: str, count: int, prefix: str) -> None:
        """`count` accepted agent documents derived from `parent`, inserted directly (fast)."""
        from agentic_os.models import DocStatus, Origin, SourceKind

        with self.client.app.state.sessionmaker() as db:
            for n in range(count):
                doc = KnowledgeDoc(
                    scope="general",
                    title=f"{prefix}{n}",
                    summary=f"Un resumen de una línea del documento número {n}. " * 3,
                    source_kind=SourceKind.MARKDOWN,
                    origin=Origin.AGENT,
                    status=DocStatus.READY,
                    markdown=f"# {prefix}{n}\n\nTexto {n}",
                    md_tokens=10,
                )
                db.add(doc)
                db.flush()
                db.add(KnowledgeSource(doc_id=doc.id, source_id=parent, source_title="hub"))
            db.commit()
        self.service.refresh_graph_now()


@pytest.fixture
def world(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> World:
    install_fake_model(client, monkeypatch)
    with client.app.state.sessionmaker() as db:
        agent = Agent(name="Dev", role="R")
        project = Project(name="Web", path=str(tmp_path), path_key=str(tmp_path))
        db.add_all([agent, project])
        db.flush()
        run = Run(
            agent_id=agent.id,
            project_id=project.id,
            agent_name="Dev",
            agent_color="#4FD1C5",
            project_name="Web",
            cli="claude",
            prompt="x",
            cwd=str(tmp_path),
        )
        db.add(run)
        db.commit()
        world = World(client, run.id, tmp_path, project.id)
    client.put("/api/settings/knowledge", json={"proposals_per_run": 20})
    return world


def tools(world: World):
    """Runs a graph tool the way the MCP server does: with a DB session and the run."""

    class Bound:
        def __init__(self, world: World) -> None:
            self.world = world

        def call(self, function, *args, **kwargs) -> str:
            with self.world.client.app.state.sessionmaker() as db:
                run = db.get(Run, self.world.run_id)
                return function(db, run, *args, **kwargs)[0]

        def explore(self, **kwargs) -> str:
            with self.world.client.app.state.sessionmaker() as db:
                run = db.get(Run, self.world.run_id)
                return graph_tools.explore_knowledge(db, self.world.service, run, **kwargs)[0]

        def search(self, query: str, **kwargs) -> str:
            with self.world.client.app.state.sessionmaker() as db:
                run = db.get(Run, self.world.run_id)
                return agent_tools.search_knowledge(
                    db, self.world.service, Path(self.world.tmp), run, query, **kwargs
                )[0]

    return Bound(world)


@pytest.fixture
def chain(world: World) -> dict:
    """manual (the user's) ← retries (an agent's) ← tuning (an agent's, built on retries), and
    two documents about other things."""
    ids = {"manual": world.user_doc("manual", MANUAL)}
    ids["retries"] = world.agent_doc("retries", RETRIES, ["manual"])
    ids["tuning"] = world.agent_doc("tuning", "Ajustes finos de reintentos " * 20, ["retries"])
    ids["cancel"] = world.user_doc("cancel", CANCEL)
    ids["backup"] = world.user_doc("backup", BACKUP)
    return {"world": world, "tools": tools(world), "ids": ids}


# ------------------------------------------------------------------------------ exploring
def test_one_hop_reaches_the_neighbours_and_two_reach_their_neighbours(chain: dict):
    t = chain["tools"]
    one = t.explore(document="manual", hops=1)
    assert "retries" in one and "tuning" not in one
    two = t.explore(document="manual", hops=2)
    assert "retries" in two and "tuning" in two
    assert "camino: «manual» —origen de→ «retries» —origen de→ «tuning»" in two
    assert "a 2 saltos" in two and "punto de partida" in two


def test_hops_are_capped_at_three(chain: dict):
    answer = chain["tools"].explore(document="manual", hops=99)
    assert "3 saltos como máximo" in answer


def test_exploring_by_a_question_starts_from_what_the_search_finds(chain: dict):
    answer = chain["tools"].explore(query="Celery worker broker productor", hops=2)
    assert "la búsqueda «Celery worker broker productor»" in answer
    assert "manual" in answer and "tuning" in answer


def test_exploring_needs_somewhere_to_start(chain: dict):
    assert "Indica un `document` o una `query`" in chain["tools"].explore()
    assert "No encuentro un documento" in chain["tools"].explore(document="no existe")
    chain["world"].service.search = lambda *args, **kwargs: []  # a question nothing answers
    assert "No encontré nada" in chain["tools"].explore(query="zzqx wwvk")


def test_the_filters_of_link_kind_origin_and_level(chain: dict):
    t = chain["tools"]
    related_only = t.explore(document="manual", hops=2, kinds="related")
    assert "retries" not in related_only and "No hay vecinos con esos filtros" in related_only
    derived = t.explore(document="manual", hops=2, kinds="derived")
    assert "retries" in derived and "tuning" in derived
    by_user = t.explore(document="manual", hops=2, origin="user")
    assert "retries" not in by_user
    by_agent = t.explore(document="manual", hops=2, origin="agent")
    assert "retries" in by_agent and "tuning" in by_agent and "generado por agente" in by_agent
    assert "No hay vecinos" in t.explore(document="manual", hops=2, level="agent")
    assert "`kinds` debe ser" in t.explore(document="manual", kinds="x")
    assert "`origin` debe ser" in t.explore(document="manual", origin="x")
    assert "`level` debe ser" in t.explore(document="manual", level="x")


def test_the_number_of_documents_is_capped(world: World):
    hub = world.user_doc("hub", MANUAL)
    world.many_agent_docs(hub, 12, "spoke")
    t = tools(world)
    answer = t.explore(document="hub", max_docs=5)
    assert answer.count("— a 1 salto") == 5
    assert answer.count("punto de partida") == 1


def test_a_long_answer_is_cut_to_the_token_budget(world: World, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graph_tools, "EXPLORE_TOKENS", 400)
    hub = world.user_doc("hub", MANUAL)
    world.many_agent_docs(hub, 40, "hijo")
    answer = tools(world).explore(document="hub", max_docs=30)
    assert graph_tools.tokens_of(answer) <= 400 + 60
    assert "líneas más" in answer


# --------------------------------------------------------------------------- visibility
def test_nothing_hidden_ever_shows_up(chain: dict, tmp_path: Path):
    world, t = chain["world"], chain["tools"]
    with world.client.app.state.sessionmaker() as db:
        other = Project(name="Otro", path=str(tmp_path / "o"), path_key=str(tmp_path / "o"))
        db.add(other)
        db.commit()
        other_id = other.id
    world.user_doc("secreto", MANUAL + " clave ZULU", scope="project", project_id=other_id)
    switched_off = world.user_doc("apagado", RETRIES + " apagado")
    world.client.patch(f"{DOCS}/{switched_off}", json={"mode": "off"})
    # A pending proposal derived from the manual.
    with world.client.app.state.sessionmaker() as db:
        proposals.propose(
            db,
            world.service,
            db.get(Run, world.run_id),
            title="Pendiente",
            markdown="# Pendiente\n\n" + "una propuesta aún sin revisar " * 20,
            based_on=[world.titles["manual"]],
        )
    world.service.refresh_graph_now()
    outputs = [
        t.call(graph_tools.knowledge_map),
        t.call(graph_tools.related_knowledge, "manual"),
        t.explore(document="manual", hops=3, max_docs=30),
        t.explore(query="Celery tareas", hops=3, max_docs=30),
        t.call(graph_tools.knowledge_path, "manual", "tuning"),
        t.search("Celery reintentos", graph="explore"),
    ]
    for text in outputs:
        assert "secreto" not in text and "ZULU" not in text
        assert "apagado" not in text and "Pendiente" not in text
    assert "retries" in outputs[2]  # sanity: the visible ones are there


# ------------------------------------------------------------------------------ the path
def test_the_path_between_two_documents(chain: dict):
    answer = chain["tools"].call(graph_tools.knowledge_path, "manual", "tuning")
    assert "(2 saltos)" in answer
    assert "«manual» —origen de→ «retries» —origen de→ «tuning»" in answer
    back = chain["tools"].call(graph_tools.knowledge_path, "tuning", "manual")
    assert "«tuning» —derivado de→ «retries» —derivado de→ «manual»" in back


def test_no_path_a_missing_document_or_the_same_one(chain: dict):
    t = chain["tools"]
    assert "No hay camino" in t.call(graph_tools.knowledge_path, "manual", "backup")
    assert "En `source`: No encuentro" in t.call(graph_tools.knowledge_path, "x", "manual")
    assert "En `target`: No encuentro" in t.call(graph_tools.knowledge_path, "manual", "x")
    assert "mismo documento" in t.call(graph_tools.knowledge_path, "manual", "manual")
    assert "No hay camino" in t.call(graph_tools.knowledge_path, "manual", "tuning", max_hops=1)


# -------------------------------------------------------------------------------- the map
def test_the_map_lists_topics_with_their_main_documents(chain: dict):
    answer = chain["tools"].call(graph_tools.knowledge_map)
    assert answer.startswith("## Mapa del conocimiento: 5 documentos")
    assert "Principales:" in answer and "(generado por agente)" in answer
    assert "knowledge_map(topic=" in answer


def test_a_topic_can_be_asked_for_by_number_or_name(chain: dict):
    t = chain["tools"]
    by_number = t.call(graph_tools.knowledge_map, "1")
    assert by_number.startswith("## Tema 1:") and "manual" in by_number and "tuning" in by_number
    assert t.call(graph_tools.knowledge_map, "manual") == by_number
    unknown = t.call(graph_tools.knowledge_map, "inexistente")
    assert "No encuentro el tema" in unknown and "1." in unknown


def test_the_map_of_an_empty_library_says_so(world: World):
    assert "No hay documentos de conocimiento" in tools(world).call(graph_tools.knowledge_map)


# ------------------------------------------------------------------------- the neighbours
def test_related_documents_come_with_the_reason(chain: dict):
    answer = chain["tools"].call(graph_tools.related_knowledge, "retries")
    assert "origen de → **tuning**" in answer and "derivado de → **manual**" in answer
    only_user = chain["tools"].call(graph_tools.related_knowledge, "retries", origin="user")
    assert "manual" in only_user and "tuning" not in only_user
    assert "no tiene vecinos" in chain["tools"].call(graph_tools.related_knowledge, "backup")


# ----------------------------------------------------------------------------- the search
def test_search_lists_the_neighbours_of_each_result(chain: dict):
    answer = chain["tools"].search("Celery cola tareas worker")
    assert "Vecinos: " in answer and "(origen de)" in answer


def test_the_graph_argument_chooses_how_much_graph_comes_with_the_search(chain: dict):
    t = chain["tools"]
    assert "Vecinos:" not in t.search("Celery cola tareas worker", graph="off")
    assert "Grafo cercano" not in t.search("Celery cola tareas worker")
    explored = t.search("Celery cola tareas worker", limit=1, graph="explore")
    assert "Grafo cercano a los resultados" in explored and "tuning" in explored
    assert "`graph` debe ser" in t.search("Celery", graph="mucho")


def test_neighbours_that_fit_the_question_are_added_after_the_direct_results(chain: dict):
    world, ids = chain["world"], chain["ids"]
    with world.client.app.state.sessionmaker() as db:
        run = db.get(Run, world.run_id)
        direct = world.service.search(
            db, "Celery cola tareas worker broker", run.project_id, [run.agent_id], 1, False
        )
        added = world.service.search(
            db, "Celery cola tareas worker broker", run.project_id, [run.agent_id], 1
        )
    assert [h.doc.id for h in direct] == [ids["manual"]]
    assert added[0].doc.id == ids["manual"]  # the direct result stays first
    extra = [h for h in added if h.found_by == "graph"]
    assert extra and all(h.doc.id != ids["manual"] for h in extra)
    assert "origen de" in extra[0].via and "manual" in extra[0].via


def test_the_expansion_can_be_switched_off_and_never_exceeds_its_limit(chain: dict):
    world = chain["world"]

    def found(limit_setting: int) -> list:
        world.client.put("/api/settings/knowledge", json={"graph_expand": limit_setting})
        with world.client.app.state.sessionmaker() as db:
            run = db.get(Run, world.run_id)
            return world.service.search(
                db, "Celery cola tareas worker broker", run.project_id, [run.agent_id], 1
            )

    assert [h.found_by for h in found(0)] == ["both"] or all(
        h.found_by != "graph" for h in found(0)
    )
    assert len([h for h in found(1) if h.found_by == "graph"]) <= 1


def test_a_neighbour_that_says_nothing_about_the_question_is_not_added(chain: dict):
    world = chain["world"]
    with world.client.app.state.sessionmaker() as db:
        run = db.get(Run, world.run_id)
        hits = world.service.search(
            db, "cancelar baja suscripción cobro", run.project_id, [run.agent_id], 1
        )
    assert all(h.found_by != "graph" for h in hits)  # «cancel» has no neighbours of its own


def test_a_document_off_the_graph_changes_nothing_for_the_tools(chain: dict):
    # Knowing nothing about the graph (no links at all) the tools still answer.
    world = chain["world"]
    with world.client.app.state.sessionmaker() as db:
        db.query(KnowledgeDoc).delete()
        db.commit()
    assert "No hay documentos" in tools(world).explore(document="manual")


# ------------------------------------------------------------------- the search tester
def test_the_tester_explores_the_way_an_agent_does(chain: dict):
    world = chain["world"]
    answer = world.client.post(
        "/api/knowledge/explore",
        json={"document": "manual", "hops": 2, "project_id": world.project_id},
    ).json()
    assert answer["message"] == ""
    by_title = {n["title"]: n for n in answer["nodes"]}
    assert by_title["manual"]["depth"] == 0 and by_title["manual"]["strength"] == 1
    assert by_title["retries"]["depth"] == 1 and by_title["retries"]["reasons"] == ["origen de"]
    assert by_title["tuning"]["path"] == ["manual", "retries", "tuning"]
    assert by_title["tuning"]["depth"] == 2 and 0 < by_title["tuning"]["strength"] <= 1


def test_the_tester_says_in_words_why_it_cannot_explore(chain: dict):
    client = chain["world"].client
    nothing = client.post("/api/knowledge/explore", json={}).json()
    assert nothing["nodes"] == [] and "Indica un `document` o una `query`" in nothing["message"]
    unknown = client.post("/api/knowledge/explore", json={"document": "no existe"}).json()
    assert "No encuentro un documento" in unknown["message"]
    assert client.post("/api/knowledge/explore", json={"hops": 9}).status_code == 422


def test_the_run_log_says_what_the_agent_asked_the_graph(chain: dict):
    world = chain["world"]
    with world.client.app.state.sessionmaker() as db:
        run = db.get(Run, world.run_id)
        _, detail = graph_tools.explore_knowledge(
            db, world.service, run, document="manual", hops=3, kinds="derived", origin="agent"
        )
        assert detail.startswith("«manual» → 3 documentos")
        assert "3 saltos" in detail and "kinds=derived" in detail and "origin=agent" in detail
        _, related = graph_tools.related_knowledge(db, run, "retries", "derived", "agent")
        assert related == "retries → 1 vecinos (derived, agent)"
