"""The «related» links and the graph that is read (phase 15, block 3)."""

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from knowledge_helpers import FakeEmbedWorker, install_fake_model

from agentic_os.models import KnowledgeDoc, KnowledgeRelated, Project
from agentic_os.services.knowledge import graph, similarity

DOCS = "/api/knowledge/docs"
GRAPH = "/api/knowledge/graph"
CANCEL = "cancelar baja suscripción cobro pagar dejar " * 12
BACKUP = "respaldo copia seguridad backup restaurar " * 12
PASSWORD = "contraseña clave acceso entrar password " * 12


# ---------------------------------------------------------------- the links, as numbers
DIMS = 64  # a few dimensions make the cosines too noisy to say anything


def unit(*values: float) -> np.ndarray:
    vector = np.zeros(DIMS, dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def clusters(per_cluster: int = 6, noise: float = 0.05, seed: int = 1):
    """Two well separated groups of unit vectors (a big library: the mean can be trusted)."""
    rng = np.random.default_rng(seed)
    centers = [unit(1), unit(0, 1)]
    ids, rows = [], []
    for c, center in enumerate(centers):
        for i in range(per_cluster):
            ids.append(f"{'ab'[c]}{i}")
            rows.append(unit(*(center + rng.normal(0, noise, DIMS))))
    return ids, np.stack(rows)


def links(ids, matrix, **options):
    defaults = {"threshold": 0.20, "max_neighbors": 8, "raw_threshold": 0.9}
    return graph.related_links(ids, matrix, **{**defaults, **options})


def test_only_documents_of_the_same_group_are_related():
    ids, matrix = clusters()
    found = links(ids, matrix)
    assert found and all(link.a[0] == link.b[0] for link in found)
    assert all(link.a < link.b for link in found)  # a pair is stored once, in order


def test_the_number_of_neighbours_per_document_is_capped():
    ids, matrix = clusters(per_cluster=10)
    found = links(ids, matrix, max_neighbors=2)
    per_doc = {i: sum(i in (link.a, link.b) for link in found) for i in ids}
    # A document may be picked by others, but it chooses at most two for itself, so the total
    # is far below «everybody with everybody» (45 pairs per group).
    assert len(found) <= 2 * len(ids) < 45 * 2
    assert max(per_doc.values()) < 10


def test_the_closest_neighbour_is_always_linked_if_it_is_somewhat_close():
    ids, matrix = clusters()
    far = np.vstack([matrix, unit(0.35, 0.3, 0.9)])  # not near anybody
    found = links([*ids, "lonely"], far, threshold=0.90)  # a threshold nobody reaches
    # With the threshold out of reach only the nearest-neighbour rule links documents.
    assert found
    assert all(link.weight >= similarity.NEAREST_FLOOR for link in found)


def test_a_document_with_nothing_near_stays_alone():
    ids, matrix = clusters()
    outlier = unit(0, 0, 1)  # a direction nobody else has
    found = links([*ids, "lonely"], np.vstack([matrix, outlier]))
    assert not any("lonely" in (link.a, link.b) for link in found)


def test_a_tiny_library_uses_the_raw_cosine_with_the_models_threshold():
    ids = ["a", "b", "c"]
    matrix = np.stack([unit(1, 0.05), unit(1, 0.1), unit(0, 1)])
    assert [(x.a, x.b) for x in links(ids, matrix, raw_threshold=0.95)] == [("a", "b")]
    assert links(ids, matrix, raw_threshold=1.01) == []


def test_without_two_documents_there_is_nothing_to_link():
    assert links(["a"], np.stack([unit(1)])) == []
    assert links([], np.zeros((0, DIMS))) == []


# ------------------------------------------------------------------ in the real thing
def add(client: TestClient, tmp_path: Path, name: str, text: str, **level) -> dict:
    path = tmp_path / "docs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"# {name}\n\n{text}", encoding="utf-8")
    body = {"scope": "general", "paths": [str(path)], **level}
    return client.post(f"{DOCS}/files", json=body).json()[0]["doc"]


def settle(client: TestClient) -> dict:
    client.app.state.knowledge.run_pending(FakeEmbedWorker())
    client.app.state.knowledge.refresh_graph_now()
    return client.get(GRAPH, params={"all": True}).json()


def pairs(data: dict, kind: str = "related") -> set[frozenset[str]]:
    return {frozenset((e["source"], e["target"])) for e in data["edges"] if e["kind"] == kind}


@pytest.fixture
def library(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    install_fake_model(client, monkeypatch)
    docs = {
        "cancel1": add(client, tmp_path, "baja1.md", CANCEL),
        "cancel2": add(client, tmp_path, "baja2.md", CANCEL + "otra vez"),
        "backup1": add(client, tmp_path, "copia1.md", BACKUP),
        "backup2": add(client, tmp_path, "copia2.md", BACKUP + "otra vez"),
        "password": add(client, tmp_path, "clave.md", PASSWORD),
    }
    return {"client": client, "docs": docs, "tmp": tmp_path}


def test_documents_with_close_content_are_related_and_the_others_are_not(library: dict):
    client, docs = library["client"], library["docs"]
    data = settle(client)
    ids = {k: v["id"] for k, v in docs.items()}
    assert pairs(data) == {
        frozenset((ids["cancel1"], ids["cancel2"])),
        frozenset((ids["backup1"], ids["backup2"])),
    }
    assert all(e["weight"] > 0.9 for e in data["edges"])


def test_the_graph_names_its_topics_and_puts_loose_documents_together(library: dict):
    data = settle(library["client"])
    named = [t for t in data["topics"] if not t["loose"]]
    assert sorted(t["size"] for t in named) == [2, 2]
    [loose] = [t for t in data["topics"] if t["loose"]]
    assert loose["name"] == "Sueltos" and loose["size"] == 1
    by_id = {n["id"]: n for n in data["nodes"]}
    assert {by_id[i]["topic"] for t in data["topics"] for i in t["central"]} == {
        t["id"] for t in data["topics"]
    }


def test_a_removed_document_takes_its_links_with_it(library: dict):
    client, docs = library["client"], library["docs"]
    settle(client)
    assert client.delete(f"{DOCS}/{docs['cancel2']['id']}").status_code == 204
    data = settle(client)
    assert pairs(data) == {frozenset((docs["backup1"]["id"], docs["backup2"]["id"]))}


def test_a_new_document_is_linked_when_it_is_indexed(library: dict):
    client, tmp = library["client"], library["tmp"]
    settle(client)
    third = add(client, tmp, "baja3.md", CANCEL + "y más")
    data = settle(client)
    related = {i for p in pairs(data) for i in p}
    assert third["id"] in related


def test_changing_the_model_recomputes_the_links(library: dict, monkeypatch: pytest.MonkeyPatch):
    client = library["client"]
    settle(client)
    assert client.app.state.sessionmaker().query(KnowledgeRelated).count() == 2
    install_fake_model(client, monkeypatch, "fake-two", choose=True)
    # The documents still carry the first model's centroids: nothing can be said with the new
    # model until they are indexed again.
    client.app.state.knowledge.refresh_graph_now()
    assert client.app.state.sessionmaker().query(KnowledgeRelated).count() == 0
    client.app.state.knowledge.reindex_now(FakeEmbedWorker())
    assert client.app.state.sessionmaker().query(KnowledgeRelated).count() == 2
    with client.app.state.sessionmaker() as db:
        assert {r.model for r in db.query(KnowledgeRelated)} == {"fake-two"}


def test_without_a_model_there_are_no_related_links(library: dict, monkeypatch: pytest.MonkeyPatch):
    client = library["client"]
    settle(client)
    with client.app.state.sessionmaker() as db:
        from agentic_os.services.localmodels import catalog, selection

        selection.choose(db, catalog.EMBEDDING, None)  # back to the default: not downloaded
        db.commit()
    client.app.state.knowledge.refresh_graph_now()
    assert pairs(client.get(GRAPH, params={"all": True}).json()) == set()


def test_the_threshold_is_a_setting(library: dict):
    client = library["client"]
    assert len(pairs(settle(client))) == 2
    client.put("/api/settings/knowledge", json={"graph_max_neighbors": 1, "graph_threshold": 0.9})
    assert client.get("/api/settings/knowledge").json()["graph_threshold"] == 0.9
    client.app.state.knowledge.refresh_graph_now()
    assert len(pairs(client.get(GRAPH, params={"all": True}).json())) == 2  # still very close


# ---------------------------------------------------------------------------- scope
def test_the_graph_shows_what_an_agent_of_a_project_sees(library: dict):
    client, tmp = library["client"], library["tmp"]
    with client.app.state.sessionmaker() as db:
        mine = Project(name="Mío", path=str(tmp / "m"), path_key=str(tmp / "m"))
        other = Project(name="Otro", path=str(tmp / "o"), path_key=str(tmp / "o"))
        db.add_all([mine, other])
        db.commit()
        mine_id, other_id = mine.id, other.id
    own = add(client, tmp, "propio.md", CANCEL, scope="project", project_id=mine_id)
    hidden = add(client, tmp, "ajeno.md", CANCEL, scope="project", project_id=other_id)
    settle(client)
    seen = client.get(GRAPH, params={"project_id": mine_id}).json()
    ids = {n["id"] for n in seen["nodes"]}
    assert own["id"] in ids and hidden["id"] not in ids
    assert {library["docs"]["cancel1"]["id"], library["docs"]["password"]["id"]} <= ids
    everything = client.get(GRAPH, params={"all": True}).json()
    assert hidden["id"] in {n["id"] for n in everything["nodes"]}
    # General documents only, when no project is given.
    general = client.get(GRAPH).json()
    assert own["id"] not in {n["id"] for n in general["nodes"]}


def test_a_pending_proposal_is_a_node_with_its_derived_edge_and_nothing_else(library: dict):
    from test_knowledge_graph_data import add_proposal

    client, docs = library["client"], library["docs"]
    proposal = add_proposal(client, "Guía de bajas", based_on=[docs["cancel1"]])
    data = settle(client)
    node = next(n for n in data["nodes"] if n["id"] == proposal)
    assert (node["review"], node["origin"]) == ("proposed", "agent")
    assert node["topic"] is not None  # it sits in the topic of its source
    edges = [e for e in data["edges"] if proposal in (e["source"], e["target"])]
    assert [(e["kind"], e["source"], e["target"]) for e in edges] == [
        ("derived", docs["cancel1"]["id"], proposal)
    ]
    hidden = client.get(GRAPH, params={"all": True, "include_proposed": False}).json()
    assert proposal not in {n["id"] for n in hidden["nodes"]}


def test_a_deleted_source_leaves_a_ghost_the_derived_document_hangs_from(library: dict):
    from test_knowledge_graph_data import add_proposal

    client, docs = library["client"], library["docs"]
    proposal = add_proposal(client, "Guía de bajas", based_on=[docs["cancel1"]])
    client.delete(f"{DOCS}/{docs['cancel1']['id']}")
    data = settle(client)
    [ghost] = [n for n in data["nodes"] if n["ghost"]]
    assert ghost["title"] == docs["cancel1"]["title"]
    [edge] = [e for e in data["edges"] if e["kind"] == "derived"]
    assert (edge["source"], edge["target"]) == (ghost["id"], proposal)


def test_the_graph_reports_its_version(library: dict):
    client = library["client"]
    before = client.get(GRAPH).json()["version"]
    client.app.state.knowledge.refresh_graph_now()
    assert client.get(GRAPH).json()["version"] == before + 1


def test_documents_report_the_model_their_centroid_comes_from(library: dict):
    settle(library["client"])
    with library["client"].app.state.sessionmaker() as db:
        assert {d.centroid_model for d in db.query(KnowledgeDoc)} == {"fake-emb"}
