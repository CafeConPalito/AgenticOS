"""Which skills a run gets (phase 17, block 3): visibility and precedence (CA3), the stage over the
agent (CA4), the candidates by words and by vectors, the section's budgets and the tester."""

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_os.models import Pipeline, Run, RunSkill, Stage
from agentic_os.services.skills import config as skills_config
from agentic_os.services.skills import runtime
from agentic_os.services.skills import selection as sel


def _skill(client: TestClient, name: str, description: str, body: str = "", **level) -> dict:
    payload = {"scope": "general", "name": name, "description": description, "body": body, **level}
    response = client.post("/api/skills", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def world(client: TestClient, tmp_path: Path) -> dict:
    """Two agents, a project with a pipeline (stages Dev and QA) and skills at every level."""
    dev = client.post("/api/agents", json={"name": "Dev", "role": "Desarrollador"}).json()
    qa = client.post("/api/agents", json={"name": "QA", "role": "QA"}).json()
    folder = tmp_path / "web"
    folder.mkdir()
    project = client.post("/api/projects", json={"name": "Web", "path": str(folder)}).json()
    with client.app.state.sessionmaker() as db:
        pipeline = Pipeline(project_id=project["id"], name="Web")
        db.add(pipeline)
        db.flush()
        dev_stage = Stage(
            pipeline_id=pipeline.id, position=0, name="Desarrollo", agent_id=dev["id"]
        )
        qa_stage = Stage(pipeline_id=pipeline.id, position=1, name="QA", agent_id=qa["id"])
        db.add_all([dev_stage, qa_stage])
        db.commit()
        stages = {"dev": dev_stage.id, "qa": qa_stage.id}
    skills = {
        "migraciones": _skill(
            client, "migraciones-alembic", "Escribir migraciones de Alembic para la base de datos."
        ),
        "revision": _skill(client, "revision-codigo", "Revisar el código de una rama antes de QA."),
        "propuesta": _skill(client, "propuesta-comercial", "Redactar propuestas comerciales."),
        "tienda": _skill(
            client,
            "revision-codigo",
            "La revisión de esta tienda.",
            scope="project",
            project_id=project["id"],
        ),
        "mia": _skill(
            client, "notas-dev", "Notas del agente Dev.", scope="agent", agent_id=dev["id"]
        ),
    }
    return {"dev": dev, "qa": qa, "project": project, "stages": stages, "skills": skills}


def test_visible_by_level_with_the_most_specific_name_winning(client: TestClient, world):
    with client.app.state.sessionmaker() as db:
        names = {
            s.name: s.id for s in sel.visible(db, world["project"]["id"], [world["dev"]["id"]])
        }
        assert names["revision-codigo"] == world["skills"]["tienda"]["id"]  # project > general
        assert "notas-dev" in names
        others = {s.name for s in sel.visible(db, None, [world["qa"]["id"]])}
        assert "notas-dev" not in others  # another agent's
        # a subagent of Dev, run by QA, sees its parent's
        assert "notas-dev" in {
            s.name for s in sel.visible(db, None, [world["qa"]["id"], world["dev"]["id"]])
        }


def test_switched_off_skills_are_not_visible(client: TestClient, world):
    client.patch(f"/api/skills/{world['skills']['propuesta']['id']}", json={"enabled": False})
    with client.app.state.sessionmaker() as db:
        assert "propuesta-comercial" not in {s.name for s in sel.visible(db, None, [])}


def test_the_stage_wins_over_the_agent(client: TestClient, world):
    revision = world["skills"]["revision"]["id"]
    migraciones = world["skills"]["migraciones"]["id"]
    qa = world["qa"]["id"]
    client.put(
        f"/api/agents/{qa}/skill-modes", json={"modes": {revision: "auto", migraciones: "always"}}
    )
    stage = world["stages"]["qa"]
    client.put(
        f"/api/stages/{stage}/skill-modes",
        json={"modes": {revision: "always", migraciones: "never"}},
    )
    with client.app.state.sessionmaker() as db:
        skills = sel.visible(db, None, [qa])
        modes = sel.modes(db, skills, qa, stage)
        assert modes[revision] == ("always", "stage")
        assert modes[migraciones] == ("never", "stage")
        chosen = sel.select_skills(skills, modes, "Revisar la rama", limit=5)
        assert [o.skill.id for o in chosen.always] == [revision]
        assert (next(s for s, _ in chosen.excluded if s.id == migraciones), "never_stage") in [
            (s, r) for s, r in chosen.excluded
        ]
        # without the stage, the agent's «always» counts
        agent_only = sel.modes(db, skills, qa, None)
        assert agent_only[migraciones] == ("always", "agent")


def test_modes_api_shows_what_a_run_gets(client: TestClient, world):
    revision = world["skills"]["tienda"]["id"]  # in the project it hides the general one
    client.put(f"/api/agents/{world['qa']['id']}/skill-modes", json={"modes": {revision: "never"}})
    view = client.get(f"/api/stages/{world['stages']['qa']}/skill-modes").json()
    row = next(r for r in view if r["skill"]["id"] == revision)
    assert (row["mode"], row["effective"], row["set_by"]) == ("auto", "never", "agent")
    client.put(
        f"/api/stages/{world['stages']['qa']}/skill-modes", json={"modes": {revision: "always"}}
    )
    view = client.get(f"/api/stages/{world['stages']['qa']}/skill-modes").json()
    row = next(r for r in view if r["skill"]["id"] == revision)
    assert (row["mode"], row["effective"], row["set_by"]) == ("always", "always", "stage")
    back = client.put(
        f"/api/stages/{world['stages']['qa']}/skill-modes", json={"modes": {revision: "auto"}}
    ).json()
    assert next(r for r in back if r["skill"]["id"] == revision)["set_by"] == "agent"


def test_candidates_by_words_pick_the_matching_skill(client: TestClient, world):
    with client.app.state.sessionmaker() as db:
        skills = sel.visible(db, None, [])
        chosen = sel.select_skills(
            skills,
            sel.modes(db, skills, None, None),
            sel.task_query("Añadir columna", "Crear la migración de Alembic para la base de datos"),
            limit=2,
        )
    assert chosen.method == "words"
    assert chosen.candidates[0].skill.name == "migraciones-alembic"
    assert len(chosen.candidates) <= 2


def test_candidates_by_vector_respect_the_floor(client: TestClient, world):
    vectors = {"migraciones-alembic": [1, 0, 0], "revision-codigo": [0.8, 0.6, 0]}
    with client.app.state.sessionmaker() as db:
        skills = sel.visible(db, None, [])
        for skill in skills:
            skill.vector = np.array(vectors.get(skill.name, [0, 0, 1]), dtype=np.float32).tobytes()
            skill.vector_model = "fake"
        chosen = sel.select_skills(
            skills,
            sel.modes(db, skills, None, None),
            "migración",
            limit=5,
            embed_query=lambda _: np.array([1, 0, 0], dtype=np.float32),
            model="fake",
            floor=0.7,
        )
    assert chosen.method == "vector"
    assert [o.skill.name for o in chosen.candidates] == ["migraciones-alembic", "revision-codigo"]
    assert chosen.candidates[0].score == pytest.approx(1.0)


def test_a_skill_the_model_must_not_invoke_is_never_a_candidate(client: TestClient):
    response = client.post(
        "/api/skills/import",
        json={"scope": "general", "path": str(_manual_only(client))},
    )
    skill = response.json()["skill"]
    assert skill["model_invocable"] is False
    with client.app.state.sessionmaker() as db:
        skills = sel.visible(db, None, [])
        chosen = sel.select_skills(skills, sel.modes(db, skills, None, None), "despliegue", limit=5)
    assert ("despliegue-manual", "manual_only") in [(s.name, r) for s, r in chosen.excluded]


def _manual_only(client: TestClient) -> Path:
    folder = Path(client.app.state.settings.data_dir).parent / "manual" / "despliegue-manual"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: despliegue-manual\ndescription: Despliegue a producción.\n"
        "disable-model-invocation: true\n---\nPasos.\n",
        "utf-8",
    )
    return folder


