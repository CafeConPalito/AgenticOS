# Fase 06: Subagentes y human-in-the-loop · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador

## Diseño

### Visión general
```
CLI ──MCP request_human──► Inbox (pending) ──► UI: Inbox + contador + notificación
CLI pantalla: diálogo de permiso ──► ScreenState.permission_dialog() ──► Inbox «Aprobación»
                                                  │
Usuario responde (Inbox / tarea) ──► API ──► RunSession.deliver(texto) / answer_dialog(sí|no)
                                                  │
                                         Tarea: Esperando humano ⇄ En ejecución
CLI ──MCP spawn_subagent──► RunManager.launch(hija, parent_run_id, cwd del padre)
         hija complete_task ──► resumen ──► RunSession.deliver() del padre
CLI hooks / PreToolUse ──► subagentes nativos (eventos) ──► árbol de la tarea
```

### Modelo (migración `0005`)
| Tabla | Cambio |
|---|---|
| `inbox_items` (nueva) | `kind` (`approval`, `question`, `blocker`, `review`, `stalled`, `delivery`), `status` (`pending`, `resolved`), `task_id`, `run_id`, `agent_id`/`agent_name`, `project_id`/`project_name`, `title`, `detail`, `command`, `options` (JSON), `response`, `resolution` (`approved`, `rejected`, `answered`, `answered_in_terminal`, `reviewed`, `dismissed`), `notified_at`, `created_at`, `resolved_at` |
| `runs` | + `parent_run_id` (subagente de Agentic OS) |
| `tasks` | + `parent_task_id` (subtarea) |
| `app_state` | + `notifications` (JSON con los interruptores por tipo y el sonido) |

Motivos nuevos de «Esperando humano»: `human_request` y `permission` (la columna no tiene `CHECK`, así que no requiere migración de datos).

### Escribir en la terminal de un agente (`RunSession.deliver`)
- Cola de mensajes por sesión. El *ticker* (cada 250 ms) escribe el siguiente cuando el CLI espera entrada:
  - fuera de turno (hooks);
  - sin diálogos en pantalla;
  - sin una persona con el control;
  - y en agy, con «? for shortcuts».
- Se escribe **una sola línea**: los saltos se convierten en « / », porque Enter enviaría en el primero (en agy, y también en Claude). Si el texto es muy largo, se recorta y se indica que el resto está en `get_context`.
- Se escribe el texto, se espera 0,4 s y Enter, igual que el prompt diferido. Si en 20 s no empieza un turno, se registra `waiting_for_human` (`message_not_started`).
- La usan la respuesta a `request_human`, el resumen de un subagente para su padre y las respuestas escritas desde la Inbox.

### `request_human`
- Herramienta `request_human(title, detail="", options=[])`:
  - crea un `inbox_item` `question` (con opciones) o `blocker`;
  - con tarea, la pone «Esperando humano» (`human_request`);
  - devuelve «Petición enviada. Termina tu turno; recibirás la respuesta como un mensaje».
- Responder (`POST /inbox/{id}/answer {text}`):
  - resuelve el elemento y guarda un `task_event` `human_answered`;
  - la tarea vuelve a «En ejecución»;
  - `deliver(«Respuesta de la persona a «<título>»: <texto>»)`. Si la ejecución ya no vive, la respuesta queda en el historial: el contexto de tarea del reintento incluye las preguntas y respuestas.
- Las reglas de `AGENTIC_OS_RULES` explican cuándo usar `request_human` y que hay que terminar el turno tras llamarla.

### Diálogos de permiso del CLI
- **Tarea 1 del plan**: capturar con los CLIs reales los textos de los diálogos y guardarlos como *fixtures*:
  - Claude: `Bash`, `Write`/`Edit` y `WebFetch` en «Preguntar» y «Restringido»;
  - agy: `run_command` y una herramienta MCP que no sea nuestra;
  - para cada uno, las opciones, la tecla que aprueba o rechaza y la pantalla tras responder.
- `ScreenState.permission_dialog()` devuelve `{tool, command, approve_keys, reject_keys}`, solo si el diálogo está al final de la pantalla (como en la fase 04). Las expresiones regulares viven en `screen.py`.
- En la sesión, cuando aparece un diálogo nuevo (con una firma por herramienta y comando), se llama a `on_permission(dialog)`:
  - el `RunManager` crea el `inbox_item` `approval`, con la tarea en «Esperando humano» (`permission`), y un evento de ejecución;
  - cuando el diálogo desaparece sin respuesta desde la Inbox, se llama a `on_permission_gone()`: el elemento se resuelve con `answered_in_terminal` y la tarea vuelve a «En ejecución».
