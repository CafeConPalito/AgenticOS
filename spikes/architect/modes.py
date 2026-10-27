"""Mode-specific blocks of the Architect's instructions (they replace {MODE})."""

MODES = {
    "agent": """## Ahora
Diseñas **un agente nuevo**. Usa `agent_ref` "main".""",
    "improve_agent": """## Ahora
Mejoras el agente existente **{target}**. Su ficha actual ya está cargada (`get_sheet`, agent_ref "main").
Cambia solo lo que el usuario pida o lo que haga falta para eso, y di qué has cambiado y por qué. El
usuario verá los cambios campo a campo y decidirá cuáles aplica.""",
    "team": """## Ahora
Diseñas **un equipo completo con su pipeline** para un proyecto existente:
1. El equipo (`update_team`: uno nuevo o uno existente).
2. Sus agentes: **reutiliza** los que ya existan para un rol (`use_existing_agent`) y crea solo los que falten
   (`update_sheet` con un `agent_ref` corto por agente, p. ej. "redactor").
3. El pipeline del proyecto (`set_pipeline`): etapas con su agente, revisión humana donde haya que validar,
   `reject_to` para devolver trabajo a una etapa anterior y bifurcaciones solo si hay trabajos que van por
   caminos distintos (cada rama con una condición clara que un modelo pueda evaluar leyendo la tarea).
Antes de dar por cerrado el diseño, comprueba con `get_sheet` que no quedan problemas.""",
    "improve_pipeline": """## Ahora
Mejoras el pipeline del proyecto **{target}** (su pipeline actual está en `get_sheet` y en `list_projects`).
Cambia solo lo que el usuario pida, con `set_pipeline` (el pipeline completo, con las etapas que se quedan),
y di qué etapas y ramas añades, quitas o cambias.""",
}


def instructions(base: str, mode: str, target: str = "") -> str:
    return base.replace("{MODE}", MODES[mode].replace("{target}", target))
