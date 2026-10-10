from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_os.app import create_app
from agentic_os.config import Settings
from agentic_os.db.base import utcnow
from agentic_os.models import EventKind, Run, RunEvent, RunStatus


def make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path / "data")))


def add_run(client: TestClient, **fields) -> str:
    with client.app.state.sessionmaker() as db:
        run = Run(
            agent_name="Dev",
            agent_color="#4FD1C5",
            project_name="Web",
            cli="claude",
            prompt="Arregla el login",
            cwd=str(Path.cwd()),
            **fields,
        )
        db.add(run)
        db.commit()
        return run.id


def test_run_exposes_agent_reports_and_events_in_order(tmp_path: Path):
    with make_client(tmp_path) as client:
        run_id = add_run(
            client, status=RunStatus.COMPLETED, summary="Login arreglado", last_status="tests"
        )
        now = utcnow()
        with client.app.state.sessionmaker() as db:
            db.add_all(
                [
                    RunEvent(
                        run_id=run_id,
                        at=now,
                        kind=EventKind.MCP,
                        name="complete_task",
                        detail="Login arreglado",
                    ),
                    RunEvent(
                        run_id=run_id,
                        at=now - timedelta(seconds=5),
                        kind=EventKind.HOOK,
                        name="Stop",
                    ),
                ]
            )
            db.commit()

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "completed"
        assert (run["summary"], run["last_status"]) == ("Login arreglado", "tests")
        events = client.get(f"/api/runs/{run_id}/events").json()
        assert [(e["kind"], e["name"]) for e in events] == [
            ("hook", "Stop"),
            ("mcp", "complete_task"),
        ]
        assert events[1]["detail"] == "Login arreglado"
        assert client.get("/api/runs/nope/events").json()["detail"]["code"] == "run_not_found"


def test_events_go_with_their_run(tmp_path: Path):
    with make_client(tmp_path) as client:
        run_id = add_run(client, status=RunStatus.EXITED)
        with client.app.state.sessionmaker() as db:
            db.add(RunEvent(run_id=run_id, kind=EventKind.SYSTEM, name="prompt_sent"))
            db.commit()
            db.delete(db.get(Run, run_id))
            db.commit()
            assert db.scalars(select(RunEvent)).all() == []
