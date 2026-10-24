"""Which connections a run receives (phase 18, block 4): CA5 (general, project and agent levels,
what an agent has taken away, switched-off ones) and CA6 (what a stage takes away, also a branch
of a pipeline, and only in that stage)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_os.models import Pipeline, Stage
from agentic_os.services.connections import resolve


def _connection(client: TestClient, name: str, **extra) -> dict:
    response = client.post("/api/connections", json={"name": name, "command": "x", **extra})
    assert response.status_code == 201, response.text
    return response.json()[0]


@pytest.fixture
def world(client: TestClient, tmp_path: Path) -> dict:
    """Two agents, two projects, a pipeline with Dev and QA stages, and a fork's branch."""
    dev = client.post("/api/agents", json={"name": "Dev"}).json()
    qa = client.post("/api/agents", json={"name": "QA"}).json()
    folders = []
    for name in ("web", "api"):
        folder = tmp_path / name
        folder.mkdir()
        folders.append(
            client.post("/api/projects", json={"name": name, "path": str(folder)}).json()
        )
    web, api = folders
    with client.app.state.sessionmaker() as db:
        pipeline = Pipeline(project_id=web["id"], name="Web")
        db.add(pipeline)
        db.flush()
        stages = [
            Stage(pipeline_id=pipeline.id, position=0, name="Dev", agent_id=dev["id"]),
            Stage(pipeline_id=pipeline.id, position=1, name="QA", agent_id=qa["id"]),
            Stage(pipeline_id=pipeline.id, position=2, name="Dev frontend", agent_id=dev["id"]),
        ]
        db.add_all(stages)
        db.commit()
        ids = {"dev": stages[0].id, "qa": stages[1].id, "branch": stages[2].id}
    return {"dev": dev["id"], "qa": qa["id"], "web": web["id"], "api": api["id"], "stages": ids}


def _names(report: resolve.Report) -> list[str]:
    return [e.connection.name for e in report.effective]


def test_a_run_gets_the_general_project_and_agent_connections(client: TestClient, world):
    _connection(client, "github", level={"scope": "general"})
    _connection(client, "tienda-db", level={"scope": "project", "project_id": world["web"]})
    _connection(client, "api-db", level={"scope": "project", "project_id": world["api"]})
    _connection(client, "notas", level={"scope": "agent", "agent_id": world["dev"]})
    _connection(client, "suelta")  # in the catalog, given to nobody
    with client.app.state.sessionmaker() as db:
        dev_in_web = resolve.resolve(db, world["dev"], world["web"], None)
        assert _names(dev_in_web) == ["github", "notas", "tienda-db"]
        qa_in_web = resolve.resolve(db, world["qa"], world["web"], None)
        assert _names(qa_in_web) == ["github", "tienda-db"]  # «notas» is Dev's
        dev_in_api = resolve.resolve(db, world["dev"], world["api"], None)
        assert _names(dev_in_api) == ["api-db", "github", "notas"]
        nowhere = resolve.resolve(db, None, None, None)  # a manual run without project
        assert _names(nowhere) == ["github"]


def test_the_most_concrete_level_is_the_one_reported(client: TestClient, world):
    created = _connection(client, "github", level={"scope": "general"})
    for level in (
        {"scope": "project", "project_id": world["web"]},
        {"scope": "agent", "agent_id": world["dev"]},
    ):
        client.post(f"/api/connections/{created['id']}/assignments", json=level)
    with client.app.state.sessionmaker() as db:
        [only] = resolve.resolve(db, world["dev"], world["web"], None).effective
        assert only.level == "agent"
        [other] = resolve.resolve(db, world["qa"], world["web"], None).effective
        assert other.level == "project"


def test_a_switched_off_connection_is_not_sent(client: TestClient, world):
    created = _connection(client, "github", level={"scope": "general"})
    client.patch(f"/api/connections/{created['id']}", json={"enabled": False})
    with client.app.state.sessionmaker() as db:
        report = resolve.resolve(db, world["dev"], world["web"], None)
        assert report.effective == []
        assert [(x.connection.name, x.reason) for x in report.excluded] == [("github", "disabled")]


def test_an_agent_can_have_a_connection_taken_away(client: TestClient, world):
    db_conn = _connection(
        client, "tienda-db", level={"scope": "project", "project_id": world["web"]}
    )
    _connection(client, "github", level={"scope": "general"})
    put = client.put(
        f"/api/agents/{world['qa']}/connections",
        params={"project_id": world["web"]},
        json={"excluded": [db_conn["id"]]},
    )
    assert put.status_code == 200
    view = put.json()
    assert [e["connection"]["name"] for e in view["effective"]] == ["github"]
    assert [(x["connection"]["name"], x["reason"]) for x in view["excluded"]] == [
        ("tienda-db", "agent")
    ]
    assert view["excluded_ids"] == [db_conn["id"]]
    dev = client.get(f"/api/agents/{world['dev']}/connections", params={"project_id": world["web"]})
    assert [e["connection"]["name"] for e in dev.json()["effective"]] == ["github", "tienda-db"]
    # putting an empty list gives it back
    back = client.put(f"/api/agents/{world['qa']}/connections", json={"excluded": []}).json()
    assert back["excluded_ids"] == []


