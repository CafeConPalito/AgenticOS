# ADR 0020: Pipelines con ramas

- **Estado**: aceptado
- **Fecha**: 2026-10-18
- **Contexto de decisión**: fase 13 ([`spec.md`](../phases/13-pipelines-ramas/spec.md), [`plan.md`](../phases/13-pipelines-ramas/plan.md))

## Contexto
Un pipeline era una fila de etapas y una tarea estaba en un solo sitio: `Task.stage_id`, `Task.agent_id` y `Task.status` son únicos, y de ellos dependen las colas, el scheduler, el tablero, el contexto de los agentes, la Inbox, los worktrees y los diffs. La fase pide que tras una etapa el flujo se **bifurque** en varias ramas, que **un LLM decida** cuáles toma la tarea, que las elegidas avancen **a la vez** y se vuelvan a **unir**, y que un rechazo repita solo la rama que falló.

## Decisión

### El pipeline es un grafo estructurado (`services/pipeline_graph.py`)
- Etapas y **enlaces** (`StageLink`: origen, destino, nombre, condición en lenguaje natural o «siempre»). Una etapa con varios enlaces de salida es una **bifurcación** y cada enlace es una **rama**.
- **Estructurado**: las ramas de una bifurcación se cierran en **una sola etapa de unión** (la primera que todas alcanzan) o terminan todas en etapas finales; las bifurcaciones se anidan dentro de una rama; las ramas no se cruzan; no hay ciclos. Así la unión siempre sabe a qué ramas espera. Una rama no puede ser vacía (el enlace directo a la unión).
- La validación es **código puro sin base de datos**, con una copia en TypeScript (`validate.ts`) para el editor; los tests de las dos comparten casos. El servidor decide al guardar (`422 invalid_graph` con la lista de problemas por índice).
- Los **rechazos** no son enlaces. Una etapa tiene un destino por defecto (`reject_to_stage_id`) y puede tener más (`reject_extra_ids`): tras una unión, QA puede devolver la tarea a la rama que falló. Dentro de una rama solo se puede rechazar a etapas **de esa misma rama** (volver antes de la bifurcación obligaría a parar las ramas hermanas); tras la unión, a cualquier rama o a antes de la bifurcación. El agente nombra el destino con `reject_to` en `complete_task` (obligatorio si hay varios; el error le lista las opciones).
- Los pipelines lineales existentes se migran a una cadena de enlaces (`0015`) y no cambian de comportamiento.

### Cada rama tomada es una tarea hija (`services/lanes.py`)
- Una **vía** (*lane*) es una `Task` normal, hija de la que bifurcó (`lane_of_id`), con el **mismo número** (`T-142·backend`; único por `(workspace, number, lane_key)`). Reutiliza sin cambios las colas, el scheduler, las ejecuciones, reintentar, terminar a mano, la revisión humana, la Inbox, los worktrees y los diffs: todo eso ya funciona por tarea. Las vías anidan: una vía que llega a una bifurcación es madre de las suyas.
- La tarea madre pasa a `forked` (o `deciding` mientras se eligen las ramas): no tiene agente ni sitio en ninguna cola. La API **no expone esos estados**: muestra el de su vía más urgente (esperando humano › en revisión › en ejecución › en cola) y un campo `phase`. Cada vía cuenta una sola vez en los contadores.
- **Unión** (`try_join`): cuando todas las vías no canceladas de la bifurcación han llegado, la madre integra sus ramas de git, registra el evento `joined` con el resumen de cada una y sigue desde la etapa de unión (o termina, si las ramas no se unen). Si todas se cancelan espera (`lanes_cancelled`).
- **Rechazo desde la unión**: se **reabre** la vía de la rama que falló en la etapa de destino, con el motivo en su contexto, y la madre vuelve a esperar solo a esa. El contador de rechazos y su máximo son de la tarea raíz.
- **Carpeta directa**: las vías van **una detrás de otra**, en el orden de las ramas (hay una ejecución por proyecto); el editor lo avisa.

