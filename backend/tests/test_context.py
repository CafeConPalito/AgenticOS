from agentic_os.models import Agent, Project
from agentic_os.services.context import MEMORY_LIMIT, build_context, build_instructions


def test_instructions_carry_role_memory_and_the_agentic_os_rules():
    agent = Agent(name="Dev", role="Desarrollador", instructions="Escribe tests primero.")
    project = Project(name="Web", path="D:/web", memory="Usa pnpm.")
    text = build_instructions(agent, project, "D:/web")
    assert text.startswith("# Tu rol: Dev · Desarrollador\n\nEscribe tests primero.")
    assert "# Proyecto: Web\nCarpeta de trabajo: D:/web" in text
    assert "## Memoria del proyecto\nUsa pnpm." in text
    for tool in ("report_status", "write_project_memory", "complete_task", "get_context"):
        assert tool in text
    assert build_context(text, " Arregla el login ").endswith("# Tarea\nArregla el login\n")


def test_empty_and_long_memory():
    agent = Agent(name="QA", role="", instructions="")
    assert "## Memoria del proyecto\n(vacía)" in build_instructions(agent, None, "D:/x")
    project = Project(name="Web", path="D:/web", memory="viejo " + "x" * MEMORY_LIMIT + " nuevo")
    text = build_instructions(agent, project, "D:/web")
    assert "(se muestra lo más reciente)" in text
    assert "viejo" not in text and text.count("nuevo") == 1
    assert text.startswith("# Tu rol: QA\n\n# Proyecto")
