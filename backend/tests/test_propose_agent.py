"""`propose_agent` (phase 19, block 9; CA13) through the real MCP server: only agents allowed to,
once per run, with the sheet's rules, no repeated role; the draft keeps who proposed it and why,
and the Architect can go on refining it."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from live_server import LiveServer, live_server
from sqlalchemy import select
from test_architect_session import FixedClis
from test_mcp_server import call, events, mcp_url, seed_run

from agentic_os.config import Settings
from agentic_os.models import Agent, AgentStatus, InboxItem, Proposal, Run

SHEET = {
    "name": "Traductor",
    "role": "Traductor inglés",
    "cli": "claude",
    "model": "sonnet",
    "instructions": "Traduce del español al inglés americano.",
    "permission_mode": "restricted",
}


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LiveServer]:
    with live_server(Settings(_env_file=None, data_dir=tmp_path / "data")) as live:
        live.app.state.architect.clis = FixedClis()
        yield live


def new_run(server: LiveServer, tmp_path: Path, allowed: bool = True) -> dict:
    folder = tmp_path / f"p{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    run_id, token = seed_run(server, folder)
    with server.db() as db:
        agent = db.get(Agent, db.get(Run, run_id).agent_id)
        agent.can_propose_agents = allowed
        db.commit()
        agent_id = agent.id
    return {"id": run_id, "url": mcp_url(server, token), "agent": agent_id}


def propose(run: dict, sheet: dict | None = None, reason: str = "Hay textos en inglés.") -> str:
    return call(run["url"], "propose_agent", {"sheet": sheet or SHEET, "reason": reason})


def test_an_allowed_agent_proposes_a_draft_with_its_origin(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path)
    answer = propose(run, {**SHEET, "can_propose_agents": True})
    assert "Propuesta registrada: el agente «Traductor»" in answer
    assert "can_propose_agents" in answer  # what it may not set is said, not stored
    with server.db() as db:
        proposal = db.scalar(select(Proposal))
        assert (proposal.origin, proposal.source_run_id, proposal.source_agent_id) == (
            "agent",
            run["id"],
            run["agent"],
        )
        assert proposal.reason == "Hay textos en inglés."
        draft = db.get(Agent, proposal.target_agent_id)
        assert (draft.status, draft.name, draft.can_propose_agents) == (
            AgentStatus.DRAFT,
            "Traductor",
            False,
        )
        item = db.scalar(select(InboxItem).where(InboxItem.kind == "proposal"))
        assert item.proposal_id == proposal.id and item.agent_name == "Dev"
    assert ("propose_agent", f"Traductor ({proposal.id})") in events(server, run["id"])
    listed = httpx.get(f"{server.url}/api/agents").json()
    assert next(a for a in listed if a["id"] == draft.id)["proposed_by"] == "Dev"


def test_without_the_permission_nothing_is_proposed(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path, allowed=False)
    assert propose(run) == "No tienes permiso para proponer agentes."
    with server.db() as db:
        assert db.scalar(select(Proposal)) is None


def test_once_per_run(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path)
    propose(run)
    second = propose(run, {**SHEET, "name": "Corrector", "role": "Corrector"})
    assert "Ya has propuesto un agente en esta ejecución" in second


def test_a_sheet_that_does_not_pass_is_refused_with_the_reason(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path)
    answer = propose(run, {**SHEET, "model": "gpt-5", "skills": ["inventada"]})
    assert answer.startswith("No se ha registrado la propuesta")
    assert "gpt-5" in answer and "inventada" in answer
    assert "Explica en `reason`" in propose(run, reason="  ")
    with server.db() as db:
        assert db.scalar(select(Proposal)) is None


def test_a_role_the_team_already_has_is_not_proposed(server: LiveServer, tmp_path: Path):
    run = new_run(server, tmp_path)
    answer = propose(run, {**SHEET, "name": "Otro Dev", "role": "Desarrollador"})
    assert "Ya hay un agente con ese rol: Dev" in answer


def test_the_architect_goes_on_from_the_proposal_and_replaces_it(
    server: LiveServer, tmp_path: Path
):
    """Spec G: «Abrir con el Arquitecto» to refine a proposed agent."""
    run = new_run(server, tmp_path)
    propose(run)
    with server.db() as db:
        first = db.scalar(select(Proposal))
        first_id, first_draft = first.id, first.target_agent_id
    conversation = httpx.post(
        f"{server.url}/api/architect/conversations", json={"mode": "agent", "proposal_id": first_id}
    ).json()
    assert conversation["sheet"]["sheet"]["agents"]["main"]["name"] == "Traductor"
    assert conversation["title"] == "Refinar Traductor"
    httpx.patch(
        f"{server.url}/api/architect/conversations/{conversation['id']}/sheet",
        json={"patch": {"role": "Traductor y corrector"}},
    )
    second = httpx.post(
        f"{server.url}/api/architect/conversations/{conversation['id']}/propose"
    ).json()
    assert second["origin"] == "architect" and second["id"] != first_id
    with server.db() as db:
        assert db.get(Proposal, first_id).status == "rejected"
        assert db.get(Agent, first_draft) is None
        assert db.get(Agent, second["target_agent_id"]).role == "Traductor y corrector"
