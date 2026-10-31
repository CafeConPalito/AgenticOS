"""Phase 21 (fixes from the user's test of v0.9.0): the Architect's runs in Ejecuciones (CA3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_architect_session import FixedClis

from agentic_os.db.base import DEFAULT_WORKSPACE
from agentic_os.models import ArchitectConversation, Run, RunKind


@pytest.fixture
def api(client: TestClient) -> TestClient:
    client.app.state.architect.clis = FixedClis()
    return client


def _run(api: TestClient, kind: RunKind, **fields) -> str:
    with api.app.state.sessionmaker() as db:
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            kind=kind,
            agent_name="Arquitecto" if kind == RunKind.ARCHITECT else "Decisor",
            agent_color="#7C3AED",
            project_name="",
            cli="claude",
            prompt="x",
            cwd=".",
            **{"status": "running", **fields},
        )
        db.add(run)
        db.commit()
        return run.id


def test_the_architects_runs_are_listed_and_counted_like_the_list(api: TestClient):
    conversation = api.post("/api/architect/conversations", json={}).json()
    live = _run(api, RunKind.ARCHITECT)
    old = _run(api, RunKind.ARCHITECT, status="exited")
    _run(api, RunKind.DECISION)  # an internal call: neither listed nor counted
    with api.app.state.sessionmaker() as db:
        db.get(ArchitectConversation, conversation["id"]).run_id = live
        db.commit()

    runs = {r["id"]: r for r in api.get("/api/runs").json()}
    assert set(runs) == {live, old}
    assert runs[live]["kind"] == "architect"
    assert runs[live]["conversation_id"] == conversation["id"]
    assert runs[old]["conversation_id"] is None  # the conversation moved on to another CLI
    assert api.get("/api/home").json()["counts"]["active_runs"] == len(
        api.get("/api/runs", params={"active": True}).json()
    )
    # They have no agent: filtering by one leaves them out.
    agent = api.post("/api/agents", json={"name": "QA", "role": "QA"}).json()
    assert api.get("/api/runs", params={"agent_id": agent["id"]}).json() == []


def test_a_link_marked_always_is_saved_without_its_condition(api: TestClient, tmp_path):
    """Phase 21: «always» has one form in the data, no condition (code review)."""
    folder = tmp_path / "web"
    folder.mkdir()
    project = api.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()
    body = {
        "stages": [{"name": n} for n in "ABCD"],
        "links": [
            {"source": 0, "target": 1, "condition": "toca la API", "always": True},
            {"source": 0, "target": 2, "condition": "toca los datos"},
            {"source": 1, "target": 3},
            {"source": 2, "target": 3},
        ],
    }
    saved = api.put(f"/api/projects/{project['id']}/pipeline", json=body)
    assert saved.status_code == 200, saved.text
    links = {
        (x["always"], x["condition"])
        for x in saved.json()["links"]
        if x["condition"] or x["always"]
    }
    assert links == {(True, ""), (False, "toca los datos")}