- Aprobar o rechazar (`POST /inbox/{id}/approve · reject`) escribe las teclas del diálogo, solo si sigue en pantalla y nadie tiene el control. Si ya no está, se responde 409 y el elemento se marca como respondido en la terminal.
- Los diálogos de nuestras herramientas MCP en agy siguen aprobándose solos (fase 04). El consentimiento de «Autónomo» de Claude sigue siendo de la persona; pasa a la Inbox como `blocker` con «Abrir terminal».

### Subagentes de Agentic OS
- `spawn_subagent(prompt, agent="")`, con `agent` como nombre de un agente, o vacío para el mismo:
  - lo comprueba el `RunManager`: `can_spawn_subagents` del agente padre, máximo 3 hijas vivas, y agy no en una carpeta ocupada por otra ejecución de agy;
  - lanza `launch(..., parent_run=…, cwd=padre.cwd)` con la misma tarea y la misma etapa (`task_id` y `stage_id`), y el contexto de tarea más una sección «Eres un subagente de <padre>: haz solo esto: <prompt>»;
  - devuelve el id de la ejecución hija, o el error para el modelo.
- **El scheduler ignora el fin de las ejecuciones hijas** (`parent_run_id` no nulo): no mueven la tarea.
- Al terminar una hija, se hace `deliver()` en el padre: «Subagente <nombre> terminó: <resumen | estado>».
- Parar, cancelar o cerrar el padre para a las hijas vivas.
- La concurrencia del agente no cambia: solo cuenta tareas `running`.

### Subagentes nativos
- **Claude**: los hooks se amplían con `SubagentStart`, `SubagentStop` y `PreToolUse` (matcher `Agent`).
- **agy**: `PreToolUse` en `hooks.json`; solo interesa `invoke_subagent`, con `Role` y `Prompt`. Su fin se deduce del `PostToolUse` correspondiente.
- La tarea 1 captura las cargas reales (ids para emparejar inicio y fin).
- Se guardan como `RunEvent` `hook` con `name` `subagent_start` o `subagent_stop` y un `detail` JSON (`{"id", "description"}`).
- `GET /tasks/{id}/tree` construye el árbol:
  - ejecuciones de la tarea, con sus hijas y su estado;
  - nodos nativos a partir de los eventos (descripción, inicio y fin).

### Subtareas
- `create_subtask(title, description="", agent="")`:
  - requiere `can_create_tasks`;
  - `task_ops.create_task(..., parent_task_id=…)` en el proyecto de la tarea, con el agente indicado o la primera etapa del pipeline (`requeue`);
  - devuelve el código (`T-150`).
- `TaskRead` gana `parent_task_id`, `parent_code` y `subtasks: {done, total}`; `GET /tasks?parent_task_id=`.

### Revisiones, «Sin terminar» y entregas
- `task_ops` crea o resuelve los elementos en los puntos donde cambia el estado:
  - al entrar en `review` → `review`;
  - al pasar a `done` → `delivery`;
  - al salir de `review` por la API de tarea → resuelve el elemento pendiente.
- Resolver una `review` desde la Inbox llama a `task_ops.review`.
- **«Sin terminar»**: el *housekeeping* del scheduler (cada minuto) busca ejecuciones de tarea con actividad `idle` desde hace más de 10 minutos, sin `complete_task` y sin elemento pendiente, y crea uno. Se resuelve solo si la ejecución vuelve a trabajar o termina. Para eso, `runs` gana `idle_since`, que mantiene `_persist`.

### Notificaciones
- **Las lanza el frontend**: el backend es un *sidecar* sin ventana. Un `useInboxNotifier()` en `AppShell`:
  - consulta `GET /inbox/summary` cada 3 s (la Inbox necesita el contador igualmente);
  - por cada elemento pendiente con `notified_at = null` y su tipo activado en los ajustes, notifica y marca `POST /inbox/{id}/notified`. Así, con dos ventanas no se notifica dos veces.
