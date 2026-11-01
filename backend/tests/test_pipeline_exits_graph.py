"""«Terminar aquí» exits in the shape of a pipeline (phase 24, block 2; CA2, ADR 0030): where an
exit is allowed, and that it is saved and read back with the pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.services.pipeline_graph import Edge, Graph

# A → (B | C) → D → E: the fork's stages B and C are inside it; A, D and E are not.
DIAMOND = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E")]


def graph(exits: dict[str, str], links: list[tuple[str, str]] = DIAMOND) -> Graph:
    names = sorted({n for link in links for n in link})
    edges = [Edge(f"{a}{b}", a, b, position=i) for i, (a, b) in enumerate(links)]
    return Graph(names, edges, exits=exits)


def issues(g: Graph) -> list[tuple[str, str | None]]:
    return [(e.code, e.stage) for e in g.validate()]


# ------------------------------------------------------------------------------ the rules
def test_an_exit_before_the_fork_on_the_fork_and_after_the_join_is_valid():
    g = graph({"A": "Solo pide requisitos", "D": "No necesita despliegue"})
    assert g.validate() == []
    assert g.exit_of("A") == "Solo pide requisitos" and g.exit_of("B") is None


def test_an_exit_needs_a_condition():
    assert issues(graph({"A": "   "})) == [("exit_no_condition", "A")]


def test_a_final_stage_needs_no_exit():
    assert issues(graph({"E": "Terminar"})) == [("exit_on_final", "E")]


def test_an_exit_inside_an_open_fork_would_stop_the_other_branches():
    assert issues(graph({"B": "Terminar", "C": "Terminar"})) == [
        ("exit_in_branch", "B"),
        ("exit_in_branch", "C"),
    ]


def test_a_branch_that_ends_on_its_own_is_final_and_takes_no_exit():
    # A → (B → B2 | C): the branches never meet, so B2 and C are finals.
    links = [("A", "B"), ("B", "B2"), ("A", "C")]
    assert issues(graph({"B": "Terminar"}, links)) == [("exit_in_branch", "B")]
    assert issues(graph({"C": "Terminar"}, links)) == [("exit_on_final", "C")]


def test_a_chain_without_exits_is_as_before():
    g = graph({}, [("A", "B"), ("B", "C")])
    assert g.validate() == [] and g.exits == {}


# ---------------------------------------------------------------------------- saving
@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        client.post("/api/scheduler/pause")
        yield client


def project(api: TestClient, tmp_path: Path) -> str:
    folder = tmp_path / "web"
    folder.mkdir()
    return api.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()["id"]


PIPELINE = {
    "stages": [
        {"name": "Requisitos"},
        {"name": "Validación", "exit_condition": "  La tarea solo pide requisitos  "},
        {"name": "Desarrollo"},
    ]
}


def test_an_exit_is_saved_with_its_node_beside_the_stage_and_read_back(
    api: TestClient, tmp_path: Path
):
    project_id = project(api, tmp_path)
    saved = api.put(f"/api/projects/{project_id}/pipeline", json=PIPELINE)
    assert saved.status_code == 200, saved.json()
    first, validation, last = saved.json()["stages"]
    assert validation["exit_condition"] == "La tarea solo pide requisitos"
    assert (validation["exit_x"], validation["exit_y"]) != (None, None)
    assert validation["exit_x"] == validation["x"] and validation["exit_y"] > validation["y"]
    assert first["exit_condition"] is None and first["exit_x"] is None

    # Moved on the canvas, then removed: the node goes with it.
    stages = [
        {"id": first["id"], "name": "Requisitos"},
        {
            "id": validation["id"],
            "name": "Validación",
            "exit_condition": "La tarea solo pide requisitos",
            "exit_x": 900,
            "exit_y": 40,
        },
        {"id": last["id"], "name": "Desarrollo"},
    ]
    moved = api.put(f"/api/projects/{project_id}/pipeline", json={"stages": stages}).json()
    assert (moved["stages"][1]["exit_x"], moved["stages"][1]["exit_y"]) == (900, 40)
    stages[1] = {"id": validation["id"], "name": "Validación"}
    removed = api.put(f"/api/projects/{project_id}/pipeline", json={"stages": stages}).json()
    assert removed["stages"][1]["exit_condition"] is None
    assert removed["stages"][1]["exit_x"] is None


def test_a_misplaced_exit_is_refused_with_its_problem(api: TestClient, tmp_path: Path):
    project_id = project(api, tmp_path)
    body = {
        "stages": [
            {"name": "A"},
            {"name": "B", "exit_condition": "Terminar"},
            {"name": "C"},
            {"name": "D", "exit_condition": ""},
        ],
        "links": [
            {"source": 0, "target": 1, "condition": "toca B"},
            {"source": 0, "target": 2, "condition": "toca C"},
            {"source": 1, "target": 3},
            {"source": 2, "target": 3},
        ],
    }
    url = f"/api/projects/{project_id}/pipeline"
    assert api.post(f"{url}/validate", json=body).json() == [
        {"code": "exit_in_branch", "stage": 1, "link": None},
        {"code": "exit_no_condition", "stage": 3, "link": None},
        {"code": "exit_on_final", "stage": 3, "link": None},
    ]
    refused = api.put(url, json=body)
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "invalid_graph"
