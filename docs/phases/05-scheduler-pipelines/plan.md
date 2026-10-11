# Fase 05: Scheduler y pipelines · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado

## Diseño

### Visión general
```
UI ──REST──► /tasks, /agents/{id}/queue, /projects/{id}/pipeline, /projects/{id}/memory, /scheduler
                 │ (cada cambio)                                     
                 ▼                                                   
            Scheduler.poke() ──► hilo único del scheduler: tick()
                                   ├─ por agente con hueco: recorre su cola en orden
                                   ├─ salta las tareas con la carpeta directa ocupada
                                   ├─ prepara el workspace (carpeta o worktree)
                                   └─ RunManager.launch(..., task=…)  → Run(task_id, stage_id)
RunSession termina ──► RunManager.on_end ──► Scheduler.run_ended(run_id) ──► avanza / rechaza /
                                                                            revisión / «Esperando humano»
```
- **Un único hilo de scheduler** dirigido por eventos: `poke()` activa un `threading.Event`; `tick()` y `run_ended()` se ejecutan siempre en ese hilo, uno detrás de otro. Así nunca hay dos decisiones a la vez sobre la misma cola, y no hace falta bloquear filas en SQLite. Además, un tick de respaldo cada 5 s.
- Las ejecuciones manuales de la fase 03 no pasan por el scheduler y no cuentan para la concurrencia del agente.

### Modelo de datos (migración `0004`)
| Tabla | Campos principales |
|---|---|
| `tasks` | `number` (secuencia por workspace → `T-142`), `project_id`, `title`, `description`, `priority` (`high`/`normal`/`low`), `status`, `stage_id` (nulo sin pipeline), `agent_id` (agente de la etapa actual; el asignado sin pipeline), `queue_position`, `rejections`, `waiting_reason` (código) + `waiting_detail`, `worktree_path`, `branch`, `queued_at`, `started_at`, `finished_at` |
| `task_events` | Historial de la tarea: `kind` (`created`, `queued`, `stage_started`, `stage_completed`, `rejected`, `review_approved`, `review_rejected`, `waiting_human`, `retried`, `completed_manually`, `cancelled`, `done`), `stage_name`, `agent_name`, `run_id`, `summary`/`reason`, `at` |
| `pipelines` | `project_id` (único), `name`, `max_rejections` (3) |
| `stages` | `pipeline_id`, `position`, `name`, `agent_id`, `requires_review`, `reject_to_stage_id` (nulo = no puede rechazar) |
| `memory_notes` | `project_id`, `author_kind` (`agent`/`user`), `author_name`, `agent_id`, `text`, fechas |
| `runs` | + `task_id`, `stage_id`, `verdict` (`approved`/`rejected`) |
| `projects` | + `base_branch`; − `memory` (pasa a `memory_notes`) |
| `app_state` | clave-valor: `scheduler_paused` |

La migración parte la memoria actual en notas:
- los bloques `### <fecha> · <agente>` que escribió `write_project_memory` se convierten en notas de ese agente;
- el resto del texto se convierte en una nota de «Tú».

Estados de tarea: `backlog`, `queued`, `running`, `waiting_human`, `review`, `done`, `cancelled`. Con un `CheckConstraint`, como en las demás tablas.

### Colas (ADR 0009)
- **Orden de la cola** de un agente: tareas `queued` cuyo `agent_id` es el suyo, por (`priority`, `queue_position`).
- **Posición al encolar**:
  - **al final** de su prioridad: una tarea nueva y el paso a la siguiente etapa;
  - **al principio**: un rechazo, un reintento y un rechazo en revisión. Una tarea devuelta no espera otra vez toda la cola.
