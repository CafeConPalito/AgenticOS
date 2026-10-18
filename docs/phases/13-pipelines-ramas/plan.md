# Fase 13: Pipelines con ramas · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-18) · desarrollo sin empezar

## Lo que ya se sabe (revisado al escribir el plan)
- **Una tarea está en un solo sitio** (`services/tasks.py`, `services/scheduler.py`):
  - las colas, el scheduler (`_fill`, `blocked_reason`), `occupies_agent()`, el contexto (`task_context`), las acciones de la API (reintentar, terminar a mano, revisar, cancelar), la Inbox, el tablero y los diffs trabajan sobre `Task.stage_id`, `Task.agent_id` y `Task.status`;
  - hay 29 usos de `stage_id` fuera de las migraciones.
- **Precedente útil**: la tarea de resolución de conflictos de la fase 12 (`Task.resolves_task_id`). Es una `Task` normal que trabaja en la rama de otra (`worktrees._branch_of`). Las ramas paralelas pueden seguir el mismo patrón.
- **Avance lineal**: `next_stage` usa `Stage.position`. El rechazo usa `reject_to_stage_id`, y `pipelines._validate` exige que sea anterior por posición.
- **Worktrees** (fase 12): `prepare` crea `<proyecto>.wt\T-142` con un worktree por repo en la rama `agentic/T-142`; si la rama ya existe, la reutiliza. `release` commitea lo que queda suelto y borra el worktree. **git no admite a la vez `agentic/T-142` y `agentic/T-142/backend`**: un ref no puede ser también carpeta. Las ramas de las vías serán `agentic/T-142-backend`. El parser de `gitx/tasks.py` y `maintenance.py` reconoce hoy solo `agentic/T-n`.
- **Integración** (`services/integration.py`): ya tiene merge sin carpeta de trabajo (`merge-tree`), merge en un worktree temporal y la tarea de resolución con un agente. La unión reutiliza esas piezas.
- **Consumo**: todo se calcula a partir de filas de `Run` (paneles, límite diario, consumo por tarea). Si el decisor deja una `Run` con su consumo, cuenta en todo sin tocar las estadísticas.
- **Claude Code 2.1.302 en modo `-p`**:
  - `--json-schema` devuelve salida estructurada;
  - `--tools ""` deja la sesión sin herramientas;
  - también sirven `--max-budget-usd`, `--no-session-persistence`, `--strict-mcp-config` y `--model`;
  - con `--output-format json` el resultado trae `total_cost_usd` y `usage` (spike P11).
- **agy 1.4.2**:
  - en el spike de la fase 01, `agy -p` devolvió `response` vacío;
  - en la fase 12 se vio que en `-p` deniega todos los comandos, lo que da igual para un decisor sin herramientas.
  
  Falta comprobar si devuelve texto (bloque 0).
- **Frontend**: no hay librería de grafos. `@xyflow/react` 12.12 (React Flow, MIT) da lienzo, nodos, aristas, arrastre, zoom y teclado. Lo que queda es el diseño de los nodos y la colocación automática.

## Bloque 0 · Spikes (antes de programar)
| # | Pregunta | Cómo | Si falla |
|---|---|---|---|
| S1 | ¿Claude Code en `-p` con `--tools ""`, `--json-schema`, `--strict-mcp-config` y `--no-session-persistence` devuelve la decisión en JSON válido, con coste, sin tocar ficheros ni la configuración global, con la cuenta de un `CLAUDE_CONFIG_DIR` (fase 10)? ¿Cuánto tarda y cuánto cuesta con `haiku`? | `spikes/scenarios/decider.py` con 5 tareas de ejemplo y las ramas de la plantilla; evidencias en `evidencias/s1-claude-decider.md` | Pedir el JSON en el prompt y extraerlo del texto |
| S2 | ¿`agy -p` con `--output-format json` o `stream-json` devuelve el texto de la respuesta con algún modelo? ¿Trae el consumo? | Mismo script, `evidencias/s2-agy-decider.md` | El decisor solo admite Claude Code; el editor no ofrece agy y lo explica |
| S3 | Ramas de las vías: ¿se puede crear `agentic/T-142-backend` desde `agentic/T-142` con este ya activo en otro worktree, hacer merge de las dos vías en el worktree de la tarea y reabrir una vía (llevar su rama al nuevo extremo de la de la tarea) sin chocar con el worktree que la tiene activa? | `spikes/git_lanes_probe.py` con un repo temporal; `evidencias/s3-git-lanes.md` | Ajustar los pasos de `services/lanes.py` |

## Resultados de los spikes (bloque 0, 2026-10-18)
Scripts en `spikes/scenarios/decider.py` y `spikes/git_lanes_probe.py`; evidencias en `evidencias/`.

