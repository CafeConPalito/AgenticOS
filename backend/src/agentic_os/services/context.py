"""Instructions a run starts with: the agent's role, the project memory, the task and its stage,
and how to work with Agentic OS. Claude Code gets them as an appended system prompt, agy as
plugin rules, and any agent can read them again with the `get_context` MCP tool."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentic_os.models import Agent, Project

if TYPE_CHECKING:
    from agentic_os.services.tasks import TaskContext

AGENTIC_OS_RULES = """\
# Cómo trabajar con Agentic OS
Trabajas dentro de Agentic OS, que coordina a varios agentes. Tienes el servidor MCP `agentic-os`:
- `report_status`: cuenta brevemente en qué estás cada vez que empieces algo relevante.
- `write_project_memory`: si descubres algo útil para futuras tareas en este proyecto \
(convenciones, decisiones, trampas), guárdalo en una nota breve.
- `complete_task`: cuando hayas terminado, llámala con un resumen de lo hecho y de lo que \
queda pendiente. Después no sigas trabajando: Agentic OS cerrará la sesión.
- `get_context`: vuelve a leer estas instrucciones, la tarea y la memoria del proyecto.
- `spawn_subagent`: si tu agente puede lanzar subagentes, reparte en paralelo una parte \
independiente del trabajo (otro agente o tú mismo); su resultado te llegará como un mensaje.
- `create_subtask`: si tu agente puede crear tareas, deja en cola trabajo para más adelante.
- `request_human`: si necesitas una decisión o un dato de la persona, o algo que solo ella \
puede hacer (una clave, un acceso), pídeselo con una pregunta corta y el contexto necesario. \
Después termina tu turno: su respuesta te llegará como un mensaje nuevo. No lo uses para lo \
que puedas decidir tú.
"""

VERDICT_RULES = """\
## Tu veredicto
Esta etapa revisa el trabajo de las anteriores. Al terminar, llama a `complete_task` con:
- `verdict="approved"` si el trabajo es correcto y la tarea puede seguir;
- `verdict="rejected"` si hay que corregir algo: en `summary` explica con precisión qué falla \
y qué hay que cambiar. La tarea volverá a la etapa anterior con tu explicación.
"""


GIT_RULES = """\
## Git
Puedes usar git libremente (commit, ramas, merge, rebase, push…) sin pedir permiso. \
Commitea tu trabajo en la rama de trabajo de cada repositorio. Agentic OS registra lo que \
haces con git en esta ejecución y la persona puede deshacerlo."""


@dataclass(frozen=True)
class RepoLine:
    """One repository of the project as the agent sees it (phase 12)."""

    name: str
    path: str  # relative to the working folder when it is inside it
    branch: str | None = None  # the task's working branch here
    base: str | None = None


def repos_section(repos: Sequence[RepoLine], cwd: str) -> str | None:
    """Lists the repositories when there is more than the working folder itself to explain."""
    if not repos or (len(repos) == 1 and repos[0].path in ("", ".")):
        return None
    lines = ["## Repositorios del proyecto", "Este proyecto tiene varios repositorios git:"]
    for repo in repos:
        where = repo.path if repo.path not in ("", ".") else f"{cwd} (la carpeta de trabajo)"
        detail = []
        if repo.branch:
            detail.append(f"rama de trabajo {repo.branch}")
        if repo.base:
            detail.append(f"base {repo.base}")
        suffix = f" · {', '.join(detail)}" if detail else ""
        lines.append(f"- {repo.name}: {where}{suffix}")
    return "\n".join(lines)


# $VARIABLES the agent's instructions may use (shown in the agent editor, design 03c).
VARIABLES = ("$PROYECTO", "$ETAPA", "$TAREA", "$MEMORIA", "$WORKSPACE")


def substitute(text: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        text = text.replace(name, value)
    return text


def task_section(task: TaskContext) -> str:
    lines = [f"# Tarea {task.code}: {task.title}"]
    if task.stage_name:
        lines.append(f"Etapa {task.stage_index} de {task.stage_count}: {task.stage_name}")
    if task.branch:
        # Not "commit in it": an agent without git permission would block on the CLI's prompt.
        # Whatever is left uncommitted is committed to the branch when the task ends.
        lines.append(
            f"Rama de trabajo: {task.branch} (al terminar, Agentic OS guarda en ella lo que "
            "quede sin commitear)"
        )
    if task.description.strip():
        lines += ["", task.description.strip()]
    if task.rejection:
        lines += ["", "## Vuelve a ti porque se rechazó", task.rejection]
    if task.history:
        lines += ["", "## Historial de la tarea", *task.history]
    return "\n".join(lines)


def build_instructions(
    agent: Agent | None,
    project: Project | None,
    cwd: str,
    memory: str = "",
    task: TaskContext | None = None,
    subagent: tuple[str, str] | None = None,
    repos: Sequence[RepoLine] = (),
    git_authorized: bool = False,
) -> str:
    """`memory` is the rendered project memory (services.memory.render_memory); `task`, the
    task and stage of a run launched by the scheduler (None for a manual run); `repos`, the
    project's repositories as this run sees them."""
    name = project.name if project is not None else "(proyecto)"
    memory = memory.strip() or "(vacía)"
    values = {
        "$PROYECTO": name,
        "$ETAPA": (task.stage_name or "") if task else "",
        "$TAREA": f"{task.code} · {task.title}" if task else "",
        "$MEMORIA": memory,
        "$WORKSPACE": cwd,
    }
    parts: list[str] = []
    if agent is not None:
        title = f"{agent.name} · {agent.role}" if agent.role else agent.name
        parts.append(f"# Tu rol: {title}")
        if agent.instructions.strip():
            parts.append(substitute(agent.instructions.strip(), values))
    parts.append(f"# Proyecto: {name}\nCarpeta de trabajo: {cwd}")
    section = repos_section(repos, cwd)
    if section:
        parts.append(section)
    if git_authorized:
        parts.append(GIT_RULES)
    parts.append(f"## Memoria del proyecto\n{memory}")
    if task is not None:
        parts.append(task_section(task))
    if subagent is not None:
        parent, prompt = subagent
        parts.append(
            f"# Eres un subagente de {parent}\n"
            f"{parent} te ha lanzado para una parte concreta de su trabajo. Haz solo esto:\n\n"
            f"{prompt.strip()}\n\n"
            f"Trabajas en la misma carpeta que {parent}: no toques lo que no te pide. Cuando "
            f"termines, llama a complete_task con el resultado; le llegará a {parent}."
        )
    parts.append(AGENTIC_OS_RULES)
    if task is not None and task.can_reject and subagent is None:
        parts.append(VERDICT_RULES)
    return "\n\n".join(parts).strip() + "\n"


def build_context(instructions: str, prompt: str | None) -> str:
    """What `get_context` returns: the instructions plus the task itself. A scheduled run's
    instructions already carry its task (prompt None)."""
    if prompt is None:
        return instructions
    return f"{instructions}\n# Tarea\n{prompt.strip()}\n"