- **Reordenar**: `PUT /agents/{id}/queue` con la lista de ids, que reescribe las posiciones. El *drag & drop* solo mueve dentro de la cola del agente; si se cambia de prioridad, la tarea va al final de la nueva.
- **Elegir la siguiente** (`tick`), para cada agente activo con `running < max_concurrency`:
  - recorre su cola en orden y arranca la primera tarea que pueda arrancar;
  - en un proyecto de **carpeta directa**, una tarea no puede arrancar si ya hay otra `running` en ese proyecto: se salta, y la API la marca como `blocked: "folder_busy"`, calculado al leerla, no guardado. Es la única causa para saltarse el orden (decidido en la spec);
  - si el lanzamiento falla con un error que se puede reintentar (p. ej. `agy_folder_busy` por una ejecución manual), la tarea sigue en cola y se reintenta en el siguiente tick, con un evento. Un error definitivo (CLI no instalado, carpeta inexistente) la deja en «Esperando humano».
- **Pausa global**: `app_state.scheduler_paused`. Con la pausa, `tick` no arranca nada, pero `run_ended` sigue procesando los finales.

### Ciclo de vida de una tarea
`run_ended(run)` (en el hilo del scheduler), según cómo terminó la ejecución de la tarea:

| Fin de la ejecución | Efecto |
|---|---|
| `completed` y `verdict = approved` | Si la etapa «requiere revisión» → `review`. Si no → siguiente etapa (`queued`, al final de la cola de su agente), o `done` si era la última |
| `completed` y `verdict = rejected` | `rejections += 1`. Si supera `max_rejections` → `waiting_human` (`max_rejections`). Si no → etapa `reject_to`, `queued`, al principio de la cola, con el motivo en `task_events` |
| `exited`, `failed`, `stopped`, `interrupted` | `waiting_human` con el motivo (`run_exited`, `run_failed`, `run_stopped`, `interrupted`) |

Acciones del usuario (`POST /tasks/{id}/…`):
- `enqueue`: `backlog` → `queued`.
- `retry`: `waiting_human` → `queued`, misma etapa, al principio de la cola.
- `complete`: con un resumen. Si hay una ejecución activa, se marca la tarea como «cierre manual» y se para la ejecución; su fin cuenta como `completed` + `approved` con ese resumen. Sirve en `running` (el modelo no llamó a `complete_task`) y en `waiting_human`.
- `review`:
  - `{approve}` → siguiente etapa;
  - `{reject, reason, target_stage_id}` → la etapa elegida (`reject_to` o la misma), al principio de la cola. No cuenta para `max_rejections`, porque el rechazo es del usuario.
- `cancel`: para la ejecución activa y pasa a `cancelled`, con la limpieza del worktree.
- `PATCH`: título, descripción y prioridad; el agente, solo en tareas sin pipeline y que no estén `running`.

**Recuperación al arrancar**: después de `RunManager.recover()`, las tareas `running` sin ejecución viva pasan a `waiting_human` (`interrupted`). Nada se relanza solo.

**Borrados**:
- un agente o un proyecto con tareas `running` no se puede borrar (409);
- al borrar un proyecto se borran sus tareas;
- una etapa con tareas activas no se puede quitar del pipeline (409).

### Contexto y MCP
- `build_instructions` recibe además la tarea y la etapa, y añade:
  - `# Tarea T-142: <título>`, la etapa y su posición («Etapa 2 de 3: Desarrollo»);
  - `## Historial`: resúmenes de las etapas anteriores y el último motivo de rechazo, si lo hay (límite de tamaño, lo más reciente);
  - la carpeta de trabajo (el worktree, si lo hay) y la rama;
  - las reglas de `complete_task`: en una etapa que puede rechazar, explican el veredicto.
- **Variables** en las instrucciones del agente: `$PROYECTO`, `$ETAPA`, `$TAREA`, `$MEMORIA` y `$WORKSPACE` se sustituyen al construirlas. En una ejecución manual, `$ETAPA` y `$TAREA` quedan vacías.
- **Prompt** de una ejecución de tarea: `T-142 · <título>` + descripción. Para agy se mantiene la regla de la fase 04: la primera línea va como prompt y lo completo, a las reglas del plugin.
- **Memoria**: las notas, de la más antigua a la más reciente, con autor y fecha, y el mismo recorte por tamaño (`MEMORY_LIMIT`).
- **`complete_task(summary, verdict="approved")`**:
  - `verdict` acepta `approved` o `rejected` (descripción en castellano);
  - `rejected` en una etapa sin `reject_to`, o en una ejecución sin tarea, devuelve un error al modelo y **no** marca la ejecución como completada;
  - el veredicto se guarda en `runs.verdict`.