- **S1 · Claude Code 2.1.302** (`haiku`): con `--json-schema`, `--tools ""`, `--strict-mcp-config`, `--no-session-persistence` y `--max-budget-usd 0.05`, 5 de 5 decisiones correctas, todas con `structured_output` válido, en **3–4,5 s** y a **~0,0003–0,001 USD**. Sin ficheros en la carpeta y sin cambios en la configuración global. Una tarea sin ninguna rama aplicable devuelve todas con `take: false`: la app lo trata como fallo (spec §2).
- **S2 · agy 1.4.2** (`gemini-3.8-flash-low`, `-p --output-format json`): 5 de 5 correctas en **5–8 s**. Devuelve el texto en `result.response` (JSON dentro del texto, sin modo de esquema) y los tokens en `result.usage` (~11 800 de entrada por llamada, sin coste, como en la fase 07). El `response` vacío del spike de la fase 01 se debía a que aquel prompt pedía escribir un fichero y `-p` lo deniega. **agy sirve como decisor**; su salida se extrae del texto.
- **S3 · git**: `agentic/T-1/backend` no puede existir junto a `agentic/T-1` (confirmado) → ramas `agentic/T-1-backend`. Se pueden crear los worktrees de las vías desde la rama de la tarea mientras esta está activa en su carpeta. La unión desde el worktree de la tarea funciona: *fast-forward* de la primera vía y `--no-ff` de la segunda; un conflicto devuelve código 1 y `merge --abort` deja el worktree limpio. Reabrir una vía: `branch -f` al extremo de la tarea sin worktree, o `merge --ff-only` desde la tarea con el worktree vivo; ambos dejan la vía sin commits propios.

### Cambios al diseño por los spikes
- §3 `HeadlessDecider` ya tiene **dos adaptadores**: Claude Code (salida estructurada) y agy (JSON extraído del texto, con un reintento si no es válido). El editor ofrece los dos.
- Sin otros cambios: el diseño de §4 se confirma tal cual.

## Diseño ([ADR 0020](../../adr/0020-branching-pipelines.md), nuevo)

### 1. El grafo del pipeline
**Modelo** (`models/pipeline.py`)
- `Stage` gana:
  - `x` y `y`: posición en el lienzo;
  - `confirm_decision` (bool): solo cuenta si la etapa bifurca.
  
  `position` se queda como orden del editor y como desempate (orden de las vías en carpeta directa).
- **`StageLink`** (nuevo, tabla `stage_links`):
  - `pipeline_id`, `from_stage_id`, `to_stage_id`;
  - `name`, `condition` (texto), `always` (bool), `position`: orden de las salidas de una etapa.
  
  Unicidad: `(from_stage_id, to_stage_id)`. Una conexión **es una rama** cuando su etapa de origen tiene más de una salida.
- `Pipeline` gana:
  - `decider_cli`, `decider_account_id` y `decider_model`;
  - nulos: el primer CLI con sesión iniciada que admita decisor, su cuenta por defecto y su modelo más barato (lista fija en `services/decider.py`).
- El límite de 12 etapas sube a 30.

**Análisis del grafo** (`services/pipeline_graph.py`, nuevo, puro y sin BD)
- `Graph.from_rows(stages, links)` construye el grafo y `validate()` devuelve una lista de errores `{code, stage_id | link_id}`. Los códigos son:
  - `no_start` y `many_starts`;
  - `unreachable`;
  - `cycle`;
  - `unstructured`: una bifurcación sin unión única, o vías que se cruzan;
  - `branch_without_condition`;
  - `reject_not_backwards` y `reject_outside_path`.
- `join_of(fork)`: la etapa donde vuelven a encontrarse todas las vías de la bifurcación. Es su **post-dominador inmediato**; nulo si todas las vías acaban en finales.
- `lane_of(fork, link)`: las etapas de una vía, desde la salida hasta la unión, sin incluirla. **Estructurado** significa que las vías de una bifurcación son disjuntas y que ninguna conexión sale de una vía hacia otra o hacia fuera, salvo a la unión. Las bifurcaciones anidadas quedan dentro de una vía.
- `next_of(stage)`: la siguiente etapa, si no bifurca.
- **Destinos de rechazo válidos** de una etapa E:
  - una etapa anterior en el mismo segmento (antes de cualquier bifurcación que la separe de E);
  - si E está después de una unión J, una etapa de cualquiera de las vías que se unen en J, o cualquier etapa anterior a la bifurcación de J.
  
  Desde dentro de una vía solo se puede rechazar a etapas **de esa misma vía**: rechazar a una etapa anterior a la bifurcación obligaría a parar las vías hermanas, y queda fuera.