def _run(db, world, stage: str | None = None) -> Run:
    run = Run(
        agent_id=world["qa"]["id"],
        project_id=world["project"]["id"],
        agent_name="QA",
        agent_color="#fff",
        project_name="Web",
        cli="claude",
        prompt="Revisar la rama antes de QA",
        cwd=".",
        stage_id=world["stages"][stage] if stage else None,
    )
    db.add(run)
    db.flush()
    return run


def test_a_run_records_its_offer_and_its_section_stays_in_budget(
    client: TestClient, world, tmp_path: Path
):
    revision = world["skills"]["tienda"]["id"]
    long_body = "Paso muy detallado de la revisión. " * 600  # ~5 000 tokens
    client.post(f"/api/skills/{revision}/versions", json={"body": long_body})
    client.put(
        f"/api/stages/{world['stages']['qa']}/skill-modes", json={"modes": {revision: "always"}}
    )
    lib = client.app.state.skills
    with client.app.state.sessionmaker() as db:
        skills_config.save(db, {"always_tokens": 1_000})
        run = _run(db, world, "qa")
        runtime.prepare_run(db, lib, tmp_path, run, None, None, runtime.Ranker())
        db.commit()
        rows = list(db.scalars(select(RunSkill).where(RunSkill.run_id == run.id)))
        fixed = next(r for r in rows if r.skill_id == revision)
        assert (fixed.offered, fixed.loaded_via, fixed.stage_name) == ("always", "context", "QA")
        assert fixed.pipeline_name == "Web"
        assert (tmp_path / run.id / "skills" / "revision-codigo" / "SKILL.md").exists()
        text = runtime.section(db, lib, tmp_path, run.id)
    assert text.startswith("## Skills")
    # too big for the budget: listed to load with use_skill instead of written whole
    assert "- revision-codigo (fijada; cárgala con `use_skill`)" in text
    assert "Paso muy detallado" not in text


def test_the_tester_says_what_a_run_would_get(client: TestClient, world):
    migraciones = world["skills"]["migraciones"]["id"]
    client.put(
        f"/api/stages/{world['stages']['dev']}/skill-modes",
        json={"modes": {world["skills"]["propuesta"]["id"]: "never"}},
    )
    result = client.post(
        "/api/skills/try",
        json={
            "text": "Crear la migración de Alembic de la tabla clientes",
            "agent_id": world["dev"]["id"],
            "stage_id": world["stages"]["dev"],
        },
    ).json()
    assert result["method"] == "words"
    assert result["candidates"][0]["skill"]["id"] == migraciones
    assert ("propuesta-comercial", "never_stage") in [
        (e["skill"]["name"], e["reason"]) for e in result["excluded"]
    ]
    assert result["section"].startswith("## Skills") and "migraciones-alembic" in result["section"]