- **`write_project_memory(note)`** inserta una `memory_notes` del agente. Una fila por nota: desaparece el problema de concatenar en SQL.

### Workspaces (ADR 0009)
- **Carpeta directa**: `cwd = project.path`. Como mucho una tarea `running` por proyecto (regla del `tick`).
- **Worktree por tarea** (`services/worktrees.py`):
  - **Requisitos**: el proyecto tiene git y una `base_branch` que existe. Al elegir el modo en Ajustes, `base_branch` toma por defecto la rama actual. Si no hay git, no se puede elegir el modo.
  - **Creación**, la primera vez que la tarea arranca: `git worktree add -b agentic/T-142 <raíz>\T-142 <base_branch>`, con `<raíz> = <carpeta del proyecto>.wt` (como en el diseño: `D:\proyectos\app-reservas.wt\T-142`). Si la rama ya existe (p. ej. un reintento tras un fallo), se reutiliza.
  - **Lo reutilizan** todas las etapas y los reintentos de la tarea.
  - **Al terminar o cancelar**, con el CLI ya cerrado:
    1. si hay cambios sin commitear, Agentic OS los commitea en la rama (`chore(agentic): uncommitted work of T-142`), para no perder el trabajo;
    2. `git worktree remove` + `prune`, con reintentos si Windows bloquea archivos; si sigue fallando, se registra un evento y la tarea muestra un aviso, pero queda `done`/`cancelled` igualmente;
    3. la rama se conserva.
  - **Confianza** (`services/trust.py`): al borrar el worktree se quita su entrada de `projects` en `~/.claude.json` (o en `CLAUDE_CONFIG_DIR`) y de `trustedWorkspaces` en la configuración de agy. Es una lectura-modificación-escritura que solo toca esa clave, comprueba que el JSON se lee y escribe con reemplazo atómico; si falla, solo se registra.
  - **Cambio respecto a la spec**: el plugin de agy dentro del worktree **sigue** excluido con `.git/info/exclude` (el del repo común, que ya resuelve la fase 04). Si no, un agente que haga `git add -A` en su worktree commitearía el plugin con su token.

### API
| Ruta | Uso |
|---|---|
| `GET/POST /tasks`, `GET/PATCH /tasks/{id}` | Filtros: `project_id`, `agent_id`, `status`. La respuesta incluye `code` (`T-142`), el nombre de la etapa, el agente, `blocked` y la ejecución activa |
| `POST /tasks/{id}/enqueue · retry · complete · review · cancel` | Acciones |
| `GET /tasks/{id}/events` | Historial |
| `GET/PUT /agents/{id}/queue` | Cola ordenada / reordenar |
| `GET/PUT /projects/{id}/pipeline`, `DELETE` | Pipeline completo (las etapas conservan su id al editarlas). `PUT` con `template: "web"` crea la plantilla |
| `GET/POST /projects/{id}/memory`, `PATCH/DELETE /projects/{id}/memory/{note_id}` | Notas |
| `GET /scheduler`, `POST /scheduler/pause · resume` | Pausa global y contadores |
| `RunOut` | + `task_id`, `task_code`, `stage_name`, `verdict` |
| `ProjectOut` | + `base_branch`, KPIs (`open_tasks`, `running_tasks`, `waiting_tasks`); − `memory` |
| `AgentOut` | + `queued_count`, `running_count` |

**UI en vivo**: igual que en las fases 03 y 04, con *polling* de TanStack Query (2–3 s) mientras haya tareas activas, y el WebSocket de la ejecución para la terminal y los eventos. Un canal global de eventos queda para más adelante.

