# Fase 06: Subagentes y human-in-the-loop · Validación

- **Rama**: `phase/06-subagentes-hitl`
- **Fecha**: 2026-10-11

## Tests automáticos
`scripts/check.ps1`:

```
Step                                Result
----                                ------
Lint backend (ruff)                 OK
Lint frontend (eslint+prettier+tsc) OK
Lint desktop (rustfmt)              OK
Lint spikes (ruff)                  OK
Tests backend (pytest)              OK  211 passed  (+30 en esta fase)
Tests frontend (vitest)             OK   64 passed  (+4 en esta fase)
Tests desktop (cargo test)          OK    3 passed
Tests spikes (pytest)               OK   15 passed
```

Tests nuevos:
- **Backend**:
  - `test_screen.py`: diálogos de permiso a partir de **pantallas reales** guardadas como *fixtures*;
  - `test_hitl_e2e.py`: pregunta respondida desde la Inbox (Claude y agy), permiso aprobado (Claude) y rechazado (agy), diálogo respondido en la terminal;
  - `test_subagents.py`: subagente que entrega su resultado, permisos y regla de agy, subagentes nativos (CLI falso y **cargas reales** de los hooks), subtareas, parada en cascada;
  - `test_inbox.py`: revisiones, entregas y «Atención» sincronizadas con la tarea, notificaciones y ajustes;
  - `test_scheduler.py`: «Sin terminar», esperas en vivo y su recuperación, fin de un subagente;
  - regresiones del code review (tabla de abajo).
- **Frontend**: `inbox.test.tsx` (acciones de la Inbox, contador, notificador, ajustes, árbol y subtareas).

**CLI falso**: nuevas directivas `PREGUNTA:`, `PERMISO:` (dibuja el diálogo con los textos reales de cada CLI), `SUBAGENTE:`, `SUBTAREA:` y `NATIVO:` (hooks con la forma real).

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | `request_human` con Claude real: Inbox, notificación, «Esperando humano», la respuesta llega y termina | ✅ | **Claude Code real** (`haiku`): pregunta «¿Usamos Postgres o SQLite?» con opciones. Al responder «SQLite» desde la Inbox, el agente recibe el mensaje, escribe `decision.txt` = `SQLite` y termina («T-1 completada. La persona eligió SQLite…»). Eventos: `request_human` → `message_sent` → `complete_task`. [Evidencia](evidencias/ca1-ca5-clis-reales.json). e2e `test_a_question_is_answered_from_the_inbox[claude]`. Notificación: `test_notifications_bookkeeping_and_settings` y el test del notificador; la notificación nativa de Windows queda para la comprobación del usuario |
| CA2 | Lo mismo con agy real | ✅ | **agy 1.3.3**: igual que Claude, y `decision.txt` = `SQLite`. e2e `[agy]` |
| CA3 | Permisos del CLI en la Inbox: aprobar, rechazar, respondido en la terminal, estados de la tarea | ✅ | **Real**: Claude en «Preguntar» pide «PowerShell: git init …» (detalle desde el hook `PermissionRequest`); aprobado desde la Inbox, crea el repositorio y termina. agy pide «git init» (leído de la pantalla); rechazado desde la Inbox, el diálogo se cierra (`permission_answered`) y no hay repositorio. Captura previa con `POST /runs/{id}/permission`: Enter aprueba y Esc rechaza en los dos CLIs. Tests: `test_screen.py` con pantallas reales y `test_hitl_e2e.py` (aprobar, rechazar, respondido en la terminal, «Esperando humano» ⇄ «En ejecución») |
| CA4 | `spawn_subagent`: hija en el mismo workspace, en el árbol, resultado al padre, parada en cascada, rechazos | ✅ | **Claude real**: el padre lanza un subagente que crea `hijo.txt` («hola»); el padre recibe «Resultado del subagente…» y termina. El árbol muestra la ejecución hija. e2e `test_subagents.py`: permiso, carpeta ocupada de agy (error para el modelo y alternativa con un agente de Claude), parada en cascada al cancelar |
| CA5 | Subagentes nativos en el árbol | ✅ | **Real**: el subagente `Agent` de Claude («Contar archivos .txt») y el `invoke_subagent` de agy («File Reader: …») aparecen como terminados en el árbol. Tests con las cargas reales capturadas (incluido el `SubagentStop` interno de Claude, que se ignora) |
| CA6 | `create_subtask` | ✅ | `test_create_subtask_and_the_parent_counts_it`: permiso, cola, `parent_task_id`, «Subtareas 0/1», evento `subtask`. UI: test del detalle de tarea |
| CA7 | Revisiones, «Sin terminar» y entregas en la Inbox, sincronizadas | ✅ | `test_inbox.py` (revisión desde la Inbox y desde la tarea, entrega «Marcar como revisado», «Atención» descartada al reintentar, cancelación) y `test_a_run_idle_for_too_long_is_reported_as_stalled`. Real: las 6 tareas terminadas generaron su «Entrega» |
| CA8 | Notificaciones según los ajustes, una vez por elemento | ✅ / ⏳ | Backend: `notified_at` y ajustes persistidos. Frontend: el notificador avisa una vez por elemento, salta los tipos desactivados (las entregas, por defecto) y marca todo; la página de Ajustes guarda los interruptores. **Pendiente del usuario**: ver la notificación nativa de Windows en la app de escritorio (plugin de Tauri compilado y con permiso) |
| CA9 | UI fiel a `10-inbox`, árbol de `09a` y notificaciones de `12`; contador | ✅ | Tests de componentes. La Inbox reproduce la anatomía de `InboxItem` (avatar con distintivo del tipo, metadatos, comando en bloque de terminal, barra de acciones por tipo, «Abrir terminal», resultado en lo resuelto) |
| CA10 | `check` en verde; ADR, README y roadmap | ✅ | Salida de arriba; [ADR 0010](../../adr/0010-human-in-the-loop.md); README (sección «Inbox y subagentes» y API); roadmap |

