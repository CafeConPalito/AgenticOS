import pytest
from fastapi.testclient import TestClient


def create(client: TestClient, **body) -> dict:
    response = client.post("/api/agents", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_roundtrip(client: TestClient):
    assert client.get("/api/agents").json() == []
    agent = create(client, name="Dev", role="Desarrollador", cli="claude", model="sonnet")
    assert agent["permission_mode"] == "ask"
    assert agent["max_concurrency"] == 1
    assert agent["status"] == "active"
    assert agent["allowed_tools"] == []

    updated = client.patch(
        f"/api/agents/{agent['id']}",
        json={"model": "opus", "max_concurrency": 2, "allowed_tools": ["read", "edit", "read"]},
    ).json()
    assert updated["model"] == "opus"
    assert updated["max_concurrency"] == 2
    assert updated["allowed_tools"] == ["read", "edit"]  # de-duplicated
    assert updated["name"] == "Dev"  # untouched

    assert [a["id"] for a in client.get("/api/agents").json()] == [agent["id"]]
    assert client.delete(f"/api/agents/{agent['id']}").status_code == 204
    assert client.get(f"/api/agents/{agent['id']}").status_code == 404


def test_templates_are_listed_and_used(client: TestClient):
    templates = client.get("/api/agent-templates").json()
    assert [t["id"] for t in templates] == ["analyst", "developer", "qa", "writer", "sales"]

    agent = create(client, template="developer", name="Dev · Desarrollador")
    assert agent["template"] == "developer"
    assert agent["name"] == "Dev · Desarrollador"  # override wins
    assert agent["permission_mode"] == "autonomous"  # from the template
    assert "terminal" in agent["allowed_tools"]
    assert "complete_task" in agent["instructions"]

    plain = create(client, template="qa")
    assert plain["name"] == "QA"
    assert plain["cli"] == "agy"


def test_unknown_template(client: TestClient):
    response = client.post("/api/agents", json={"template": "astronaut"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_template"


def test_duplicate(client: TestClient):
    source = create(client, template="analyst")
    copy = client.post(f"/api/agents/{source['id']}/duplicate").json()
    assert copy["id"] != source["id"]
    assert copy["name"] == "Analista (copia)"
    assert copy["instructions"] == source["instructions"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "X", "cli": "cursor"}, "cli"),
        ({"name": "X", "max_concurrency": 0}, "max_concurrency"),
        ({"name": "X", "max_concurrency": 6}, "max_concurrency"),
        ({"name": "X", "permission_mode": "yolo"}, "permission_mode"),
        ({"name": "X", "allowed_tools": ["teleport"]}, "allowed_tools.0"),
        ({"name": "X", "color": "red"}, "color"),
        ({"name": "X", "unknown": 1}, "unknown"),
    ],
)
def test_validation_errors(client: TestClient, body: dict, field: str):
    response = client.post("/api/agents", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == field


def test_cannot_blank_the_name_on_update(client: TestClient):
    agent = create(client, name="Dev")
    response = client.patch(f"/api/agents/{agent['id']}", json={"name": ""})
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "name"


def test_not_found(client: TestClient):
    assert client.get("/api/agents/nope").json()["detail"]["code"] == "agent_not_found"
    assert client.patch("/api/agents/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/api/agents/nope").status_code == 404
