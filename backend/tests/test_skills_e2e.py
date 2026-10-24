"""Skills end to end (phase 17): a real run of the fake CLI, with a real MCP client. With
AGENTIC_OS_E2E_BINARY it is the packaged sidecar (CA15, block 12)."""

from __future__ import annotations

from pathlib import Path

from live_server import live_server
from test_scheduler_e2e import Api, settings_for, wait_until


def test_the_matching_skill_is_offered_loaded_and_recorded(tmp_path: Path):
    """CA6: a task that fits a skill. The run's context lists it, the agent loads it with
    use_skill, reads a support file, and the run records which skill, how and which version."""
    from test_hitl_e2e import setup

    project_folder = tmp_path / "web-claude"
    settings = settings_for(tmp_path)
    with live_server(settings) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        skill = api.post(
            "/api/skills",
            {
                "scope": "general",
                "name": "migraciones-alembic",
                "description": "Escribir y revisar migraciones de Alembic con SQLAlchemy.",
                "body": "# Migraciones\n1. Genera la migración con autogenerate.\n",
                "files": {"reference/pasos.md": {"text": "Revisa el downgrade."}},
            },
        )
        api.post(
            "/api/skills",
            {
                "scope": "general",
                "name": "propuesta-comercial",
                "description": "Redactar propuestas comerciales y presupuestos para clientes.",
            },
        )
        title = (
            "Crear la migración de Alembic de clientes; CONTEXTO: ctx.txt; "
            "SKILL: migraciones-alembic|skill.txt; "
            "FICHERO_SKILL: migraciones-alembic|reference/pasos.md|pasos.txt; TERMINA: hecho"
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(task["id"], "done")

        context = (project_folder / "ctx.txt").read_text("utf-8")
        assert "## Skills" in context
        assert "- migraciones-alembic: Escribir y revisar migraciones" in context
        loaded = (project_folder / "skill.txt").read_text("utf-8")
        assert "Genera la migración con autogenerate." in loaded
        assert (project_folder / "pasos.txt").read_text("utf-8") == "Revisa el downgrade."

        run_id = done["last_run_id"]
        rows = {r["skill_name"]: r for r in api.get(f"/api/runs/{run_id}/skills")}
        assert rows["migraciones-alembic"]["offered"] == "candidate"
        assert rows["migraciones-alembic"]["rank"] == 1
        assert rows["migraciones-alembic"]["loaded_via"] == "tool"
        assert rows["migraciones-alembic"]["version"] == 1
        names = [e["name"] for e in api.get(f"/api/runs/{run_id}/events") if e["kind"] == "mcp"]
        assert "use_skill" in names and "read_skill_file" in names
        listed = {s["id"]: s for s in api.get("/api/skills")}
        assert listed[skill["id"]]["used"] == 1
        # the run's copies of the skills are removed when it ends
        folder = Path(settings.data_dir) / "runs" / run_id / "plugin"
        assert wait_until(lambda: not folder.exists(), timeout=10)


def test_import_run_propose_and_approve(tmp_path: Path):
    """CA15 (also with the packaged app): import a skill folder, a run loads it, the agent
    proposes another one, the person approves it from the Inbox's data and the next run gets it."""
    from test_hitl_e2e import setup

    source = tmp_path / "mis-skills" / "informes-semanales"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: informes-semanales\ndescription: Redactar el informe semanal del proyecto "
        "con lo hecho y lo pendiente.\n---\n\n# Informe\n1. Lista lo hecho.\n",
        "utf-8",
    )
    project_folder = tmp_path / "web-claude"
    with live_server(settings_for(tmp_path)) as server:
        api = Api(server)
        agent, project = setup(api, tmp_path, "claude")
        imported = api.post("/api/skills/import", {"scope": "general", "path": str(source)})
        assert imported["skill"]["name"] == "informes-semanales"
        title = (
            "Redactar el informe semanal; SKILL: informes-semanales|skill.txt; "
            "PROPONE_SKILL: plantilla-de-actas|propuesta.txt; TERMINA: hecho"
        )
        task = api.post("/api/tasks", {"project_id": project, "agent_id": agent, "title": title})
        done = api.wait_status(task["id"], "done")
        assert "Lista lo hecho." in (project_folder / "skill.txt").read_text("utf-8")
        assert "Propuesta registrada" in (project_folder / "propuesta.txt").read_text("utf-8")
        rows = api.get(f"/api/runs/{done['last_run_id']}/skills")
        assert rows[0]["skill_name"] == "informes-semanales" and rows[0]["loaded_via"] == "tool"

        item = next(i for i in api.get("/api/inbox") if i["kind"] == "skill")
        proposal = api.get(f"/api/skills/proposals/{item['skill_version_id']}")
        assert proposal["new_skill"] and proposal["executables"] == []
        api.post(f"/api/skills/proposals/{item['skill_version_id']}/accept", {"scope": "general"})

        second = api.post(
            "/api/tasks",
            {
                "project_id": project,
                "agent_id": agent,
                "title": "Las actas; SKILL: plantilla-de-actas|segunda.txt; TERMINA: hecho",
            },
        )
        api.wait_status(second["id"], "done")
        assert "Primer paso comprobado." in (project_folder / "segunda.txt").read_text("utf-8")