def test_a_stage_takes_it_away_only_there(client: TestClient, world):
    db_conn = _connection(
        client, "tienda-db", level={"scope": "project", "project_id": world["web"]}
    )
    _connection(client, "github", level={"scope": "general"})
    stages = world["stages"]
    client.put(f"/api/stages/{stages['qa']}/connections", json={"excluded": [db_conn["id"]]})
    with client.app.state.sessionmaker() as db:
        in_qa = resolve.resolve(db, world["qa"], world["web"], stages["qa"])
        assert _names(in_qa) == ["github"]
        assert [(x.connection.name, x.reason) for x in in_qa.excluded] == [("tienda-db", "stage")]
        # the same agent in another stage, and the stage-less run, still get it
        assert _names(resolve.resolve(db, world["qa"], world["web"], stages["dev"])) == [
            "github",
            "tienda-db",
        ]
        assert _names(resolve.resolve(db, world["qa"], world["web"], None)) == [
            "github",
            "tienda-db",
        ]


def test_a_branch_of_a_fork_is_a_stage_too(client: TestClient, world):
    db_conn = _connection(
        client, "tienda-db", level={"scope": "project", "project_id": world["web"]}
    )
    stages = world["stages"]
    client.put(f"/api/stages/{stages['branch']}/connections", json={"excluded": [db_conn["id"]]})
    view = client.get(f"/api/stages/{stages['branch']}/connections").json()
    assert view["effective"] == [] and view["excluded"][0]["reason"] == "stage"
    assert view["agent_id"] == world["dev"]
    assert client.get(f"/api/stages/{stages['dev']}/connections").json()["effective"]


def test_the_agent_and_the_stage_exclusions_add_up(client: TestClient, world):
    a = _connection(client, "uno", level={"scope": "general"})
    b = _connection(client, "dos", level={"scope": "general"})
    client.put(f"/api/agents/{world['qa']}/connections", json={"excluded": [a["id"]]})
    client.put(f"/api/stages/{world['stages']['qa']}/connections", json={"excluded": [b["id"]]})
    with client.app.state.sessionmaker() as db:
        report = resolve.resolve(db, world["qa"], world["web"], world["stages"]["qa"])
        assert report.effective == []
        assert sorted((x.connection.name, x.reason) for x in report.excluded) == [
            ("dos", "stage"),
            ("uno", "agent"),
        ]


def test_deleting_a_connection_or_an_agent_cleans_up(client: TestClient, world):
    a = _connection(client, "uno", level={"scope": "agent", "agent_id": world["dev"]})
    client.put(f"/api/agents/{world['qa']}/connections", json={"excluded": [a["id"]]})
    client.delete(f"/api/agents/{world['dev']}")
    assert client.get(f"/api/connections/{a['id']}").json()["assignments"] == []
    client.delete(f"/api/connections/{a['id']}")
    with client.app.state.sessionmaker() as db:
        assert resolve.excluded_ids(db, agent_id=world["qa"]) == []


def test_assignments_are_added_listed_and_removed(client: TestClient, world):
    created = _connection(client, "github")
    url = f"/api/connections/{created['id']}/assignments"
    first = client.post(url, json={"scope": "project", "project_id": world["web"]})
    assert first.status_code == 201
    client.post(url, json={"scope": "project", "project_id": world["web"]})  # idempotent
    client.post(url, json={"scope": "project", "project_id": world["api"]})
    listed = client.get(url).json()
    assert len(listed) == 2
    assert client.delete(f"{url}/{listed[0]['id']}").status_code == 204
    assert len(client.get(url).json()) == 1
    assert client.delete(f"{url}/{listed[0]['id']}").status_code == 404
    bad = client.post(url, json={"scope": "agent", "project_id": world["web"]})
    assert bad.status_code == 422


def test_the_preview_counts_the_tools_the_agent_will_see(client: TestClient, world):
    conn = _connection(client, "github", level={"scope": "general"})
    tools = [
        {"name": "read", "description": "Read a thing", "input_schema": {"type": "object"}},
        {"name": "write", "description": "Write a thing", "input_schema": {"type": "object"}},
    ]
    with client.app.state.sessionmaker() as db:
        from agentic_os.models import McpConnection

        row = db.get(McpConnection, conn["id"])
        row.tools = tools
        db.commit()
    everything = client.post("/api/connections/try", json={"agent_id": world["dev"]}).json()
    assert everything["total_tools"] == 2 and everything["total_tokens"] > 0
    client.patch(
        f"/api/connections/{conn['id']}", json={"tool_mode": "selected", "allowed_tools": ["read"]}
    )
    selected = client.post("/api/connections/try", json={"agent_id": world["dev"]}).json()
    assert selected["total_tools"] == 1 and selected["total_tokens"] < everything["total_tokens"]
    via_stage = client.post(
        "/api/connections/try", json={"stage_id": world["stages"]["dev"]}
    ).json()
    assert via_stage["total_tools"] == 1  # the stage brings its agent and its project
