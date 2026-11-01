# ADR 0030: Salidas en el pipeline y modo de trabajo SDD por tarea

- **Estado**: propuesto (plan aprobado el 2026-11-01)
- **Fecha**: 2026-11-01
- **Contexto de decisión**: fase 24 ([spec](../phases/24-proyectos-pipelines-arquitecto/spec.md) · [plan](../phases/24-proyectos-pipelines-arquitecto/plan.md))
- **Amplía**: [ADR 0020](0020-branching-pipelines.md) (pipelines con ramas)

## Contexto
- **Tareas que terminan antes.** Hasta ahora una tarea solo termina en una etapa sin salida. Una tarea que solo pide los requisitos o la arquitectura pasa igualmente por los programadores, QA y el despliegue, y gasta en etapas sin trabajo.
- **SDD sí o no.** El usuario quiere que la plantilla «Desarrollo» use SDD (desarrollo guiado por especificaciones) cuando el trabajo lo merece o el proyecto ya lo usa, y que no lo use en los cambios pequeños.
- **Dos spikes con llamadas reales:**
  - S1: el decisor de ramas, con su modelo barato, acierta 12 de 12 si la tarea termina en una etapa y, si sigue, por qué ramas va (0,001 $ por llamada).
  - S2: el Analista de requisitos acierta 10 de 10 si usar SDD y en qué carpeta.

## Decisión
### Salidas «Terminar aquí»
1. **La salida es un atributo de la etapa**, `stages.exit_condition`, con la condición en lenguaje natural (`NULL` si no tiene salida). No es una etapa ni un enlace. El editor la dibuja como un nodo **Fin** unido a la etapa, y su sitio en el lienzo va en `exit_x` y `exit_y`.
2. **Reglas del grafo** (`pipeline_graph.py`, repetidas en `validate.ts`):
   - la condición no puede estar vacía (`exit_no_condition`);
   - una etapa final no la necesita (`exit_on_final`);
   - **solo fuera de las bifurcaciones abiertas** (`exit_in_branch`), es decir, en una etapa cuyo camino es `()`: antes de bifurcar, en la propia etapa que bifurca o después de que las ramas se junten. Una salida dentro de una rama terminaría toda la tarea con las ramas hermanas a medias.
3. **La decide el decisor de ramas**, en la misma llamada que las ramas:
   - Cuando una etapa con salida termina (después de su revisión humana, si la tiene), la tarea queda en `deciding`, igual que en una bifurcación.
   - El decisor contesta primero si la tarea termina aquí y, solo si sigue, por qué ramas va. Terminar es excluyente: no se toma ninguna rama.
   - La decisión queda en `BranchDecision`, con el id reservado `"exit"`. La salida respeta `confirm_decision` y, si el decisor falla, la persona elige «Terminar aquí» o seguir.
   - Las etapas sin salida no pagan esa llamada.
4. **Terminar en una salida es terminar la tarea**: la integración de ramas es la del proyecto, y en `tasks.exit_stage_id` queda dónde terminó. Si la etapa de la salida no tiene revisión humana y la última etapa del pipeline sí, la tarea pasa antes por la **revisión final**, para no saltársela.
5. La persona puede **seguir con el pipeline** una tarea que terminó en una salida: vuelve a la etapa siguiente, o a las ramas, como si el decisor hubiera dicho «sigue».

### Modo de trabajo SDD
6. **El modo es de la tarea**: `tasks.work_mode` (`sdd` | `direct`), con su motivo (`work_mode_reason`) y la carpeta de la spec (`spec_path`). Las ramas leen el de la tarea raíz.
7. **Lo marca la toma de requisitos** con la herramienta `set_work_mode` del MCP `agentic-os`. Sus instrucciones llevan las pautas de S2, en este orden:
   1. un cambio trivial va sin SDD, aunque el proyecto lo use;
   2. si el proyecto ya usa SDD, la tarea va con SDD en su formato;
   3. un trabajo grande va con SDD en el formato de la app (`specs/NNN-nombre/`);
   4. lo demás va sin SDD.
8. **El formato del proyecto se detecta** (`services/sdd.py`: spec-kit, Kiro, OpenSpec, specs por fase, `specs/*/spec.md`) y se le da a la primera etapa. **El modo llega a cada etapa en su contexto**, con lo que le toca hacer en ese modo.
9. La persona puede **cambiar el modo** mientras la tarea no ha bifurcado. La tarea vuelve entonces a la primera etapa para rehacer los requisitos.

## Consecuencias
- Los pipelines que ya existían no cambian: sin salidas, el motor se comporta igual.
- Una etapa con salida añade una llamada barata al decisor (≈0,001 $ y ≈5 s) cada vez que la tarea pasa por ella.
- Una tarea puede terminar sin haber pasado por todas las etapas. El Tablero y la tarea dicen dónde terminó y por qué.
- El modo SDD depende del criterio del agente en los casos dudosos. La revisión humana de la validación de requisitos lo corrige, y la persona lo puede cambiar.
- Fuera de esta decisión, y anotado para el futuro:
  - salidas que terminen solo una rama;
  - tareas que empiecen en una etapa intermedia;
  - cambiar el modo SDD después de bifurcar.