### UI
- **Tablero** (`BoardPage`), con `@dnd-kit/core` + `@dnd-kit/sortable` (dependencias nuevas):
  - toolbar con las vistas, los chips de proyecto, los avatares de agente y el interruptor **Pausar / Reanudar scheduler**;
  - **Por estado**: columnas Backlog, En cola, En ejecución, Esperando humano, En revisión y Hecho (las canceladas se ocultan);
  - **Por etapa**: una columna por nombre de etapa de los pipelines visibles, más «Sin pipeline» y Hecho;
  - **Colas por agente**: una fila por agente con «Ahora» + «#1, #2…», y *drag & drop* horizontal con el toast del diseño.
  - Componentes: `TaskCard` y `QueueCard` (con el aviso «Carpeta ocupada»).
- **Detalle de tarea** (`/tareas/:taskId`, `TaskPage`), según `09a`:
  - cabecera con las acciones según el estado: Revisar (Aprobar / Rechazar), Reintentar, Dar por terminada, Abrir worktree y Cancelar;
  - izquierda: stepper de etapas, descripción, historial (`task_events`) y las ejecuciones de la tarea;
  - centro: la terminal de la ejecución activa o de la última;
  - derecha: los eventos de esa ejecución.
  - La terminal y los eventos se extraen de `RunPage` a componentes compartidos.
- **Diálogo «Nueva tarea»**:
  - campos: proyecto, título, descripción, prioridad, y el agente si el proyecto no tiene pipeline;
  - «Encolar ahora» (por defecto) o «Dejar en backlog»;
  - se abre desde el tablero, desde la pestaña Tareas y desde la paleta de comandos, si ya existe la acción.
- **Proyecto**:
  - **Tareas**: tabla con ID, Tarea, Etapa, Estado, Agente, Prioridad y Coste («—»);
  - **Pipeline**: editor de `06b`, con flechas ←/→, ×, selector de agente, «Requiere revisión», «Puede rechazar → etapa», máximo de rechazos, «Añadir etapa» y «Usar plantilla Desarrollo web» si no hay pipeline. Se guarda con un botón y avisa de los cambios sin guardar, como en el editor de agentes;
  - **Memoria**: notas de `06c`;
  - **Ajustes**: rama base y validación del modo worktree;
  - **Resumen**: KPIs reales (coste «—») y «Ahora mismo».
- **Agentes**: columna «En cola».
- **Ejecuciones**: un chip con la tarea en la lista y en la página de ejecución.
- **i18n**: claves nuevas en `es` y `en`.

### CLI falso
El `fake_cli.py` lee directivas en la tarea para simular cada caso sin modelo:
- `[fake:reject <motivo>]`: `complete_task` con `rejected`, solo la primera vez;
- `[fake:no-complete]`: termina el turno sin `complete_task`;
- `[fake:exit 1]`: sale con error;
- `[fake:sleep N]`: tarda N segundos.