- **Tauri**: `tauri-plugin-notification` (Rust y JS), permiso `notification:default` en la *capability*. Al pulsar la notificación se enfoca la ventana y se navega a `/inbox?item=<id>`.
- **Navegador**: la API `Notification` si hay permiso, que se pide desde Ajustes.
- **Ajustes** (`/ajustes`, sección «Notificaciones» de `12`): interruptores para Aprobaciones, Preguntas y bloqueos, Revisiones y rechazos entre etapas, Sin terminar, Tareas completadas, y Sonido. Endpoints `GET/PUT /settings/notifications`.

### API
| Ruta | Uso |
|---|---|
| `GET /inbox?status=pending\|resolved`, `GET /inbox/summary` | Lista y contador (`pending`, `latest` sin notificar) |
| `POST /inbox/{id}/answer {text}` · `approve` · `reject {reason?}` · `review {approve, reason?, target_stage_id?}` · `dismiss` · `notified` | Acciones |
| `GET /tasks/{id}/tree` | Árbol de ejecución |
| `GET /tasks?parent_task_id=` | Subtareas |
| `GET/PUT /settings/notifications` | Ajustes de notificaciones |
| `RunRead` | + `parent_run_id` |

### UI
- **Inbox** (`/inbox`, `10-inbox`):
  - segmentado Pendientes (n) · Resueltas (n);
  - `InboxItem` con avatar y distintivo del tipo, fila de metadatos, título, comando en bloque de terminal y contexto;
  - barra de acciones según el tipo, y «Abrir terminal», que abre el dock en esa ejecución;
  - en lo resuelto, el resultado en verde;
  - vacío: «Bandeja al día».
- **Barra lateral**: el contador de la Inbox con datos reales.
- **Detalle de tarea** (`09a`):
  - columna derecha con el «Árbol de ejecución» encima de los eventos; al pulsar un nodo con terminal, la terminal central cambia a esa ejecución;
  - «Subtareas n/m» en el panel izquierdo;
  - el aviso de «Esperando humano» con un enlace al elemento de la Inbox.