## Code review
`/code-review` de la rama: 10 hallazgos, todos corregidos.

| # | Hallazgo | Corrección | Test |
|---|---|---|---|
| 1 | `_active_run` de la tarea podía devolver un subagente | Filtra `parent_run_id IS NULL` | `test_the_task_shows_its_own_run_not_a_subagent` |
| 2 | «Reintentar» con el CLI vivo (pregunta o permiso) lanzaba una segunda ejecución | `retry()` da 409 `task_live`; la UI oculta el botón | `test_live_waits_hold_the_agent_until_their_cli_is_gone` |
| 3 | Una espera «en vivo» con el CLI ya muerto seguía ocupando al agente; al reiniciar, quedaba colgada | Nuevo motivo `question_pending` (no ocupa al agente); `recover()` convierte las esperas en vivo y descarta las aprobaciones | `test_live_waits_hold_…`, `test_recovery_turns_live_waits_into_offline_ones` |
| 4 | La respuesta a un subagente ya terminado se perdía | Se escribe en el CLI de su padre si sigue vivo | `test_an_answer_to_an_ended_subagent_reaches_its_parent` |
| 5 | Dos diálogos iguales seguidos de Claude contaban como uno | La firma de Claude es solo el tipo; responder reinicia el estado y da el diálogo por resuelto; 1 s sin leer la pantalla | `test_screen.py`, `test_hitl_e2e.py` |
| 6 | Un subagente que terminaba con un permiso abierto dejaba la tarea esperando | Su fin descarta sus aprobaciones y reanuda la tarea | `test_a_subagent_ending_frees_its_permission_wait_and_releases_last` |
| 7 | El worktree se liberaba con subagentes aún vivos | Se libera cuando no queda ninguna ejecución de la tarea viva | El mismo test |
| 8 | Descartar una pregunta dejaba la tarea esperando para siempre | Se avisa al agente para que siga sin la respuesta (o la tarea vuelve a la cola) | `test_dismissing_a_question_lets_the_task_go_on` |
| 9 | La detección del diálogo de Claude era laxa (`amend` y «No» sueltos) | Exige «Tab» en el pie con `amend` y «3. No» | `test_claude_output_that_only_looks_like_a_dialog_is_not_one` |
| 10 | Diccionarios por ejecución que no se vaciaban; el detalle del hook podía pasar al diálogo siguiente | Se vacían al terminar la ejecución; el detalle se consume al usarlo | Cubierto por los e2e |

## Incidencias durante el desarrollo
1. **Textos reales de los diálogos** (tarea 1): la pantalla emulada descoloca el texto de Claude («Tab t  amend», nombres de archivo perdidos). Se detecta por fragmentos estables y el detalle sale del hook `PermissionRequest`.
2. **«Tomar control» enviaba Esc**, que rechaza un diálogo de permiso abierto. Ya no lo envía si hay un diálogo.
3. **Los hooks de herramienta de agy necesitan el formato con `matcher`**. Con la forma plana, agy no los enviaba.
4. **El subagente nativo de agy usa su propia conversación** por el mismo plugin. Su `conversationId` sustituía el id de sesión de la ejecución y marcaba turnos que no eran suyos. Corregido.
5. **Esperas «en vivo»**: con la tarea en «Esperando humano» y el CLI vivo, el scheduler veía al agente libre y podía lanzar otra tarea en la misma carpeta. Ahora esas esperas ocupan su hueco y su carpeta.
6. **La terminal de la tarea mostraba la ejecución del subagente**, la última creada. `active_run_id` y `last_run_id` excluyen ahora a los subagentes.
7. **Memoria**: siete sesiones reales a la vez, con otro programa pesado abierto, dejaron el sistema sin memoria y Claude Code paró las pruebas. Se repitieron de una en una.
8. **Tests del frontend con la máquina ocupada**: se subieron los límites de tiempo (15 s por test, 3 s en `findBy`).
9. Los heredocs siguen estropeando las barras invertidas en Python embebido. Queda anotado en la memoria del proyecto.

## Retro
### Cambios respecto a la spec y al plan
- **Nuevo tipo en la Inbox, «Atención»**: las tareas que esperan al usuario por un fallo aparecen en la Inbox con Reintentar, no solo en el tablero.
- **`POST /runs/{id}/permission`**: responder al diálogo desde la ejecución, además de desde la Inbox.
- **`AGENTIC_OS_HOOK_LOG`**: registro opcional de las cargas de los hooks, para depurar.
- Tarea 1 (captura) adelantada con parte de H3, porque responder a los diálogos sin el Esc de «Tomar control» exigía ya esa pieza.

### Impacto en fases futuras
- **Fase 07**: los subagentes (de Agentic OS y nativos) tienen su propio consumo. En Claude, el transcript del subagente llega en `agent_transcript_path` de `SubagentStop`.
- **Fase 08**: la notificación nativa y el clic que lleva a la Inbox en la app empaquetada; políticas de aprobación automática.
- **Fase 12**: los avisos externos pueden reutilizar `notified_at` y los tipos de la Inbox.

## Comprobaciones pendientes del usuario
- En la app de escritorio, comprobar la **notificación nativa de Windows** (Ajustes → «Probar aviso») y que llega un aviso con una pregunta real.
- Recorrer la Inbox y el árbol de ejecución con datos propios.
- Las de fases anteriores.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.7`
- [ ] `docs/roadmap.md` actualizado
