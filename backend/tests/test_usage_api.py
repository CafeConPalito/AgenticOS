"""The usage API: KPIs, series, breakdown, sessions, CSV, today, limits and «Reanudar»."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.models import Agent, Cli, InboxKind, Project, Run, RunStatus
from agentic_os.services import accounts, inbox


def seed(client: TestClient) -> dict[str, str]:
    sessions = client.app.state.sessionmaker
    with sessions() as db:
        agent = Agent(workspace_id=DEFAULT_WORKSPACE, name="Dev", color="#43D392")
        project = Project(workspace_id=DEFAULT_WORKSPACE, name="Web", path="D:/web", path_key="web")
        db.add_all([agent, project])
        db.flush()
        start = utcnow() - timedelta(minutes=30)
        for cost, tokens in ((1.25, 1000), (0.75, 500)):
            db.add(
                Run(
                    workspace_id=DEFAULT_WORKSPACE,
                    agent_id=agent.id,
                    project_id=project.id,
                    agent_name="Dev",
                    agent_color="#43D392",
                    project_name="Web",
                    cli="claude",
                    prompt="x",
                    cwd="D:/web",
                    status=RunStatus.COMPLETED,
                    started_at=start,
                    ended_at=start + timedelta(minutes=6),
                    cost_usd=cost,
                    output_tokens=tokens,
                    usage_status="final",
                    usage_source="cost-state",
                )
            )
        db.commit()
        return {"agent": agent.id, "project": project.id}


def test_usage_endpoints(client: TestClient):
    ids = seed(client)
    summary = client.get("/api/usage/summary").json()
    assert summary["kpis"]["cost_usd"] == 2.0
    assert summary["kpis"]["sessions"] == 2
    assert summary["kpis"]["agent_hours"] == 0.2

    daily = client.get("/api/usage/daily", params={"group": "project"}).json()
    assert len(daily["days"]) == 30
    assert daily["groups"][0]["name"] == "Web"
    assert daily["days"][-1]["cost"][ids["project"]] == 2.0

    breakdown = client.get("/api/usage/breakdown").json()
    assert breakdown["rows"][0]["name"] == "Dev" and breakdown["rows"][0]["share"] == 1.0

    rows = client.get("/api/usage/sessions", params={"sort": "cost", "dir": "asc"}).json()
    assert [r["cost_usd"] for r in rows] == [0.75, 1.25]
    assert rows[0]["usage_status"] == "final"
    filtered = client.get("/api/usage/sessions", params={"agent_id": "nobody"}).json()
    assert filtered == []

    csv = client.get("/api/usage/sessions.csv")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert csv.text.count("\r\n") == 3

    today = client.get("/api/usage/today").json()
    assert today["cost_usd"] == 2.0 and today["tokens"] == 1500
    assert today["agents"][0]["name"] == "Dev"
    assert [s["cli"] for s in today["limits"]] == ["claude", "agy"]
    assert today["limits"][0]["limit"] is None


def test_invalid_periods(client: TestClient):
    bad = client.get("/api/usage/summary", params={"from": "2026-10-12", "to": "2026-10-01"})
    assert bad.status_code == 422
    long = client.get("/api/usage/summary", params={"from": "2024-01-01", "to": "2026-10-01"})
    assert long.status_code == 422


def test_limits_settings_and_runs_carry_their_usage(client: TestClient):
    seed(client)
    states = client.get("/api/settings/usage-limits").json()
    assert [(s["cli"], s["limit"]) for s in states] == [("claude", None), ("agy", None)]
    claude, agy = (s["account_id"] for s in states)

    def put(claude_limit, agy_limit=None):
        return client.put(
            "/api/settings/usage-limits",
            json={
                "limits": [
                    {"account_id": claude, "daily_limit": claude_limit},
                    {"account_id": agy, "daily_limit": agy_limit},
                ]
            },
        )

    assert put(0).status_code == 422
    saved = put(1.5, 10)
    assert [(s["cli"], s["limit"]) for s in saved.json()] == [("claude", 1.5), ("agy", 10)]
    today = client.get("/api/usage/today").json()
    assert today["limits"][0]["reached"] is True
    pending = client.get("/api/inbox", params={"status": "pending"}).json()
    assert [item["kind"] for item in pending] == ["limit"]
    put(100)
    assert client.get("/api/inbox", params={"status": "pending"}).json() == []

    runs = client.get("/api/runs").json()
    assert runs[0]["usage"]["cost_usd"] in (1.25, 0.75)
    assert runs[0]["usage"]["status"] == "final"

    notifications = client.get("/api/settings/notifications").json()
    assert notifications["limits"] is True


def test_resume_a_quota_item(client: TestClient):
    with client.app.state.sessionmaker() as db:
        item = inbox.create(db, InboxKind.QUOTA, "Antigravity se ha quedado sin cuota", "x")
        item.command = accounts.default_for(db, Cli.AGY).id
        db.commit()
        item_id = item.id
    assert client.post(f"/api/inbox/{item_id}/answer", json={"text": "x"}).status_code == 409
    resumed = client.post(f"/api/inbox/{item_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "resolved"
    assert client.post(f"/api/inbox/{item_id}/resume").status_code == 409


def test_dates_are_local(client: TestClient):
    today = client.get("/api/usage/today").json()
    assert today["day"] == datetime.now().astimezone().date().isoformat()


def test_dismissing_a_quota_item_lets_the_task_go_on(client: TestClient):
    from agentic_os.models import Task, TaskStatus, WaitingReason
    from agentic_os.services import tasks as task_ops

    ids = seed(client)
    with client.app.state.sessionmaker() as db:
        project = db.get(Project, ids["project"])
        task = task_ops.create_task(db, project, "Algo", agent_id=ids["agent"])
        task_ops.mark_running(db, task, "run-x")
        task_ops.wait_for_human(db, task, WaitingReason.QUOTA, "Quota exhausted")
        item = inbox.create(db, InboxKind.QUOTA, "sin cuota", "x", task=task)
        item.command = "agy"
        db.commit()
        item_id, task_id = item.id, task.id
    dismissed = client.post(f"/api/inbox/{item_id}/dismiss").json()
    assert dismissed["resolution"] == "dismissed"
    with client.app.state.sessionmaker() as db:
        task = db.get(Task, task_id)
        assert (task.status, task.waiting_reason) == (TaskStatus.RUNNING, None)
    limits_today = client.get("/api/usage/today").json()["limits"]
    assert not any(s["quota_exhausted"] for s in limits_today)
