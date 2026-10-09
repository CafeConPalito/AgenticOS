from fastapi.testclient import TestClient

from agentic_os import __version__


def test_health_returns_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "name": "Agentic OS", "version": __version__}


def test_cors_allows_vite_origin(client: TestClient):
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