- **Migración de los pipelines lineales**: una conexión de cada etapa a la siguiente por `position`, y `x`/`y` de la colocación automática.

**Guardar** (`services/pipelines.py`)
- `PipelineWrite` pasa a llevar `stages` (con `x`, `y`, `confirm_decision`, `reject_to` y `reject_also`, todos los destinos como índice de la lista) y `links` (`source` y `target` como índice, `name`, `condition`, `always`). Sin `links`, el pipeline es una cadena (compatible con el editor anterior).
- **Varios destinos de rechazo** (hueco de la spec, resuelto en el bloque 1): para que QA pueda rechazar a Dev backend **o** a Dev frontend, una etapa tiene un destino por defecto (`reject_to_stage_id`) y destinos extra (`Stage.reject_extra_ids`, JSON). Al rechazar, el agente indica cuál con un parámetro nuevo de `complete_task` (obligatorio si hay varios, el error le lista las opciones); el usuario lo elige en la revisión, que ya admitía destino.
- Se valida con `pipeline_graph` (422 con la lista de errores) y además:
  - no se puede quitar una etapa con tareas o vías activas (como hoy);
  - **no se puede quitar una conexión por la que va o volverá una vía activa**: una vía en curso necesita su conexión hasta la unión. Error 409 `link_in_use` con la etapa.
- Plantilla nueva `PipelineTemplate.WEB_SPLIT`: Requisitos → (Backend: Dev backend | Frontend: Dev frontend) → QA. Las condiciones vienen escritas. QA rechaza a Dev backend; en la UI se puede cambiar a Dev frontend. Cada etapa toma el primer agente activo de la plantilla `developer`, `analyst` o `qa`, como hoy.

### 2. Vías: una tarea en varias ramas a la vez
**Decisión**: cada vía paralela es una **tarea hija** (`Task`), no una tabla nueva de «estados por rama». Así reutiliza sin cambios las colas, el scheduler, las ejecuciones, reintentar, terminar a mano, revisar, tomar el control, la Inbox, los worktrees y los diffs: todo ya funciona por tarea. La tarea madre espera mientras sus hijas avanzan.

**Modelo** (`models/task.py`)
- `Task` gana:
  - `lane_of_id`: la tarea madre, si es una vía;
  - `lane_link_id`: la conexión de su rama;
  - `lane_key`: *slug* del nombre de la rama, `""` en una tarea normal;
  - `fork_stage_id`: la bifurcación de la que salió;
  - `preset_lanes` (JSON `{fork_stage_id: [link_id…]}`): las ramas fijadas a mano al crear la tarea.
- Una vía comparte el **número** de su madre. La unicidad pasa de `(workspace_id, number)` a `(workspace_id, number, lane_key)`. `code` devuelve `T-142` o `T-142·backend`.
- `TaskStatus` gana dos estados internos de la madre:
  - `deciding`: el decisor está trabajando;
  - `forked`: espera a sus vías.
  
  No ocupan agente ni cola. La API **no los muestra tal cual**: `display_status` se deriva de las vías activas (esperando humano › en revisión › en ejecución › en cola) y, en `deciding`, es «en ejecución» con el rótulo «Decidiendo rama».
- `WaitingReason` gana:
  - `choose_branch`: «Hay que elegir la rama»;
  - `join_conflict`: «Conflictos al unir las ramas»;
  - `lanes_cancelled`: «Se cancelaron todas las ramas».
- `TaskEventKind` gana `decision`, `lane_started`, `lane_finished`, `lane_added`, `lane_cancelled` y `joined`.
- **`BranchDecision`** (nueva, tabla `branch_decisions`):
  - `task_id`, `fork_stage_id` y `run_id` (la `Run` del decisor; nula si decidió el usuario o «Siempre»);
  - `decided_by` (`model` · `user` · `always` · `preset`) y `status` (`proposed` · `final`);
  - `chosen` (JSON `[link_id]`) y `reasons` (JSON `{link_id: texto}`);
  - `error`.

**Motor** (`services/lanes.py`, nuevo; `services/tasks.py` deja de usar `next_stage`)
- **`advance(task)`**, tras aprobarse la etapa actual S:
  1. Si S tiene una sola salida, la tarea va a la siguiente etapa.
  2. Si la siguiente etapa es la **unión de la bifurcación de la que salió esta vía**, la vía **llega**: estado `done` con el evento `lane_finished`, se libera su worktree conservando la rama, y se llama a `try_join(madre)`.
  3. Si S bifurca, la tarea pasa a `deciding` y se pide la decisión (§3).
  4. Si S es un final dentro de una vía cuyas ramas no se unen, se trata como el paso 2 con unión nula.
  5. Si no, la tarea queda `done`, como hoy.
