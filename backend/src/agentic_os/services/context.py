"""Instructions a run starts with: the agent's role, the project memory and how to work with
Agentic OS. Claude Code gets them as an appended system prompt, agy as plugin rules, and any
agent can read them again with the `get_context` MCP tool."""

from __future__ import annotations

from agentic_os.models import Agent, Project

# The most recent part of the memory is kept: it is appended to over time.
MEMORY_LIMIT = 12_000

AGENTIC_OS_RULES = """\
# Cómo trabajar con Agentic OS
Trabajas dentro de Agentic OS, que coordina a varios agentes. Tienes el servidor MCP `agentic-os`:
- `report_status`: cuenta brevemente en qué estás cada vez que empieces algo relevante.
- `write_project_memory`: si descubres algo útil para futuras tareas en este proyecto \
(convenciones, decisiones, trampas), guárdalo en una nota breve.
- `complete_task`: cuando hayas terminado, llámala con un resumen de lo hecho y de lo que \
queda pendiente. Después no sigas trabajando: Agentic OS cerrará la sesión.
- `get_context`: vuelve a leer estas instrucciones, la tarea y la memoria del proyecto.
"""


def project_memory(memory: str, limit: int = MEMORY_LIMIT) -> str:
    memory = memory.strip()
    if not memory:
        return "(vacía)"
    if len(memory) <= limit:
        return memory
    return "[…] (se muestra lo más reciente)\n" + memory[-limit:]


def build_instructions(agent: Agent | None, project: Project | None, cwd: str) -> str:
    parts: list[str] = []
    if agent is not None:
        title = f"{agent.name} · {agent.role}" if agent.role else agent.name
        parts.append(f"# Tu rol: {title}")
        if agent.instructions.strip():
            parts.append(agent.instructions.strip())
    name = project.name if project is not None else "(proyecto)"
    parts.append(f"# Proyecto: {name}\nCarpeta de trabajo: {cwd}")
    memory = project.memory if project is not None else ""
    parts.append(f"## Memoria del proyecto\n{project_memory(memory)}")
    parts.append(AGENTIC_OS_RULES)
    return "\n\n".join(parts).strip() + "\n"


def build_context(instructions: str, prompt: str) -> str:
    """What `get_context` returns: the instructions plus the task itself."""
    return f"{instructions}\n# Tarea\n{prompt.strip()}\n"
