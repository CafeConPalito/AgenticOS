"""An agent proposes and walks the graph through the real MCP server (phase 15, block 8): the
official MCP client against a live backend, like a CLI would. No model of embeddings is downloaded
here, so the links are the «derived from» ones the agent itself set."""

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

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
GUIDE = (
    "# Cancelar y reactivar\n\nPara dejar de pagar abra Cuenta, Plan y pulse Dar de baja. La baja "
    "se aplica al final del periodo y los datos se conservan noventa días. Reactivar la cuenta "
    "dentro de ese plazo recupera todo el contenido."
)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        yield live


def api(server: LiveServer, method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{server.url}/api{path}", timeout=60, **kwargs)


@pytest.fixture
def agent(server: LiveServer, tmp_path: Path) -> dict:
    """A run of an agent, and the user's manual (a PDF) in the library."""
    run_id, token = seed_run(server, tmp_path)
    manual = tmp_path / "library" / "manual.pdf"
    manual.parent.mkdir()
    shutil.copy(FIXTURES / "manual.pdf", manual)
    added = api(
        server,
        "POST",
        "/knowledge/docs/files",
        json={"scope": "general", "paths": [str(manual)]},
    ).json()
    pdf = added[0]["doc"]
    assert wait_until(
        lambda: api(server, "GET", f"/knowledge/docs/{pdf['id']}").json()["status"] == "ready",
        timeout=120,
    )
    return {"run": run_id, "url": mcp_url(server, token), "pdf": pdf}


def markdown_of(server: LiveServer, doc_id: str) -> str:
    return api(server, "GET", f"/knowledge/docs/{doc_id}/markdown").json()["markdown"]


def test_an_agent_proposes_a_guide_from_a_pdf_and_the_person_finds_it_in_the_inbox(
    server: LiveServer, agent: dict
):
    pdf = agent["pdf"]
    before = markdown_of(server, pdf["id"])
    answer = call(
        agent["url"],
        "propose_knowledge",
        {
            "title": "Cancelar y reactivar",
            "markdown": GUIDE,
            "description": "Cómo dar de baja y recuperar una cuenta",
            "based_on": [pdf["title"]],
            "level": "general",
        },
    )
    assert answer.startswith("Propuesta registrada")

    [found] = api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json()
    assert found["title"] == "Cancelar y reactivar" and found["origin"] == "agent"
    assert [s["id"] for s in found["sources"]] == [pdf["id"]]
    assert found["provenance"]["agent_name"] == "Dev"
    assert found["provenance"]["suggested_scope"] == "general"

    [item] = [i for i in api(server, "GET", "/inbox").json() if i["kind"] == "knowledge"]
    assert item["knowledge_doc_id"] == found["id"] and item["agent_name"] == "Dev"

    # The PDF and its Markdown are exactly as they were; nobody can read the proposal yet.
    assert markdown_of(server, pdf["id"]) == before
    nothing = call(
        agent["url"], "search_knowledge", {"query": "dar de baja reactivar noventa días"}
    )
    assert "Cancelar y reactivar" not in nothing
    assert any(name == "propose_knowledge" for name, _ in events(server, agent["run"]))


def accept(server: LiveServer, doc_id: str) -> None:
    assert api(server, "POST", f"/knowledge/docs/{doc_id}/accept", json={}).status_code == 200
    assert wait_until(
        lambda: api(server, "GET", f"/knowledge/docs/{doc_id}").json()["status"] == "ready",
        timeout=120,
    )


def test_the_whole_flow_propose_accept_search_and_walk_the_graph(server: LiveServer, agent: dict):
    pdf = agent["pdf"]
    call(
        agent["url"],
        "propose_knowledge",
        {"title": "Cancelar y reactivar", "markdown": GUIDE, "based_on": [pdf["title"]]},
    )
    [proposal] = api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json()
    accept(server, proposal["id"])
    # The inbox request is resolved by the decision.
    assert not [i for i in api(server, "GET", "/inbox").json() if i["kind"] == "knowledge"]

    # Search finds it, marked, and lists the PDF as its neighbour.
    found = call(agent["url"], "search_knowledge", {"query": "dar de baja reactivar noventa días"})
    assert "Cancelar y reactivar" in found and "generado por agente" in found
    assert "Vecinos:" in found and pdf["title"] in found

    # The agent orients itself with the map, walks the graph and reads.
    mapa = call(agent["url"], "knowledge_map")
    assert "Mapa del conocimiento: 2 documentos" in mapa and "(generado por agente)" in mapa
    explored = call(agent["url"], "explore_knowledge", {"document": pdf["title"], "hops": 2})
    assert "Cancelar y reactivar" in explored and "origen de" in explored
    related = call(agent["url"], "related_knowledge", {"document": pdf["title"], "origin": "agent"})
    assert "Cancelar y reactivar" in related
    route = call(
        agent["url"],
        "knowledge_path",
        {"source": "Cancelar y reactivar", "target": pdf["title"]},
    )
    assert "derivado de" in route and "(1 saltos)" in route
    read = call(agent["url"], "read_knowledge", {"document": "Cancelar y reactivar"})
    assert "noventa días" in read and "generado por agente" in read

    # Each call is in the run's log, with what was asked.
    log = dict(events(server, agent["run"]))
    for tool in (
        "propose_knowledge",
        "search_knowledge",
        "knowledge_map",
        "explore_knowledge",
        "related_knowledge",
        "knowledge_path",
        "read_knowledge",
    ):
        assert tool in log, (tool, sorted(log))
    assert "2 saltos" in log["explore_knowledge"]

    # And the next run is told about the topics and the tools.
    context = call(agent["url"], "get_context")
    assert "Temas: " in context and "explore_knowledge" in context
    assert "generado por agente" in context


def test_a_rejected_proposal_leaves_nothing_but_a_warning(server: LiveServer, agent: dict):
    pdf = agent["pdf"]
    args = {"title": "Cancelar y reactivar", "markdown": GUIDE, "based_on": [pdf["title"]]}
    call(agent["url"], "propose_knowledge", args)
    [proposal] = api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json()
    rejected = api(
        server, "POST", f"/knowledge/docs/{proposal['id']}/reject", json={"reason": "ya existe"}
    )
    assert rejected.status_code == 204
    again = call(agent["url"], "propose_knowledge", args)
    assert "ya rechazó" in again and "ya existe" in again
    assert api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json() == []


def test_the_graph_api_shows_the_derived_link_for_the_screen(server: LiveServer, agent: dict):
    pdf = agent["pdf"]
    call(
        agent["url"],
        "propose_knowledge",
        {"title": "Cancelar y reactivar", "markdown": GUIDE, "based_on": [pdf["title"]]},
    )
    [proposal] = api(server, "GET", "/knowledge/docs", params={"review": "proposed"}).json()
    accept(server, proposal["id"])

    def has_edge() -> bool:
        graph = api(server, "GET", "/knowledge/graph", params={"all": True}).json()
        return any(
            e["kind"] == "derived" and e["source"] == pdf["id"] and e["target"] == proposal["id"]
            for e in graph["edges"]
        )

    assert has_edge()
    graph = api(server, "GET", "/knowledge/graph", params={"all": True}).json()
    kinds = {n["id"]: (n["origin"], n["review"]) for n in graph["nodes"]}
    assert kinds[pdf["id"]] == ("user", "none")
    assert kinds[proposal["id"]] == ("agent", "none")