- **`fork(madre, ramas)`**, con la decisión ya tomada:
  - por cada rama elegida, crea la vía (o **reabre** la que ya existe, si la tarea vuelve a pasar por la bifurcación tras un rechazo) en la primera etapa de su rama;
  - la madre queda `forked`, con `stage_id` en la bifurcación;
  - título, descripción y prioridad se leen siempre de la madre;
  - **en carpeta directa** solo se encola la primera vía (por `position` de su conexión), y cada llegada encola la siguiente: así van en serie y nunca hay dos a la vez (se mantiene además `blocked_reason`);
  - en worktree, se encolan todas.
- **`try_join(madre)`**: si todas las vías no canceladas de la bifurcación están `done`:
  - se **integran** sus ramas en la de la madre (§4);
  - si va bien, la madre pasa a la unión con el evento `joined` y los resúmenes de todas las vías;
  - con unión nula, la madre queda `done` y sigue el cierre normal (liberar e integrar al aprobar, fase 12);
  - si se cancelaron todas, la madre espera con `lanes_cancelled`.
- **Rechazos** (`stage_rejected` y `review`): el destino ya está validado.
  - **Dentro de una vía**: la vía vuelve a la etapa de destino, como hoy.
  - **Desde después de una unión hacia una etapa de una vía**: se reabre esa vía en la etapa de destino, con el motivo en su contexto, y la madre vuelve a `forked` esperando solo a esa vía. Las demás vías siguen `done`.
  - **Hacia una etapa anterior a la bifurcación**: la madre vuelve a esa etapa. Al llegar otra vez a la bifurcación se decide de nuevo, y las vías que se elijan se reabren.
  - El contador de rechazos y el máximo **se llevan en la madre**: un rechazo en una vía también suma en ella.
- **Acciones**:
  - `add_lane(madre, link)` crea una vía nueva con la madre en `forked`;
  - `cancel_lane(vía)` cancela la vía (y para su ejecución, como cancelar una tarea) y llama a `try_join`;
  - cancelar la madre cancela sus vías;
  - reintentar, terminar a mano, revisar y tomar el control se hacen sobre la vía, con los endpoints de siempre.
- **Arranque** (`Scheduler.recover`): una madre en `deciding` pide la decisión de nuevo; las vías se recuperan como cualquier tarea.
- **Subtareas** (`create_subtask`) desde una vía: su `parent_task_id` es la vía y su proyecto el de la madre, como hoy.

### 3. El decisor
**`services/decider.py`** (nuevo)
- `Decider` (protocolo): `decide(request) -> DecisionResult`.
  - `request`: tarea (título y descripción), resúmenes de las etapas hechas, ramas (id, nombre y condición) y configuración del pipeline.
  - `DecisionResult`: `chosen`, `reasons`, `cost_usd`, `usage`, `model`, `duration` y `error`.
- **`HeadlessDecider`** (Claude Code):
  - lanza `claude -p <prompt> --model <m> --output-format json --json-schema <schema> --tools "" --strict-mcp-config --no-session-persistence --max-budget-usd 0.05`;
  - carpeta temporal vacía como `cwd`, el entorno de la cuenta (`accounts.env_for`), sin PTY y con un tiempo máximo de 60 s;
  - el *schema* exige `{"branches": [{"id", "take": bool, "reason"}]}` con todas las ramas;
  - el prompt (en español) explica que hay que elegir **una o varias** ramas según las condiciones y que no se puede elegir ninguna.
  
  Para agy, otro adaptador según S2.
- **`FakeDecider`** para los tests y el e2e: elige por palabras clave de la condición.
- **Ejecución**: nunca en el hilo del scheduler.
  1. `advance` deja la madre en `deciding` y avisa al servicio de decisiones.
  2. Un hilo (`decisions-worker`) hace la llamada y escribe el resultado.
  3. El scheduler, en su siguiente paso, llama a `apply_decision`, que bifurca o deja la tarea esperando. Así todos los cambios de estado de las tareas siguen siendo del scheduler.
- **Ramas «Siempre» y fijadas** (`preset_lanes`): se aplican sin llamar al LLM. Si quedan ramas por decidir, el LLM solo ve esas, y las «Siempre» se suman a su elección.
- **Fallos**: un reintento. Después, la madre queda `waiting_human` con `choose_branch` y la petición «Hay que elegir la rama» en la Inbox (fase 06), con notificación. Cuentan como fallo:
  - la cuenta bloqueada (límite diario, sin cuota o sin sesión), comprobada antes de llamar con `usage_limits.blocked_all`;
  - un error del CLI o una salida inválida;
  - ninguna rama elegida.