Además apunta en un archivo de traza qué contexto recibió, para comprobar que no se mezclan proyectos.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0004_tasks_pipelines.py` | nuevo |
| `backend/src/agentic_os/models/task.py`, `pipeline.py`, `memory.py`, `app_state.py` | nuevos |
| `backend/src/agentic_os/models/run.py`, `project.py`, `__init__.py` | modificados |
| `backend/src/agentic_os/schemas/task.py`, `pipeline.py`, `memory.py` | nuevos |
| `backend/src/agentic_os/schemas/run.py`, `project.py`, `agent.py` | modificados |
| `backend/src/agentic_os/services/scheduler.py` | nuevo: hilo, `tick`, `run_ended`, recuperación |
| `backend/src/agentic_os/services/tasks.py` | nuevo: transiciones y acciones (sin hilos, testeable) |
| `backend/src/agentic_os/services/pipelines.py` | nuevo: validación, plantilla «Desarrollo web» |
| `backend/src/agentic_os/services/worktrees.py`, `trust.py` | nuevos |
| `backend/src/agentic_os/services/git.py` | modificado: ramas, `worktree add/remove`, commit |
| `backend/src/agentic_os/services/context.py` | modificado: tarea, etapa, historial, variables, notas |
| `backend/src/agentic_os/services/mcp_server.py` | modificado: `verdict` |
| `backend/src/agentic_os/services/runs/manager.py` | modificado: `launch(..., task, stage, cwd)`, `on_end` → scheduler, notas, veredicto |
| `backend/src/agentic_os/api/tasks.py`, `pipelines.py`, `memory.py`, `scheduler.py` | nuevos |
| `backend/src/agentic_os/api/agents.py`, `projects.py`, `runs.py`, `__init__.py` | modificados |
| `backend/src/agentic_os/app.py` | modificado: crea y para el scheduler en el lifespan |
| `backend/tests/fake_cli.py` | modificado: directivas y traza |
| `backend/tests/test_tasks_api.py`, `test_scheduler.py`, `test_pipelines.py`, `test_worktrees.py`, `test_trust.py`, `test_memory_notes.py`, `test_migration_0004.py`, `test_scheduler_e2e.py` | nuevos |
| `frontend/package.json` | `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` |
| `frontend/src/api/tasks.ts`, `pipelines.ts`, `memory.ts`, `scheduler.ts`, `types.ts` | nuevos / modificado |
| `frontend/src/pages/BoardPage.tsx` + `pages/board/*` | reescrito |
| `frontend/src/pages/tasks/TaskPage.tsx`, `NewTaskDialog.tsx`, `TaskStatusBadge.tsx`, `TaskCard.tsx` | nuevos |
| `frontend/src/pages/projects/tabs/TasksTab.tsx`, `PipelineTab.tsx` | nuevos |
| `frontend/src/pages/projects/tabs/MemoryTab.tsx`, `SettingsTab.tsx`, `SummaryTab.tsx` | modificados |
| `frontend/src/pages/runs/RunPage.tsx` | modificado: terminal y eventos extraídos a componentes |
| `frontend/src/pages/agents/AgentsPage.tsx`, `routes.tsx`, `components/layout/crumbs.tsx`, `i18n/*` | modificados |
| `docs/adr/0009-scheduler-and-workspaces.md` | nuevo |
| `README.md`, `docs/roadmap.md` | modificados |

## Tareas (en orden)
Cada hito termina con `check` en verde y su propio commit (o varios).

**H1 · Modelo y memoria en notas**
1. [ ] Modelos y migración `0004`, con la conversión de la memoria; test de la migración con memoria real (bloques de agente + texto libre).
2. [ ] Notas de memoria: API, `write_project_memory` → nota, contexto con las notas, aviso de tamaño.
3. [ ] UI de la pestaña Memoria (`06c`) y retirada del campo `memory` del proyecto en la UI.

**H2 · Tareas y colas (sin pipeline)**

4. [ ] `services/tasks.py`: estados, transiciones, posiciones de cola; tests unitarios.
5. [ ] API de tareas y de colas; `queued_count` en agentes; borrados protegidos.
6. [ ] `Scheduler`: hilo, `poke`, `tick` con concurrencia y la regla de la carpeta ocupada, pausa, `run_ended`, recuperación al arrancar. `RunManager.launch` con tarea y `on_end`.
7. [ ] Contexto de tarea, variables y `complete_task(verdict)`.
8. [ ] CLI falso con directivas y traza; e2e: un agente con tareas de 2 proyectos (CA1), orden y reordenar (CA2), concurrencia en carpeta directa (CA3), fallos y acciones del usuario (CA7).

**H3 · Pipelines y revisión**

9. [ ] Modelo y API de pipeline, validación (`reject_to` anterior, etapa con tareas activas) y plantilla.
10. [ ] Avance entre etapas, rechazo con `max_rejections`, revisión humana; historial en el contexto.
11. [ ] e2e: Requisitos → Desarrollo → QA con rechazo y aprobación, máximo de rechazos (CA4); revisión humana (CA5).

**H4 · Worktrees**

12. [ ] `git.py` + `worktrees.py`: crear, reutilizar, commitear restos, borrar con reintentos; `base_branch` en Ajustes (API).
13. [ ] `trust.py`: limpieza de la confianza de Claude y agy; tests con archivos de configuración falsos (nunca los reales).
14. [ ] e2e con un repo git temporal: dos tareas en paralelo en el mismo proyecto y worktree compartido entre etapas; al terminar, rama conservada, carpeta borrada y plugin de agy fuera de git (CA6, CA3).

**H5 · UI**

15. [ ] Clientes de la API, `TaskStatusBadge`, `TaskCard`, diálogo Nueva tarea.
16. [ ] Pestañas Tareas, Pipeline (editor `06b`), Ajustes y Resumen del proyecto.
17. [ ] Detalle de tarea (`09a`), extrayendo la terminal y los eventos de `RunPage`.
18. [ ] Tablero: 3 vistas, filtros, *drag & drop* en Colas, pausa del scheduler; columna «En cola» en Agentes.

**H6 · Cierre**

19. [ ] Pruebas manuales con los CLIs reales:
    - Claude con tareas en 2 proyectos;
    - pipeline web con una etapa en agy y un rechazo real de QA;
    - proyecto en modo worktree.

    Con capturas y la comprobación de la configuración del usuario: solo deben cambiar las entradas de confianza esperadas, que se limpian.
20. [ ] ADR 0009, README, roadmap y `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_migration_0004.py`: conversión de la memoria; *upgrade* y *downgrade* | CA8 |
| `test_memory_notes.py`: CRUD, `write_project_memory` → nota con autor, notas en el contexto | CA8 |
| `test_tasks_api.py`: crear, encolar, editar, acciones por estado (códigos 409 si no tocan), borrados protegidos, reordenar | CA2, CA7 |
| `test_scheduler.py` (lanzador falso, sin PTY): orden por prioridad y posición, `max_concurrency`, carpeta ocupada → adelanta y marca `blocked`, posiciones al rechazar o reintentar, pausa, recuperación | CA2, CA3, CA7 |
| `test_pipelines.py`: validación del pipeline, plantilla, transiciones con revisión y rechazos, `max_rejections` | CA4, CA5 |
| `test_context.py` (ampliado): tarea, etapa, historial, motivo de rechazo, variables, reglas del veredicto | CA1, CA4 |
| `test_mcp_server.py` (ampliado): `verdict` válido e inválido, y sin tarea | CA4 |
| `test_scheduler_e2e.py` (backend real + CLI falso en ConPTY): 2 proyectos con un agente y contextos sin mezclar; pipeline con rechazo; revisión; ejecución sin `complete_task`; reinicio a mitad | CA1, CA4, CA5, CA7 |
| `test_worktrees.py` (repo git temporal): crear, reutilizar, commitear restos, borrar, rama conservada, ruta con espacios; e2e de dos tareas en paralelo | CA3, CA6 |
| `test_trust.py`: solo se quita la clave del worktree; JSON inválido o archivo ausente → no se toca nada | CA6 |
| Frontend (vitest): `BoardPage` (vistas, filtros, reordenar llama a la API), `TaskPage` (acciones según el estado), `PipelineTab` (reordenar, rechazo, guardar), `MemoryTab`, `NewTaskDialog` | CA2, CA9 |
| Pruebas manuales con Claude Code y agy | CA1, CA4, CA6 |

## Decisiones (ADR)
**[ADR 0009](../../adr/0009-scheduler-and-workspaces.md) · Scheduler, colas y workspaces** (se escribe en H2 y se completa en H4):
- un hilo único de scheduler dirigido por eventos, con un tick de respaldo;
- orden de la cola y posiciones (final al avanzar, principio al volver), y la única excepción: la carpeta ocupada;
- una ejecución interrumpida nunca se relanza sola;
- layout de los worktrees (`<proyecto>.wt\T-n`, rama `agentic/T-n`), commit de los restos, rama conservada;
- limpieza de la confianza;
- el plugin de agy sigue excluido de git también en los worktrees;
- *polling* en la UI en lugar de un canal global de eventos.
