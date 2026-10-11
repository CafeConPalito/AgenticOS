from datetime import UTC, datetime, timedelta

from agentic_os.models import Agent, AuthorKind, MemoryNote, Project
from agentic_os.services.context import build_context, build_instructions
from agentic_os.services.memory import render_memory
from agentic_os.services.tasks import TaskContext


def note(text: str, minutes: int, agent: str | None = None) -> MemoryNote:
    at = datetime(2026, 10, 11, 8, 0, tzinfo=UTC) + timedelta(minutes=minutes)
    kind = AuthorKind.AGENT if agent else AuthorKind.USER
    return MemoryNote(author_kind=kind, author_name=agent or "", text=text, created_at=at)


def test_instructions_carry_role_memory_and_the_agentic_os_rules():
    agent = Agent(name="Dev", role="Desarrollador", instructions="Escribe tests primero.")
    project = Project(name="Web", path="D:/web")
    text = build_instructions(agent, project, "D:/web", render_memory([note("Usa pnpm.", 0)]))
    assert text.startswith("# Tu rol: Dev · Desarrollador\n\nEscribe tests primero.")
    assert "# Proyecto: Web\nCarpeta de trabajo: D:/web" in text
    assert "## Memoria del proyecto\n### " in text
    assert "· Tú\nUsa pnpm." in text
    for tool in ("report_status", "write_project_memory", "complete_task", "get_context"):
        assert tool in text
    assert build_context(text, " Arregla el login ").endswith("# Tarea\nArregla el login\n")


def test_empty_memory():
    agent = Agent(name="QA", role="", instructions="")
    text = build_instructions(agent, None, "D:/x")
    assert "## Memoria del proyecto\n(vacía)" in text
    assert text.startswith("# Tu rol: QA\n\n# Proyecto")


def test_memory_keeps_the_most_recent_notes_in_order():
    notes = [note("vieja " + "x" * 50, 0, "Dev"), note("media", 1, "QA"), note("nueva", 2)]
    full = render_memory(notes)
    assert full.index("vieja") < full.index("media") < full.index("nueva")
    assert "· Dev\nvieja" in full and "· QA\nmedia" in full and "· Tú\nnueva" in full

    short = render_memory(notes, limit=80)
    assert "vieja" not in short
    assert short.startswith("[…] (hay notas más antiguas que no se muestran)\n\n### ")
    assert short.index("media") < short.index("nueva")


def test_a_single_huge_note_keeps_its_end():
    text = render_memory([note("inicio " + "x" * 100 + " final", 0)], limit=40)
    assert text.startswith("[…] ") and text.endswith("final") and "inicio" not in text


def test_task_stage_history_and_variables():
    agent = Agent(
        name="QA",
        role="Tester",
        instructions="Revisa $TAREA en $PROYECTO ($ETAPA), dentro de $WORKSPACE.",
    )
    task = TaskContext(
        code="T-7",
        title="Login con Google",
        description="Usa OAuth.",
        stage_name="QA",
        stage_index=3,
        stage_count=3,
        can_reject=True,
        history=("- Desarrollo · Dev terminó: login hecho",),
        rejection="Falta el test del callback",
        branch="agentic/T-7",
    )
    text = build_instructions(agent, Project(name="Web"), "D:/web.wt/T-7", "", task)
    assert "Revisa T-7 · Login con Google en Web (QA), dentro de D:/web.wt/T-7." in text
    assert "# Tarea T-7: Login con Google\nEtapa 3 de 3: QA\nRama de trabajo: agentic/T-7" in text
    assert "## Vuelve a ti porque se rechazó\nFalta el test del callback" in text
    assert "## Historial de la tarea\n- Desarrollo · Dev terminó: login hecho" in text
    assert 'verdict="rejected"' in text
    # A scheduled run's context already carries its task: no second "# Tarea" block.
    assert build_context(text, None) == text


def test_manual_runs_have_no_task_nor_verdict_rules():
    agent = Agent(name="Dev", role="", instructions="Proyecto $PROYECTO, etapa [$ETAPA].")
    text = build_instructions(agent, Project(name="Web"), "D:/web")
    assert "Proyecto Web, etapa []." in text
    assert "# Tarea" not in text and "verdict" not in text