- **Confirmar la decisión** (`Stage.confirm_decision`): la decisión queda `proposed` y la madre `review`, con la petición «Confirmar la decisión» y las ramas y motivos propuestos. Aprobar o cambiar la selección la deja `final` y bifurca.
- **Consumo**: cada llamada deja una **`Run` de tipo decisión**:
  - `Run.kind` (nuevo: `agent` · `decision`), `agent_id` nulo, `agent_name` «Decisor» y `status` `completed`;
  - `cli`, `model`, `account_id`, tokens y `cost_usd` (agy: solo tokens, como en la fase 07);
  - `task_id` de la madre, `stage_id` de la bifurcación y `usage_status` `final`.
  
  Así cuenta en los paneles, en el límite diario y en el consumo de la tarea. Las listas de ejecuciones, el `RunManager`, los diffs y el registro git **filtran `kind == agent`**.
- **«Probar»**: `POST /projects/{id}/pipeline/decide-preview` con `{stage_key, title, description}` y el pipeline sin guardar. Hace una llamada síncrona (en un hilo del servidor) y devuelve ramas y motivos. Su consumo se registra como `Run` de decisión sin tarea.

### 4. Workspaces de las vías
- **Worktree**:
  - **La madre crea su worktree antes de bifurcar**, aunque la bifurcación sea la primera etapa con agente. Así su rama `agentic/T-142` existe en cada repo y es el origen de las vías.
  - Cada vía tiene su carpeta `<proyecto>.wt\T-142-backend` y su rama `agentic/T-142-backend` en cada repo, **creada desde el extremo de `agentic/T-142`** (`_branch_of` y `_add` aprenden de las vías, igual que de las tareas de resolución).
  - El `base_commit` de la vía es ese extremo: su diff es solo lo suyo.
- **Unión** (`lanes.integrate_lanes`), por repo y en el worktree de la madre, que está limpio porque la madre no tiene ejecución viva:
  - una vía sin commits nuevos se salta;
  - si la rama de la madre no se ha movido, *fast-forward*;
  - si no, `git merge --no-ff -m "merge(agentic): T-142·backend into T-142"`;
  - los ficheros sueltos de una vía se commitean al llegar (`release`).
- **Conflictos**:
  - el merge se aborta, la madre queda `waiting_human` con `join_conflict` y los repos y ficheros afectados;
  - el detalle ofrece **«Resolver en el editor»**: prepara el merge en el worktree de la madre y abre el editor de tres vías de la fase 12 sobre esa carpeta;
  - y **«Pasárselos a un agente»**: una tarea de resolución (`integration.resolution_task`) que trabaja en la rama de la madre e integra las vías;
  - al terminar cualquiera de las dos, `try_join` sigue.
- **Reabrir una vía** tras un rechazo: su rama se mueve al extremo de la de la madre (`git branch -f`, o `merge --ff-only` si su worktree sigue vivo). Así ve lo que ya integró la unión y lo que hizo QA.
- **Carpeta directa**: las vías trabajan en la carpeta del proyecto, una detrás de otra (§2). No hay ramas ni unión de git.
- **Nombres**: `gitx/tasks.py` y `maintenance.py` reconocen `agentic/T-n-<vía>` y lo asocian a la vía. La lista de ramas de la fase 12 muestra la vía bajo su tarea. Se borran las ramas de las vías ya integradas en la de la madre al cerrar la tarea (mismo criterio que `_drop_untouched_branches`).
- **Integración en las bases** (fase 12): solo existe para la madre, con su rama, que ya contiene las vías.

### 5. Contexto y MCP
- `TaskContext` gana:
  - `lane`: nombre de la rama, motivo de la decisión y vías hermanas con su etapa y estado;
  - `joined`: en la etapa de unión, nombre y resumen final de cada vía.
- `history` reúne los eventos de la madre y de sus vías, ordenados por `at`, con la vía en la etiqueta («Dev backend · Backend terminó: …»).
- `context.task_section` lo pinta. `get_context` devuelve lo mismo y `complete_task` no cambia.
- Variable nueva `$RAMA` en las instrucciones del agente.

### 6. API y eventos
- **Pipeline**:
  - `GET` y `PUT /projects/{id}/pipeline` con etapas y conexiones (`PipelineRead.links`, `StageRead.x`, `.y`, `.confirm_decision`, `.join_stage_id`);
  - `POST …/pipeline/validate` (sin guardar) y `POST …/pipeline/decide-preview`;
  - plantilla `web_split`.