- **Ajustes**: la sección Notificaciones. El resto de la página sigue como «próximamente».
- **Agente → Ejecución**: los interruptores «Puede lanzar subagentes» y «Puede crear tareas» ya existen; se añade una línea de ayuda que explica su efecto.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0005_inbox_subagents.py` | nuevo |
| `backend/src/agentic_os/models/inbox.py`; `models/run.py`, `task.py`, `__init__.py` | nuevo / modificados |
| `backend/src/agentic_os/schemas/inbox.py`, `settings.py`; `schemas/task.py`, `run.py` | nuevos / modificados |
| `backend/src/agentic_os/services/inbox.py` | nuevo: crear, resolver, sincronizar con las tareas |
| `backend/src/agentic_os/services/runs/screen.py`, `session.py` | `permission_dialog`, `deliver`, `idle_since`, hijas |
| `backend/src/agentic_os/services/runs/manager.py` | `request_human`, `spawn_subagent`, `create_subtask`, permisos, entrega a los padres |
| `backend/src/agentic_os/services/mcp_server.py`, `context.py`, `hooks.py`, `adapters/*` | herramientas, reglas, hooks de subagentes |
| `backend/src/agentic_os/services/tasks.py`, `scheduler.py` | elementos de la Inbox en revisión y entrega, ignorar las hijas, «Sin terminar» |
| `backend/src/agentic_os/api/inbox.py`, `settings.py`; `api/tasks.py` | nuevos / árbol y subtareas |
| `backend/tests/fixtures/screens/*.txt`, `hooks/*.json` | textos y cargas reales capturados |
| `backend/tests/fake_cli.py` | directivas `PREGUNTA:`, `PERMISO:`, `SUBAGENTE:`, `SUBTAREA:`, `NATIVO:` |
| `backend/tests/test_inbox*.py`, `test_permissions.py`, `test_subagents.py`, `test_hitl_e2e.py` | nuevos |
| `desktop/src-tauri/Cargo.toml`, `src/lib.rs`, `capabilities/default.json`; `frontend/package.json` | plugin de notificaciones |
| `frontend/src/api/inbox.ts`, `settings.ts`; `pages/InboxPage.tsx` + `pages/inbox/*`; `pages/SettingsPage.tsx`; `hooks/use-inbox-notifier.ts`; `pages/tasks/*` | nuevos / reescritos |
| `docs/adr/0010-human-in-the-loop.md` | nuevo |

## Tareas (en orden)
**H0 · Captura con los CLIs reales**
1. [ ] Diálogos de permiso de Claude y agy (pantallas antes y después, teclas) y cargas de hooks de subagentes nativos (Claude `SubagentStart/Stop`, `PreToolUse Agent`; agy `PreToolUse invoke_subagent`). Se guardan como *fixtures* y se anotan en el ADR 0010.

**H1 · Inbox (backend)**

2. [ ] Migración `0005`, modelos, `services/inbox.py`, API de la Inbox y de ajustes de notificaciones.
3. [ ] Revisiones y entregas sincronizadas con `task_ops`; tests.

**H2 · `request_human` y `deliver`**

4. [ ] `RunSession.deliver` con su cola y sus condiciones; tests con el CLI falso (Claude y agy).
5. [ ] Herramienta `request_human`, respuesta desde la API, estados de la tarea, contexto con preguntas y respuestas; e2e.

**H3 · Permisos del CLI**

6. [ ] `permission_dialog()` con las *fixtures*, detección en la sesión, aprobar y rechazar, resolución por la terminal, estados de la tarea; directiva `PERMISO:` en el CLI falso; e2e.

**H4 · Subagentes y subtareas**

7. [ ] `spawn_subagent`: validaciones, lanzamiento de la hija, el scheduler ignora a las hijas, entrega del resumen al padre, parada en cascada; e2e.
8. [ ] Subagentes nativos: hooks de los adapters, eventos, `GET /tasks/{id}/tree`; tests con las cargas reales.
9. [ ] `create_subtask`, `parent_task_id`, subtareas en `TaskRead`; tests.

**H5 · «Sin terminar»**

10. [ ] `idle_since`, *housekeeping*, creación y resolución; tests.

**H6 · UI y notificaciones**

11. [ ] Clientes de la API, página Inbox (`10-inbox`), contador en la barra lateral.
12. [ ] Árbol de ejecución y subtareas en el detalle de tarea.
13. [ ] Notificaciones: plugin de Tauri, `useInboxNotifier`, sección de Ajustes.

**H7 · Cierre**

14. [ ] Pruebas manuales con los CLIs reales (CA1–CA5) y con la app de escritorio (CA8); ADR 0010, README, roadmap, `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_inbox.py`: crear y resolver cada tipo, contador, `notified`, revisiones y entregas sincronizadas en los dos sentidos, ajustes | CA7, CA8 |
| `test_screen.py` (ampliado): `permission_dialog` con las pantallas reales de Claude y agy; un diálogo ya respondido no cuenta | CA3 |
| `test_permissions.py` (backend real + CLI falso): diálogo → Aprobación → aprobar o rechazar → el CLI sigue; respondido en la terminal → resuelto solo; estados de la tarea | CA3 |
| `test_deliver.py`: espera el fin de turno, el diálogo y el control; una línea; aviso si no arranca un turno | CA1, CA2, CA4 |
| `test_hitl_e2e.py`: `request_human` → respuesta → el agente la recibe y termina (modo Claude y modo agy); respuesta con el CLI cerrado → llega en el reintento | CA1, CA2 |
| `test_subagents.py`: permisos, máximo, carpeta de agy ocupada, la hija no mueve la tarea, el resumen llega al padre, parada en cascada, árbol | CA4 |
| `test_hooks.py` (ampliado): subagentes nativos con las cargas reales | CA5 |
| `test_tasks_api.py` (ampliado): `create_subtask`, `parent_task_id`, subtareas n/m | CA6 |
| `test_scheduler.py` (ampliado): «Sin terminar» | CA7 |
| Frontend: `InboxPage` (cada tipo y sus acciones, pendientes y resueltas), contador, árbol, subtareas, ajustes de notificaciones, `useInboxNotifier` (una vez por elemento y según los ajustes) | CA7, CA8, CA9 |
| Pruebas manuales con Claude y agy reales y con la app empaquetada | CA1–CA5, CA8 |

## Decisiones (ADR)
**[ADR 0010](../../adr/0010-human-in-the-loop.md) · Human-in-the-loop y subagentes**:
- `request_human` sin bloquear, con la respuesta escrita en la terminal (`deliver`);
- los diálogos de permiso, detectados en pantalla y respondidos con sus teclas, y la resolución desde la terminal;
- notificaciones lanzadas desde el frontend, con `notified_at` contra duplicados;
- los subagentes de Agentic OS como ejecuciones hijas que no mueven la tarea;
- los subagentes nativos como eventos de hooks;
- los textos y las cargas reales de cada CLI (tarea 1).
