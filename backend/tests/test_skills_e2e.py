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
        folder = Path(settings.data_dir) / "runs" / run_id / "skills"
        assert wait_until(lambda: not folder.exists(), timeout=10)