- **Tareas**:
  - `TaskRead` gana `display_status`, `lane_of_id`, `lane_name`, `fork_stage_id` y `lanes` (resumen de las vías: id, código, rama, etapa, agente, estado y motivo de la decisión);
  - `GET /tasks` devuelve solo las madres y las tareas normales, salvo con `?lanes=include` (tablero «Por etapa» y colas);
  - `POST /tasks` acepta `preset_lanes`.
- **Decisión y vías**:
  - `GET /tasks/{id}/decisions`;
  - `POST /tasks/{id}/decision`, con `{fork_stage_id, chosen}`: elegir con `choose_branch` o confirmar y cambiar con `proposed`;
  - `POST /tasks/{id}/lanes` (añadir, con `{link_id}`) y `POST /tasks/{lane_id}/cancel` (el de siempre, sobre la vía);
  - `POST /tasks/{id}/join/resolve` (`{mode: editor | agent, agent_id?}`).
- **Peticiones**: `InboxKind` gana `choose_branch` y `confirm_decision`. Al resolverse, se cierran (como `review`).
- **Eventos en vivo**: el refresco sigue por sondeo (como en la fase 12). Las vistas de tarea y de tablero ya sondean y se añade la clave de las decisiones.

### 7. Frontend
- **Editor del grafo** (`pages/projects/tabs/pipeline/`, nuevo; sustituye a `PipelineTab.tsx`):
  - `PipelineCanvas.tsx` con `@xyflow/react`. Nodos `StageNode`: nombre, agente con su color, insignias de revisión, rechazo y «Confirmar». Aristas `BranchEdge`: nombre de la rama y «Siempre»; la de rechazo, discontinua.
  - Arrastrar desde el asa de un nodo crea una conexión. Menú contextual y botones para añadir y borrar etapas, y «Ordenar» (colocación automática por capas, `layout.ts`, sin dependencias).
  - `StagePanel.tsx`, `BranchPanel.tsx` y `PipelineSettings.tsx` (decisor: CLI, cuenta, modelo; máximo de rechazos).
  - `validate.ts` es una copia en TypeScript de las reglas de `pipeline_graph` para validar en vivo; el servidor es quien decide al guardar. Los errores se ven en el nodo o la arista y en una lista que lleva a cada uno.
  - `TryDecisionDialog.tsx`: «Probar».
  - Aviso en carpeta directa: «En este modo las ramas se hacen una detrás de otra».
  - **Teclado**: Tab recorre los nodos, Intro abre su panel y Supr borra con confirmación; se completa lo que React Flow ya trae.
- **Detalle de la tarea** (`TaskPage.tsx`):
  - `TaskPathGraph.tsx`: el mismo lienzo en solo lectura, con etapas hechas, en curso, no tomadas y pendientes, y el motivo de la decisión al pasar por la rama;
  - `LanesPanel.tsx`: una fila por vía con estado, agente y acciones (abrir, cancelar), «Añadir rama» y el bloque de conflictos al unir;
  - `DecisionBlock.tsx`: elegir o confirmar ramas, con sus motivos;
  - las ejecuciones y los diffs se pueden filtrar por vía.
- **Nueva tarea**: «Elegir las ramas a mano» (desplegable) con las bifurcaciones del pipeline y sus ramas.
- **Tablero**:
  - «Por etapa» pinta las vías en la columna de su etapa, con la rama en la tarjeta;
  - «Por estado» pinta la madre con `display_status` y un indicador de «2 ramas»;
  - en Colas, la vía aparece con su rama.
- **i18n**: claves nuevas en `frontend/src/i18n/` (`pipeline.graph.*`, `task.lanes.*`, `task.decision.*`, errores de validación y motivos de espera).

### 8. Migración `0015_branching_pipelines`
- Tablas `stage_links` y `branch_decisions`.
- Columnas nuevas en `stages`, `pipelines`, `tasks` y `runs` (`kind`, por defecto `agent`).
- Nuevos valores en los `CHECK` de `tasks.status` y `task_events.kind`.
- Unicidad de `tasks` con `lane_key` (en *batch* de SQLite).
- **Datos**: una conexión de cada etapa a la siguiente por `position`, y `x`/`y` en columna. Las tareas existentes no cambian.
- `downgrade` solo si el pipeline no tiene bifurcaciones ni hay vías.

