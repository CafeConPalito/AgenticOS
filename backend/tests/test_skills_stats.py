"""Usage statistics of the skills (phase 17, block 10; spec E): CA19 (exact figures with filters,
breakdowns, «never used», daily series and CSV), CA20 (fast with 50 skills and 20 000 runs) and
CA21 (the figures survive deleting an agent, a stage, a pipeline or an account)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from agentic_os.models import (
    Agent,
    CliAccount,
    Pipeline,
    Project,
    Run,
    RunSkill,
    Stage,
    Team,
    Verdict,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _skill(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/skills", json={"scope": "general", "name": name, "description": f"Hace {name}."}
    )
    return response.json()["id"]


@pytest.fixture
def world(client: TestClient, tmp_path: Path) -> dict:
    """Two agents (one in a team), a project with a pipeline (Dev, QA), two accounts, two CLIs,
    and runs that loaded (or were only offered) three skills."""
    review, migrations, unused = (_skill(client, n) for n in ("revision", "migraciones", "nadie"))
    with client.app.state.sessionmaker() as db:
        team = Team(name="Backend")
        db.add(team)
        db.flush()
        dev = Agent(name="Dev", team_id=team.id)
        qa = Agent(name="QA", cli="agy")
        project = Project(name="Web", path=str(tmp_path), path_key=str(tmp_path))
        claude = CliAccount(cli="claude", label="Personal")
        agy = CliAccount(cli="agy", label="Trabajo")
        db.add_all([dev, qa, project, claude, agy])
        db.flush()
        pipeline = Pipeline(project_id=project.id, name="Web")
        db.add(pipeline)
        db.flush()
        stage_dev = Stage(pipeline_id=pipeline.id, position=0, name="Desarrollo", agent_id=dev.id)
        stage_qa = Stage(pipeline_id=pipeline.id, position=1, name="QA", agent_id=qa.id)
        db.add_all([stage_dev, stage_qa])
        db.flush()

        def run(agent, stage, account, day, *, status="completed", verdict=None, cost=0.10):
            r = Run(
                agent_id=agent.id,
                project_id=project.id,
                agent_name=agent.name,
                agent_color="#fff",
                project_name="Web",
                cli=account.cli,
                model="sonnet" if account.cli == "claude" else "gemini",
                prompt="p",
                cwd=".",
                stage_id=stage.id,
                account_id=account.id,
                account_label=account.label,
                status=status,
                verdict=verdict,
                cost_usd=cost,
                input_tokens=1000,
                output_tokens=500,
                started_at=NOW - timedelta(days=day),
            )
            db.add(r)
            db.flush()
            return r

        def offer(r, skill, stage, *, via=None, offered="candidate", day=0):
            db.add(
                RunSkill(
                    run_id=r.id,
                    skill_id=skill,
                    skill_name="x",
                    offered=offered,
                    loaded_via=via,
                    loaded_at=NOW - timedelta(days=day) if via else None,
                    stage_name=stage.name,
                    pipeline_id=pipeline.id,
                    pipeline_name="Web",
                    team_id=team.id if r.agent_id == dev.id else None,
                    team_name="Backend" if r.agent_id == dev.id else "",
                )
            )

        # Dev in Desarrollo, Claude: review loaded twice (tool, native), migrations offered once
        r1 = run(dev, stage_dev, claude, 0, cost=0.20)
        offer(r1, review, stage_dev, via="tool")
        offer(r1, migrations, stage_dev)
        r2 = run(dev, stage_dev, claude, 1, status="failed", cost=0.40)
        offer(r2, review, stage_dev, via="native", day=1)
        # QA in QA, agy: review always (context), approved and rejected
        r3 = run(qa, stage_qa, agy, 2, verdict=Verdict.APPROVED, cost=None)
        offer(r3, review, stage_qa, via="context", offered="always", day=2)
        r4 = run(qa, stage_qa, agy, 10, verdict=Verdict.REJECTED)
        offer(r4, review, stage_qa, via="context", offered="always", day=10)
        offer(r4, migrations, stage_qa, via="tool", offered="requested", day=10)
        db.commit()
        ids = {
            "dev": dev.id,
            "qa": qa.id,
            "team": team.id,
            "pipeline": pipeline.id,
            "stage_qa": stage_qa.id,
            "claude": claude.id,
            "agy": agy.id,
            "runs": [r1.id, r2.id, r3.id, r4.id],
        }
    return {"review": review, "migrations": migrations, "unused": unused, **ids}


def _rows(client: TestClient, **params) -> dict[str, dict]:
    data = client.get("/api/skills/stats", params=params).json()
    return {(r["skill_id"], r["group_key"]): r for r in data["rows"]}


def test_the_figures_of_each_skill_are_exact(client: TestClient, world):
    rows = _rows(client)
    review = rows[(world["review"], None)]
    assert (review["offered"], review["loaded"], review["rate"]) == (4, 4, 1.0)
    assert (review["runs"], review["tasks"]) == (4, 0)
    assert (review["done"], review["failed"], review["approved"], review["rejected"]) == (
        3,
        1,
        1,
        1,
    )
    assert review["avg_cost"] == pytest.approx(
        (0.20 + 0.40 + 0.10) / 3, abs=1e-5
    )  # a run without cost
    assert review["avg_tokens"] == 1500
    assert (review["via_context"], review["via_tool"], review["via_native"]) == (2, 1, 1)
    assert review["last_used"].startswith("2026-10-20")
    migrations = rows[(world["migrations"], None)]
    # offered once (not loaded) and asked for once by name: the rate counts only the offered
    assert (migrations["offered"], migrations["loaded"], migrations["rate"]) == (1, 1, 0.0)
    assert next(iter(rows)) == (world["review"], None)  # most loaded first


@pytest.mark.parametrize(
    ("params", "loaded"),
    [
        ({"agent_id": "dev"}, 2),
        ({"team_id": "team"}, 2),
        ({"stage_id": "stage_qa"}, 2),
        ({"cli": "agy"}, 2),
        ({"account_id": "claude"}, 2),
        ({"model": "sonnet"}, 2),
        ({"via": "context"}, 2),
        ({"pipeline_id": "pipeline"}, 4),
        ({"from": "2026-10-19", "to": "2026-10-20"}, 2),
        ({"agent_id": "qa", "from": "2026-10-15"}, 1),
    ],
)
def test_filters_combine(client: TestClient, world, params, loaded):
    resolved = {k: world.get(v, v) if k.endswith("_id") else v for k, v in params.items()}
    assert _rows(client, **resolved)[(world["review"], None)]["loaded"] == loaded


def test_breakdowns_by_every_dimension(client: TestClient, world):
    by_agent = _rows(client, group_by="agent")
    assert by_agent[(world["review"], world["dev"])]["loaded"] == 2
    assert by_agent[(world["review"], world["qa"])]["group_label"] == "QA"
    by_stage = _rows(client, group_by="stage")
    assert by_stage[(world["review"], "QA")]["via_context"] == 2
    by_cli = _rows(client, group_by="cli")
    assert {k[1] for k in by_cli if k[0] == world["review"]} == {"claude", "agy"}
    for group in ("team", "project", "pipeline", "account", "model"):
        rows = _rows(client, group_by=group)
        assert sum(r["loaded"] for k, r in rows.items() if k[0] == world["review"]) == 4


def test_never_used_and_sorting(client: TestClient, world):
    never = _rows(client, unused="never_offered")
    assert set(never) == {(world["unused"], None)}
    assert never[(world["unused"], None)]["offered"] == 0
    loaded_never = _rows(client, unused="never_loaded", cli="claude")
    assert set(loaded_never) == {(world["migrations"], None), (world["unused"], None)}
    by_name = client.get("/api/skills/stats", params={"sort": "name", "desc": False}).json()
    assert [r["name"] for r in by_name["rows"]] == ["migraciones", "revision"]


def test_daily_series_runs_behind_a_figure_and_csv(client: TestClient, world):
    days = client.get(
        "/api/skills/stats/daily",
        params={"skill_ids": world["review"], "from": "2026-10-18", "to": "2026-10-20"},
    ).json()
    assert [d["day"] for d in days] == ["2026-10-18", "2026-10-19", "2026-10-20"]
    assert [d["loads"].get(world["review"], 0) for d in days] == [1, 1, 1]
    behind = client.get(
        "/api/skills/stats/runs",
        params={"skill_id": world["review"], "group_by": "agent", "group_key": world["qa"]},
    ).json()
    assert [r["run_id"] for r in behind] == [world["runs"][2], world["runs"][3]]
    assert behind[0]["stage_name"] == "QA" and behind[0]["account_label"] == "Trabajo"
    csv = client.get("/api/skills/stats.csv", params={"group_by": "cli"})
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("Skill;Grupo;Ofrecida;Cargada")
    # revision in both CLIs; migraciones in agy (asked by name) and in claude (only offered)
    assert len(lines) == 1 + 4


def test_figures_survive_deleting_what_they_were_about(client: TestClient, world):
    before = _rows(client, group_by="pipeline")
    with client.app.state.sessionmaker() as db:
        for model, key in ((Stage, "stage_qa"), (Pipeline, "pipeline")):
            db.delete(db.get(model, world[key]))
        db.commit()
    assert client.delete(f"/api/agents/{world['qa']}").status_code in (200, 204)
    client.delete(f"/api/accounts/{world['agy']}")
    after = _rows(client, group_by="pipeline")
    assert after[(world["review"], world["pipeline"])]["loaded"] == 4
    assert before[(world["review"], world["pipeline"])]["loaded"] == 4
    by_agent = _rows(client, group_by="agent")
    assert sum(r["loaded"] for k, r in by_agent.items() if k[0] == world["review"]) == 4
    assert any(r["group_label"] == "QA" for r in by_agent.values())


def test_fifty_skills_and_twenty_thousand_runs_answer_in_under_a_second(client: TestClient):
    """CA20: the aggregate is one SQL query over indexed tables."""
    ids = [_skill(client, f"skill-{i:02d}") for i in range(50)]
    with client.app.state.sessionmaker() as db:
        agent = Agent(name="Dev")
        db.add(agent)
        db.flush()
        runs, offers = [], []
        for i in range(20_000):
            run_id = f"run-{i:05d}"
            runs.append(
                {
                    "id": run_id,
                    "workspace_id": "default",
                    "created_at": NOW,
                    "updated_at": NOW,
                    "kind": "agent",
                    "agent_id": agent.id,
                    "agent_name": "Dev",
                    "agent_color": "#fff",
                    "project_name": "",
                    "cli": "claude" if i % 2 else "agy",
                    "model": "sonnet",
                    "prompt": "p",
                    "cwd": ".",
                    "status": "completed",
                    "activity": "idle",
                    "cols": 120,
                    "rows": 32,
                    "log_path": "",
                    "extra_transcripts": [],
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "thinking_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "usage_models": {},
                    "usage_status": "pending",
                    "log_purged": False,
                    "account_label": "",
                    "started_at": NOW - timedelta(minutes=i),
                }
            )
            for j in range(3):
                offers.append(
                    {
                        "id": f"{run_id}-{j}",
                        "run_id": run_id,
                        "skill_id": ids[(i + j) % 50],
                        "skill_name": "x",
                        "offered": "candidate",
                        "rank": j + 1,
                        "loaded_via": "tool" if j == 0 else None,
                        "loaded_at": NOW if j == 0 else None,
                        "stage_name": "",
                        "pipeline_name": "",
                        "team_name": "",
                        "created_at": NOW,
                    }
                )
        db.execute(insert(Run), runs)
        db.execute(insert(RunSkill), offers)
        db.commit()
    for params in ({}, {"group_by": "cli"}, {"cli": "claude", "sort": "rate"}):
        started = time.perf_counter()
        response = client.get("/api/skills/stats", params=params)
        took = time.perf_counter() - started
        assert response.status_code == 200
        assert took < 1.0, (params, took)
    total = sum(r["loaded"] for r in client.get("/api/skills/stats").json()["rows"])
    assert total == 20_000
