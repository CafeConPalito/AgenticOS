"""Does the graph help to find things? (phase 15, block 8) The corpus of the graph spikes (24
documents about Celery, Redis, Docker, PostgreSQL, React, Git, authentication, cooking, travel and
the invoicing product Aurora; 12 of them guides an agent derived from a user's document) through
the whole product: the real `multilingual-e5-small`, the real pipeline, the proposal flow and the
real tools. The model is the one the phase 14 quality test downloads into the system's temp."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_knowledge_quality import CACHE, e5_files  # noqa: F401 - the model, a fixture

from agentic_os.models import Agent, Project, Run
from agentic_os.services.knowledge import graph_tools, proposals
from agentic_os.services.knowledge.worker import InlineWorker
from agentic_os.services.localmodels import catalog, selection, store

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "knowledge" / "graph_corpus.json").read_text("utf-8")
)
DOCS = "/api/knowledge/docs"
assert CACHE  # imported for the model fixture


class Library:
    def __init__(self, client: TestClient, run_id: str, project_id: str) -> None:
        self.client, self.run_id, self.project_id = client, run_id, project_id
        self.ids: dict[str, str] = {}  # corpus id → document id
        self.title_of: dict[str, str] = {}

    @property
    def service(self):
        return self.client.app.state.knowledge

    def search(self, query: str, *, limit: int, graph: bool) -> list[tuple[str, str]]:
        """(corpus id, found_by) of the results, as an agent of the project gets them."""
        by_doc = {v: k for k, v in self.ids.items()}
        with self.client.app.state.sessionmaker() as db:
            run = db.get(Run, self.run_id)
            hits = self.service.search(db, query, run.project_id, [run.agent_id], limit, graph)
        return [(by_doc[h.doc.id], h.found_by) for h in hits]

    def explore(self, **kwargs) -> list[dict]:
        with self.client.app.state.sessionmaker() as db:
            run = db.get(Run, self.run_id)
            nodes, message = graph_tools.explore_data(
                db, self.service, run.project_id, [run.agent_id], **kwargs
            )
        assert message == "", message
        by_doc = {v: k for k, v in self.ids.items()}
        return [{**n, "key": by_doc[n["id"]]} for n in nodes]


@pytest.fixture
def library(client: TestClient, tmp_path: Path, e5_files: Path) -> Library:  # noqa: F811
    entry = catalog.entry("e5-small")
    data_dir = Path(client.app.state.settings.data_dir)
    shutil.copytree(e5_files, store.downloaded_folder(data_dir, entry), dirs_exist_ok=True)
    assert store.is_installed(data_dir, entry)
    with client.app.state.sessionmaker() as db:
        assert selection.chosen(db)["embedding"] == "e5-small"
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
        built = Library(client, run.id, project.id)
    client.put("/api/settings/knowledge", json={"proposals_per_run": 20})

    folder = tmp_path / "corpus"
    folder.mkdir()
    worker = InlineWorker()
    user_docs = [d for d in CORPUS["docs"] if d["origin"] == "user"]
    paths = []
    for doc in user_docs:
        path = folder / f"{doc['id']}.md"
        path.write_text(f"# {doc['title']}\n\n" + "\n\n".join(doc["chunks"]), encoding="utf-8")
        paths.append(str(path))
    added = client.post(f"{DOCS}/files", json={"scope": "general", "paths": paths}).json()
    for doc, item in zip(user_docs, added, strict=True):
        client.patch(f"{DOCS}/{item['doc']['id']}", json={"title": doc["title"]})
        built.ids[doc["id"]] = item["doc"]["id"]
        built.title_of[doc["id"]] = doc["title"]
    client.app.state.knowledge.run_pending(worker)

    # The guides an agent derived: proposed from the documents they were built on, accepted.
    for doc in (d for d in CORPUS["docs"] if d["origin"] == "agent"):
        with client.app.state.sessionmaker() as db:
            answer, _ = proposals.propose(
                db,
                built.service,
                db.get(Run, built.run_id),
                title=doc["title"],
                markdown=f"# {doc['title']}\n\n" + "\n\n".join(doc["chunks"]),
                based_on=[built.title_of[source] for source in doc["derived"]],
            )
        assert answer.startswith("Propuesta registrada"), (doc["id"], answer)
        [found] = [
            p
            for p in client.get(DOCS, params={"review": "proposed"}).json()
            if p["title"] == doc["title"]
        ]
        client.post(f"{DOCS}/{found['id']}/accept", json={})
        built.ids[doc["id"]] = found["id"]
        built.title_of[doc["id"]] = doc["title"]
        client.app.state.knowledge.run_pending(worker)
    client.app.state.knowledge.refresh_graph_now()
    return built


AGENT_GUIDES = {d["id"]: d for d in CORPUS["docs"] if d["origin"] == "agent"}
TOPIC_OF = {d["id"]: d["topic"] for d in CORPUS["docs"]}


def graph_read(library: Library) -> dict:
    return library.client.get("/api/knowledge/graph", params={"all": True}).json()


def keyed(library: Library, graph: dict) -> tuple[set[frozenset[str]], set[tuple[str, str]]]:
    by_doc = {v: k for k, v in library.ids.items()}
    related, derived = set(), set()
    for edge in graph["edges"]:
        pair = (by_doc[edge["source"]], by_doc[edge["target"]])
        if edge["kind"] == "related":
            related.add(frozenset(pair))
        else:
            derived.add(pair)
    return related, derived


# ------------------------------------------------------------------------------ the links
def test_every_guide_hangs_from_the_document_it_was_built_on(library: Library):
    _, derived = keyed(library, graph_read(library))
    expected = {(src, doc["id"]) for doc in AGENT_GUIDES.values() for src in doc["derived"]}
    assert derived == expected


def test_most_related_links_join_documents_of_the_same_subject(library: Library):
    related, _ = keyed(library, graph_read(library))
    same = [p for p in related if len({TOPIC_OF[k] for k in p}) == 1]
    precision = len(same) / len(related)
    print(f"related links: {len(related)}, same subject: {precision:.2f}")
    # Spike S1 measured 0.8-0.9 with the centered cosine; the rest are honest bridges (a Celery
    # manual and the Docker Compose guide that runs its worker).
    assert precision >= 0.7, sorted(tuple(sorted(p)) for p in related)


# ------------------------------------------------------------------------------ the topics
def topics_of(library: Library) -> list[set[str]]:
    by_doc = {v: k for k, v in library.ids.items()}
    graph = graph_read(library)
    return [
        {by_doc[n["id"]] for n in graph["nodes"] if n["topic"] == t["id"]}
        for t in graph["topics"]
        if not t["loose"]
    ]


def test_the_map_groups_the_corpus_into_topics_that_make_sense(library: Library):
    found = topics_of(library)
    print("topics:", [sorted(t) for t in found])
    celery = {"celery-manual", "celery-reintentos", "celery-colas", "celery-observabilidad"}
    docker = {"docker-basico", "docker-compose", "docker-multistage"}
    cooking = {"cocina-paella", "cocina-masa"}
    for topic in found:
        # Nothing mixes Celery with cooking, or Docker with cooking.
        assert not (topic & cooking and topic & (celery | docker)), topic
    assert any(celery <= topic for topic in found), found
    assert any(docker <= topic for topic in found), found
    assert any(cooking <= topic for topic in found), found
    assert any({"aurora-facturas", "aurora-backup"} <= topic for topic in found), found


def test_the_same_library_always_gives_the_same_topics(library: Library):
    first = sorted(sorted(t) for t in topics_of(library))
    library.service.refresh_graph_now()
    assert sorted(sorted(t) for t in topics_of(library)) == first


def test_the_map_tool_names_the_topics_after_their_documents(library: Library):
    with library.client.app.state.sessionmaker() as db:
        answer, _ = graph_tools.knowledge_map(db, db.get(Run, library.run_id))
    assert "Mapa del conocimiento: 25 documentos" in answer
    assert "Desarrollo con Celery" in answer and "(generado por agente)" in answer


# ------------------------------------------------------------------------- finding things
def test_the_guides_of_a_pdf_come_with_it(library: Library):
    """Question about the PDF, one result asked for: without the graph that is all the agent
    gets; with it the guides derived from the PDF come along (CA9)."""
    off_recall, on_recall = [], []
    for item in CORPUS["family"]:
        wanted = {item["answer"], *item["family"]}
        off = [k for k, _ in library.search(item["q"], limit=1, graph=False)]
        on = library.search(item["q"], limit=1, graph=True)
        print(f"{item['answer']:18s} off={off} on={on}")
        # The direct result is the same: the graph only adds after it.
        assert [k for k, how in on if how != "graph"] == off
        off_recall.append(len(wanted & set(off)) / len(wanted))
        on_recall.append(len(wanted & {k for k, _ in on}) / len(wanted))
    mean_off = sum(off_recall) / len(off_recall)
    mean_on = sum(on_recall) / len(on_recall)
    print(f"family recall: without the graph {mean_off:.2f}, with it {mean_on:.2f}")
    assert mean_on > mean_off + 0.15
    assert all(on >= off for on, off in zip(on_recall, off_recall, strict=True))


def test_the_graph_never_pushes_a_direct_result_out(library: Library):
    for item in CORPUS["questions"]:
        off = [k for k, _ in library.search(item["q"], limit=3, graph=False)]
        on = library.search(item["q"], limit=3, graph=True)
        assert [k for k, how in on][: len(off)] == off, item["q"]
        extra = [k for k, how in on[len(off) :]]
        assert all(how == "graph" for _, how in on[len(off) :]), (item["q"], on)
        assert len(extra) <= 3  # graph_expand


def test_what_lies_two_hops_from_the_best_result_is_reached_by_exploring(library: Library):
    """The agent reads the best result and wants to see how it connects with the rest (CA15). The
    search alone — even with the neighbours it adds — stops one hop away; exploring goes on."""
    chain = CORPUS["chain"]
    plain = library.search(chain["q"], limit=1, graph=False)
    near = library.search(chain["q"], limit=1, graph=True)
    assert plain[0][0] == chain["start"], plain
    assert chain["answer"] not in {k for k, _ in plain} | {k for k, _ in near}, near
    start = library.title_of[chain["start"]]
    reached = {n["key"]: n for n in library.explore(document=start, hops=2)}
    print("explored from", start, {k: n["depth"] for k, n in reached.items()})
    assert chain["answer"] in reached
    assert reached[chain["answer"]]["depth"] == 2
    assert reached[chain["answer"]]["path"][1] == library.title_of[chain["via"]]
    assert chain["answer"] not in {n["key"] for n in library.explore(document=start, hops=1)}
    # The path tool names the same chain.
    with library.client.app.state.sessionmaker() as db:
        answer, _ = graph_tools.knowledge_path(
            db, db.get(Run, library.run_id), start, library.title_of[chain["answer"]]
        )
    assert "(2 saltos)" in answer and library.title_of[chain["via"]] in answer