## Archivos
| Archivo | Cambio |
|---|---|
| `spikes/scenarios/decider.py`, `spikes/git_lanes_probe.py` | nuevos (bloque 0) |
| `backend/src/agentic_os/models/pipeline.py` | `StageLink`, campos de `Stage` y `Pipeline` |
| `backend/src/agentic_os/models/task.py` | campos de vía, estados, motivos, eventos, `BranchDecision` |
| `backend/src/agentic_os/models/run.py`, `models/inbox.py` | `Run.kind`; tipos de petición nuevos |
| `backend/src/agentic_os/db/migrations/versions/0015_branching_pipelines.py` | nuevo |
| `backend/src/agentic_os/services/pipeline_graph.py` | nuevo: validación, uniones, vías, destinos de rechazo, colocación |
| `backend/src/agentic_os/services/pipelines.py`, `schemas/pipeline.py` | grafo, conexiones, plantilla `web_split`, `validate` |
| `backend/src/agentic_os/services/lanes.py` | nuevo: bifurcar, unir, reabrir, añadir y cancelar vías, integración de ramas |
| `backend/src/agentic_os/services/decider.py` | nuevo: protocolo, `HeadlessDecider`, `FakeDecider`, hilo de decisiones |
| `backend/src/agentic_os/services/tasks.py` | `advance`, rechazos, revisión y contexto con vías; `display_status` |
| `backend/src/agentic_os/services/scheduler.py` | aplicar decisiones, vías en serie en carpeta directa, recuperación |
| `backend/src/agentic_os/services/worktrees.py` | worktrees y ramas de las vías desde la rama de la madre |
| `backend/src/agentic_os/services/gitx/tasks.py`, `services/maintenance.py` | ramas `agentic/T-n-<vía>` |
| `backend/src/agentic_os/services/context.py`, `services/mcp_server.py` | rama, vías hermanas y resúmenes al unir; `$RAMA` |
| `backend/src/agentic_os/services/changes.py`, `services/runs/manager.py`, `services/usage/stats.py`, `api/runs.py` | filtrar las `Run` de decisión donde no aplican; diffs de la madre con sus vías |
| `backend/src/agentic_os/api/pipelines.py`, `api/tasks.py`, `schemas/task.py` | endpoints y campos nuevos |
| `backend/tests/test_pipeline_graph.py`, `test_lanes.py`, `test_decider.py`, `test_migration_0015.py`, `test_lanes_git.py`, `test_e2e_branching.py` | nuevos |
| `frontend/package.json` | `@xyflow/react` 12.12 |
| `frontend/src/pages/projects/tabs/pipeline/*` | nuevo editor (sustituye a `PipelineTab.tsx`) |
| `frontend/src/pages/tasks/TaskPage.tsx`, `TaskPathGraph.tsx`, `LanesPanel.tsx`, `DecisionBlock.tsx`, `NewTaskDialog.tsx` | vías, decisión, camino |
| `frontend/src/pages/BoardPage.tsx` | vías en «Por etapa» y en Colas; estado derivado |
| `frontend/src/api/pipelines.ts`, `frontend/src/api/tasks.ts` | tipos y llamadas |
| `frontend/src/i18n/*` | textos |
| `docs/adr/0020-branching-pipelines.md`, `README.md`, `docs/roadmap.md` | nuevo / actualizados |

## Tareas (en orden)
Cada bloque se cierra con sus tests en verde y un commit (o varios) en `phase/13-pipelines-ramas`.

0. [x] **Spikes S1–S3** con sus evidencias; ajustar el plan si algo cambia.
1. [x] **Grafo y migración**:
   - `StageLink` y los campos nuevos;
   - `pipeline_graph` con todas las reglas;
   - guardar y validar en `pipelines.py`;
   - migración `0015`.
   
   Los pipelines lineales siguen igual: los tests de la fase 05 en verde.
2. [x] **Motor de vías sin LLM**:
   - campos de vía en `Task` y estados internos;
   - `lanes.fork/try_join/add_lane/cancel_lane`;
   - `advance`, rechazos y revisión sobre el grafo;
   - ramas «Siempre» y `preset_lanes`;
   - carpeta directa en serie;
   - `display_status` y la API de tareas con vías.
   
   Todo con tareas en carpeta directa y el CLI falso.
3. [ ] **Decisor**:
   - `Run.kind` y los filtros;
   - `Decider`, `FakeDecider` y `HeadlessDecider` (y agy, según S2);
   - hilo de decisiones y `apply_decision`;
   - fallos y `choose_branch`, confirmar la decisión, peticiones de la Inbox;
   - `decide-preview`;
   - recuperación al arrancar.
4. [ ] **Worktrees de las vías**:
   - ramas y carpetas de las vías;
   - integración en la unión;
   - conflictos (editor y agente);
   - reabrir una vía;
   - nombres de rama en la pestaña Git;
   - diffs de la madre con sus vías.
