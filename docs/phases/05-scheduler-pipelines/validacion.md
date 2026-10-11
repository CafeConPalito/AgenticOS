# Fase 05: Scheduler y pipelines · Validación

- **Rama**: `phase/05-scheduler-pipelines`
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
Tests backend (pytest)              OK  181 passed  (+53 en esta fase)
Tests frontend (vitest)             OK   60 passed  (+7 en esta fase)
Tests desktop (cargo test)          OK    3 passed
Tests spikes (pytest)               OK   15 passed
```

Tests nuevos de la fase:
- **Backend**:
  - `test_scheduler.py`: orden, concurrencia, carpeta ocupada, fallos, pausa, recuperación, errores al lanzar, pipeline con rechazo, máximo de rechazos, revisión, etapa sin agente y cambio de agente;
  - `test_tasks_api.py`;
  - `test_pipelines.py`;
  - `test_worktrees.py`: repo git real con espacios en la ruta, y la identidad de reserva;
  - `test_trust.py`;
  - `test_memory_notes.py`;
  - `test_migration_0004.py`;
  - `test_context.py` y `test_mcp_server.py`, ampliados;
  - `test_scheduler_e2e.py`: backend real y CLI falso en ConPTY. Cubre dos proyectos, fallos y cierre a mano, reinicio, pipeline con una etapa en agy y worktrees en paralelo.
- **Frontend**: `tasks.test.tsx` (tablero, colas, detalle de tarea, nueva tarea, editor de pipeline) y la memoria en `projects.test.tsx`.

**CLI falso**: lee directivas del título de la tarea:
- `RECHAZA`, `RECHAZA1`: rechaza siempre, o solo la primera vez;
- `CONTEXTO`: guarda lo que devuelve `get_context`;
- `GIT`: guarda el `git status` de su carpeta;
- `SALE`: termina con un código de salida.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Cola de un agente en dos proyectos, sin compartir contexto | ✅ | **Claude Code real** (`haiku`), agente «Dev» con dos tareas en «Tienda» y «Blog», cada proyecto con una nota de memoria distinta. T-1 responde «pnpm» y T-2 «Poetry». T-2 arranca sola 35 ms después de que T-1 termine. Cada ejecución: `SessionStart → mcp_connected → … → complete_task → closing → SessionEnd`. [Evidencia](evidencias/ca1-claude-dos-proyectos.json). e2e `test_one_agent_works_through_tasks_of_two_projects`: el contexto de cada ejecución contiene la memoria y la tarea de su proyecto, y no las del otro |
| CA2 | Orden por prioridad y posición; reordenar persiste | ✅ | `test_an_agent_takes_its_queue_in_order_across_projects`, `test_reorder_changes_the_next_task`, `test_reorder_queue` (API, con 409 si la cola cambió) y el test del tablero (botones ←/→ → `PUT /queue` y aviso). El orden vive en la BD (`queue_position`) |
| CA3 | Concurrencia; carpeta directa una a la vez; worktree en paralelo | ✅ | `test_concurrency_and_the_busy_direct_folder`: el agente adelanta T-3 mientras T-2 espera por la carpeta ocupada, marcada `blocked: folder_busy`. `test_a_worktree_project_runs_tasks_in_parallel`. e2e `test_worktree_tasks_run_in_parallel_on_their_own_branches`: dos ejecuciones del mismo proyecto se solapan |
| CA4 | Pipeline con rechazo y vuelta; máximo de rechazos | ✅ | **CLIs reales**: Desarrollo con Dev (Claude) y QA con Gema (agy, puede rechazar). Dev crea `saludo.txt` con «hola». Gema **rechaza** con «contiene «hola» en lugar de «hola mundo»». Dev corrige, Gema aprueba y la tarea queda «Hecho» con 1 rechazo. [Evidencia](evidencias/ca4-ca6-pipeline-rechazo-worktree.json). Con el CLI falso: `test_a_pipeline_with_a_rejection_and_an_agy_stage` y, en unitarios, `test_too_many_rejections_wait_for_the_user` |
| CA5 | Revisión humana | ✅ | `test_review_gate`: «En revisión», no arranca nada, el rechazo exige motivo y vuelve a la etapa elegida, y la aprobación avanza. API en `test_actions_check_the_status`. UI en el test «rejects a task in review back to an earlier stage» |
| CA6 | Worktrees | ✅ | **Real**: `web2.wt\T-4` con la rama `agentic/T-4`, compartido por las cuatro ejecuciones (dos de Claude y dos de agy). Al terminar, la rama tiene `hola mundo` commiteado por Agentic OS (`chore(agentic): uncommitted work of T-4`), el worktree ya no existe y `main` está limpio. **Cancelación** de T-3 con el CLI vivo: el worktree se borra cuando el CLI se ha cerrado y la rama se conserva ([evidencia](evidencias/ca6-cancelar-en-worktree.json)). **Confianza**: agy guardó la del worktree y se quitó al terminar. Claude Code guarda la del repositorio principal, no la del worktree. Lo pendiente de Claude queda en `trust-cleanup.json` mientras Claude Code esté abierto. Tests: `test_worktrees.py`, `test_trust.py` y el e2e (el plugin de agy no aparece en `git status` del worktree) |
| CA7 | Fallos → «Esperando humano»; reintentar, dar por terminada y cancelar | ✅ | `test_a_bad_run_end_leaves_its_task_waiting` (salida, fallo, parada), `test_launch_errors`, `test_recovery_after_a_restart`. e2e `test_failures_manual_completion_and_cancel` (`exit code 3`, cierre a mano con la ejecución viva, reintento y cancelación) y `test_a_restart_leaves_the_running_task_waiting`. En la UI: «Dar por terminada» con la demo, y la ejecución pasó a «Parada» y la tarea a Desarrollo |
| CA8 | Memoria en notas | ✅ | `test_migration_0004.py` (bloques de agente con su autor, texto libre como «Tú», downgrade). `test_memory_notes.py`, `test_each_memory_write_is_its_own_note`, `test_context.py` (lo más reciente cabe; aviso), test de UI de la pestaña Memoria |
| CA9 | UI fiel a `06b`, `06c`, `07a`, `07b`, `07c`, `09a` | ✅ | Tests de componentes y revisión visual con datos de demostración: tablero por estado y por colas, detalle de tarea en ejecución, editor de pipeline, pestaña Memoria |
| CA10 | `check` en verde; ADR, README y roadmap | ✅ | Salida de arriba. [ADR 0009](../../adr/0009-scheduler-and-workspaces.md). README (sección «Tareas, colas y pipelines», variables y API). Roadmap |

## Code review
`/code-review high` sobre `main...phase/05-scheduler-pipelines`: 10 hallazgos, todos corregidos. Los de lógica tienen test de regresión.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Una tarea cuya primera etapa no tiene agente quedaba «En cola» sin agente para siempre, y desde el backlog no se podía encolar | Alta | **Corregido**: `requeue()` usa el agente de la etapa *actual* y, si no hay, la tarea pasa a «Esperando humano» (`no_agent`). Lo usan crear, encolar, reintentar y la revisión. Test `test_a_first_stage_without_agent_waits_instead_of_queueing_on_nobody` |
| En modo worktree, un fallo al lanzar hacía *rollback* de `worktree_path` con la carpeta ya creada en disco, así que todos los reintentos fallaban | Alta | **Corregido**: el worktree preparado se guarda antes de lanzar. Test `test_a_failed_launch_keeps_the_prepared_worktree` |
| Con un filtro de proyecto en el tablero, reordenar enviaba solo parte de la cola y la API respondía 409 | Media | **Corregido**: la fila conoce la cola completa del agente y envía el orden entero. Test de UI |
| Reintentar volvía a encolar con el agente guardado, no con el de la etapa tras editar el pipeline | Media | **Corregido** con `requeue()`. El mismo test que el primero |
| El resumen de «Dar por terminada» se guardaba por tarea: si la ejecución acababa justo antes, se aplicaba a la siguiente ejecución | Media | **Corregido**: va ligado a la ejecución (`run_id`), y si la ejecución ya no se puede parar se descarta y se responde 409. Test `test_a_manual_summary_only_applies_to_its_own_run` |
| Cancelar paraba la ejecución antes de hacer commit del estado: el fin de la ejecución podía leer la tarea como «En ejecución» o chocar con el bloqueo de SQLite, y no liberar el worktree | Media | **Corregido**: commit de «Cancelada» antes de parar. Lo cubre el e2e de cancelación |
| Borrar un proyecto (o una tarea con un worktree que no se pudo quitar) dejaba carpetas `.wt\T-n` que la app ya no podía limpiar | Media | **Corregido**: se liberan antes de borrar. Test `test_deleting_a_project_releases_its_task_worktrees` |
| Reordenar podía cruzar prioridades: el aviso decía «posición #1», pero la prioridad volvía a mandar | Baja | **Corregido**: solo se mueve entre tareas de la misma prioridad (los botones se desactivan). Test de UI |
| La migración ponía el texto libre del usuario después de las notas de los agentes (fecha de la migración) | Baja | **Corregido**: toma una fecha anterior a la nota más antigua. Test de la migración |
| Tras superar el máximo de rechazos, «Reintentar» volvía a lanzar QA sin que Desarrollo corrigiera, con el contador sin reiniciar | Baja | **Corregido**: el reintento vuelve a la etapa de destino del rechazo con el contador a cero. Test `test_retry_after_too_many_rejections_goes_back_to_the_fixing_stage` |

## Incidencias durante el desarrollo
1. **Migraciones de SQLite con las claves foráneas activas.** El modo *batch* recrea las tablas con `DROP TABLE` y disparaba los `ON DELETE`. La migración `0004` habría borrado todos los eventos de las ejecuciones y las notas recién convertidas, y dejado las ejecuciones sin proyecto. Ahora se migra con `foreign_keys=OFF` y se comprueba `foreign_key_check` al terminar. Hay un test con datos reales de la fase 04.
2. **El test intermitente de la fase 04** era del CLI falso: un Ctrl+C que llegaba durante un hook se convertía en `KeyboardInterrupt`. Ahora se pierde, como en los CLIs reales.
3. **Orden de los eventos de una tarea.** Dos eventos de la misma transacción pueden compartir marca de tiempo (el reloj de Windows avanza cada ~15 ms), y el desempate por UUID los desordenaba. Ahora hay una secuencia por tarea (`task_events.seq`).
4. **Con los CLIs reales: «Rama de trabajo … (haz commits en ella)»** llevó a Dev, en «Restringido» y sin la herramienta git, a pedir permiso para `git commit`. La tarea quedó «Trabajando» con el permiso pendiente en la terminal ([pantalla](evidencias/hallazgo-permiso-git-restringido.screen.txt)). Se cambió el texto: ahora dice que Agentic OS guarda lo pendiente al terminar. Ver «Impacto en fases futuras».
5. **El `check` no incluía el *typecheck* del frontend** (`tsc -p .` no comprueba nada con `files: []`). Se añadió `npm -w frontend run typecheck` al paso de lint.
6. **La UI deja de consultar la API cuando la ventana está oculta** (comportamiento por defecto de TanStack Query): en Chrome controlado, el detalle no se refrescaba hasta recargar. En una ventana visible sí refresca.
7. Los heredocs del entorno siguen estropeando `\n` y `\t` en los scripts de Python embebidos: esos cambios se hicieron con el editor.

## Retro
### Cambios respecto a la spec y al plan
- **El plugin de agy sigue excluido de git dentro de los worktrees** (el plan decía no tocar `.git/info/exclude`): un `git add -A` del agente lo commitearía con su token.
- **La confianza se limpia solo con el CLI cerrado**, y lo pendiente queda apuntado. Escribir en esos archivos con el CLI abierto puede pisar sus cambios.
- **KPIs del proyecto** calculados en el cliente con sus tareas, no en `ProjectRead`.
- **Solo hay i18n en castellano** (el plan citaba también `en`, que no existe en el proyecto).
- **Endpoint** `POST /tasks/{id}/open-worktree` y filtro `task_id` en `GET /runs`, para el detalle de tarea.

### Impacto en fases futuras
- **Fase 06**:
  - un **permiso pendiente del CLI** (Claude «¿Quieres continuar?», agy «Allow…» de herramientas que no son nuestras) no saca la tarea de «Trabajando». Detectarlo en pantalla y llevarlo a «Esperando humano» y a la Inbox encaja con `request_human`;
  - un aviso tras N minutos de inactividad sin `complete_task`.
- **Fase 07**: las columnas de coste de las tareas ya están en la UI («—»).
- **Fase 08**: las ramas `agentic/T-n` se acumulan. Habrá que decidir qué hacer con ellas: listarlas o borrarlas tras el merge.
- **`run_events`** sigue ordenándose por marca de tiempo; podría necesitar la misma secuencia que `task_events`.

## Comprobaciones pendientes del usuario
- Abrir la app y recorrer el tablero, el detalle de tarea y el editor de pipeline con datos propios.
- Las de fases anteriores (aviso de «Autónomo» en Claude Code; app instalada; «Examinar…»; F5 en una subruta; `cleanup.py --claude`).
- Las pruebas reales dejaron entradas de confianza de Claude para las carpetas de prueba (`scratchpad\real\projects\…`). Se pueden quitar con Claude Code cerrado.

## Cierre
- [x] OK del usuario (2026-10-11)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v0.6`
- [x] `docs/roadmap.md` actualizado