### Quién decide las ramas (`services/decider.py`)
- Una **llamada corta a un CLI sin herramientas**, no una ejecución de agente: `claude -p` con `--json-schema`, `--tools ""`, `--strict-mcp-config`, `--no-session-persistence` y `--max-budget-usd 0.05`, o `agy -p` (el JSON va dentro del texto). Modelo más barato del CLI, cuenta y modelo configurables por pipeline. Probado con los dos CLIs reales (spikes S1/S2 y prueba manual M1).
- Nunca en el hilo del scheduler: una tarea que llega a una bifurcación con ramas por decidir queda en `deciding`, y **el scheduler, en cada paso, pide la decisión** de las que no tienen una en curso (así también tras un reinicio o un reintento, sin código aparte); un trabajador hace la llamada y el scheduler aplica el resultado.
- **Ramas «siempre» y ramas fijadas al crear la tarea** (`preset_lanes`) no llaman al modelo. Un fallo se reintenta una vez; si vuelve a fallar (cuenta bloqueada, salida inválida, ninguna rama), la tarea espera con `choose_branch` y la persona elige. Una bifurcación puede pedir **confirmar** la decisión: la tarea queda en revisión con la propuesta y sus motivos.
- La llamada se guarda como una **`Run` de tipo `decision`** (sin agente, terminal ni cambios): su consumo y coste cuentan en el proyecto, la tarea, la cuenta y el límite diario sin tocar las estadísticas. Las listas de sesiones, los diffs y la retención de logs filtran `kind == agent`.
- Cada decisión queda en `BranchDecision` (quién, qué ramas, motivo de cada una) y en el historial de la tarea.

### Git de las vías (`services/lane_git.py`, `services/worktrees.py`)
- En modo worktree cada vía tiene **su carpeta y su rama por repo**: `<proyecto>.wt\T-142-backend` y `agentic/T-142-backend`, creada **desde la rama de su madre**. No puede ser `agentic/T-142/backend`: git no admite una rama que sea a la vez carpeta de otra. Antes de ramificar se commitea lo que la madre dejó suelto.
- Al **unir**, la rama de cada vía se mezcla en la de la madre con la misma maquinaria que integra una tarea en su base (fase 12: `merge-tree` + `commit-tree`, sin carpeta), un *merge commit* por vía; una vía sin commits se salta. Lo ya mezclado se queda: reintentar solo hace lo que falta.
- **Conflictos**: la unión no toca nada, la madre espera (`join_conflict`) y se resuelven en un worktree de trabajo sobre la rama de la madre (con la carpeta de la madre cerrada), o con una **tarea de resolución** para un agente (que trabaja en la rama de la madre, solo en los repos que chocan). Al terminar cualquiera de las dos, la unión continúa sola. Las tareas de resolución son ahora **tareas sueltas** (`create_task(standalone=True)`): antes, en un proyecto con pipeline, la tarea de la fase 12 entraba por la primera etapa e ignoraba el agente elegido.
- **Reabrir una vía** tras un rechazo: su rama avanza hasta la de la madre (todo lo suyo ya está dentro) y su `base_commit` se reinicia, así su diff es solo lo nuevo.
- Las ramas de las vías se **conservan**; la pestaña Git las asocia a su tarea (`TaskRepo`) y el borrado de ramas integradas de la fase 12 las recoge una vez integrada la madre.

## Consecuencias
- Una tarea que bifurca tiene varias filas `Task`: cualquier código nuevo que cuente o liste tareas debe decidir si quiere las vías (el listado general las oculta; el del agente, las colas y el tablero «Por etapa» las incluyen).
- La unión y la reapertura dependen de que la carpeta de la madre esté limpia o se pueda limpiar; el trabajo suelto se commitea en la rama de cada tarea.
- El decisor cuesta una llamada por bifurcación y tarea (céntimos con un modelo pequeño, algo más de 11 000 tokens de entrada con agy); «siempre» y las ramas fijadas la evitan.
- Fuera de esta fase: etapas que solo deciden (sin agente), bifurcar sin una etapa previa, condiciones como código, bucles que no sean de rechazo y grafos no estructurados.