5. [ ] **Contexto**: `TaskContext` con la vía y la unión, `get_context` y `$RAMA`.
6. [ ] **Editor del grafo**:
   - `@xyflow/react`, nodos, aristas y paneles;
   - validación en vivo y «Ordenar»;
   - «Probar»;
   - plantilla `web_split`;
   - aviso de carpeta directa.
7. [ ] **Seguimiento en la UI**:
   - camino de la tarea, panel de vías y bloque de decisión;
   - Nueva tarea con ramas a mano;
   - tablero y colas;
   - peticiones nuevas.
8. [ ] **e2e y cierre**:
   - `test_e2e_branching.py` (CA1, CA7);
   - prueba manual con el decisor real (Claude Code) y la plantilla;
   - ADR 0020, README;
   - `/code-review`;
   - `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_pipeline_graph.py`: inicio único, alcanzables, ciclos, bifurcaciones sin unión, vías que se cruzan, anidadas, uniones (post-dominador), destinos de rechazo válidos e inválidos, colocación | CA8 |
| `test_pipelines.py` (ampliado): guardar el grafo, errores 422, no quitar etapa o conexión con vías activas (409), plantilla `web_split` | CA8 |
| `test_migration_0015.py`: un pipeline lineal y sus tareas en curso pasan a conexiones y siguen avanzando igual; `downgrade` | CA9 |
| `test_lanes.py`: bifurcar en 1 y en 2 vías, la unión espera solo a las tomadas, añadir y cancelar vía, todas canceladas, final sin unión, rechazo dentro de una vía, desde la unión a una vía, a antes de la bifurcación (nueva decisión), máximo de rechazos en la madre, `preset_lanes` y «Siempre», `display_status` | CA1, CA4, CA7 |
| `test_scheduler.py` (ampliado): en carpeta directa las vías van en serie y nunca hay dos ejecuciones del proyecto; en worktree, en paralelo según `max_concurrency` | CA6 |
| `test_decider.py`: el prompt y el *schema*; salida válida, inválida, vacía, error del CLI y cuenta bloqueada → `choose_branch` tras un reintento; confirmar y cambiar; `Run` de decisión con coste y su efecto en el consumo y el límite diario; `decide-preview`; recuperación de `deciding` | CA2, CA3 |
| `test_lanes_git.py` (repos reales): ramas `agentic/T-n-<vía>` desde la rama de la madre, *fast-forward* y merge en la unión, dos repos, conflicto → `join_conflict` → resolver en el editor y con un agente, reabrir una vía, ramas de vía en la pestaña Git, diff de la madre | CA5 |
| `test_context.py` (ampliado): rama, motivo, vías hermanas y resúmenes al unir; `$RAMA` | CA1 |
| `test_e2e_branching.py`: plantilla `web_split` con el CLI falso y `FakeDecider`; tarea de API, de UI y de las dos en paralelo hasta QA; rechazo de QA a Dev backend | CA1, CA7 |
| Frontend: `pipeline-editor.test.tsx` (crear, conectar, validar, bloquear guardar, «Probar»), `validate.test.ts` (mismas reglas que el backend, con los mismos casos), `task-lanes.test.tsx` (camino, vías, elegir y confirmar rama, añadir y cancelar, conflictos), `board.test.tsx` (vías por etapa, estado derivado), `new-task.test.tsx` (ramas a mano) | CA8, CA10, CA3, CA4 |
| Prueba manual: plantilla con agentes reales y el decisor de Claude Code (`haiku`), tres tareas de ejemplo, capturas | CA1, CA2, CA10 |
| `check` (lint, tipos, tests de backend y de frontend) | CA11 |

## Decisiones (ADR)
- **ADR 0020 · Pipelines con ramas**:
  - grafo de etapas y conexiones, estructurado (cada bifurcación con una sola unión, calculada como post-dominador);
  - **vías como tareas hijas** que comparten el número de la madre, con estados internos de la madre (`deciding`, `forked`) y estado derivado en la API;
  - el decisor como llamada *headless* sin herramientas, cuyo consumo es una `Run` de tipo decisión;
  - ramas de git de las vías (`agentic/T-n-<vía>`) integradas en la de la madre en la unión;
  - en carpeta directa, vías en serie;
  - rechazos desde una vía, solo dentro de esa vía.
- **Concreción de la spec** (para aprobar con el plan): desde dentro de una vía solo se puede rechazar a etapas de esa vía, porque rechazar a una etapa anterior a la bifurcación obligaría a parar las vías hermanas. Desde después de una unión sí se puede rechazar a una vía o a antes de la bifurcación (en ese caso se vuelve a decidir).
- **Fuera de esta fase**, anotado para el futuro: etapas solo de decisión (sin agente) y bifurcar al principio del pipeline sin una etapa previa.
