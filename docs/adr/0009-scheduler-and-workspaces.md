# ADR 0009: Scheduler, colas y workspaces

- **Estado**: borrador (se completa con los worktrees, hito H4 de la fase 05)
- **Fecha**: 2026-10-11
- **Contexto de decisión**: fase 05 ([`spec.md`](../phases/05-scheduler-pipelines/spec.md), [`plan.md`](../phases/05-scheduler-pipelines/plan.md))

## Contexto
Desde la fase 05, los agentes trabajan como empleados:
- cada uno tiene una **cola de tareas** y la recorre solo;
- cada tarea puede pasar por las **etapas** del pipeline de su proyecto;
- una etapa puede **rechazar** y devolver la tarea, o esperar una **revisión** humana.

Hay que decidir:
- quién elige la siguiente tarea y cuándo;
- en qué orden;
- qué pasa cuando algo falla;
- en qué carpeta trabaja cada tarea.

Y todo sin carreras sobre SQLite y sin perder trabajo del agente.

## Decisión
### Un único hilo de scheduler
- `services/scheduler.py` tiene **un hilo** que hace todo el trabajo:
  - procesar los finales de ejecución (`run_ended`);
  - y después arrancar lo que se pueda (`tick`).
- Se despierta con `poke()` (una tarea creada, encolada, reordenada o editada, la pausa…), cuando termina una ejecución y, como red de seguridad, cada 5 s.
- Al ser un solo hilo, nunca hay dos decisiones a la vez sobre las mismas colas: no hace falta bloquear filas.
- El `RunManager` avisa con `on_run_ended(run_id)` **después** de guardar el estado final de la ejecución y de limpiar sus archivos.
- La API nunca lanza ejecuciones de tareas: solo cambia el estado de las tareas y despierta al scheduler.

### Colas
- **Una cola por agente**: sus tareas `queued`, ordenadas por **prioridad** (alta · normal · baja) y después por **posición**.
- **Al final** de su prioridad entra: una tarea nueva, y una que pasa a la siguiente etapa.
- **Al principio** entra: una rechazada, una reintentada y una rechazada en revisión. Una tarea que vuelve no espera otra vez toda la cola.
- **Reordenar** reescribe las posiciones con la lista completa de la cola. Si la cola cambió entre tanto, se responde 409 `queue_changed`, para no pisar un orden que el usuario no ha visto.
- **Concurrencia**: un agente tiene a la vez como mucho `max_concurrency` tareas `running`. Las ejecuciones manuales no cuentan.
- **Única excepción al orden**: en un proyecto de **carpeta directa** solo puede haber una tarea en ejecución. Si la primera de la cola no puede arrancar por eso, el agente **adelanta** la siguiente que sí pueda (decidido al aprobar la spec). La API la marca como `blocked: "folder_busy"`; ese dato se calcula al leer, no se guarda.
- **Errores al lanzar**:
  - `agy_folder_busy` (una ejecución manual de agy en esa carpeta) es pasajero: la tarea sigue en cola;
  - cualquier otro error deja la tarea en «Esperando humano» (`launch_failed`) con el mensaje.
- **Pausa global** (`app_state.scheduler_paused`): con la pausa no se arranca nada, pero se siguen procesando los finales.

### Ciclo de vida de una tarea
| Fin de la ejecución | Tarea |
|---|---|
| `completed` + `verdict = approved` | Revisión si la etapa la pide; si no, siguiente etapa o «Hecho» |
| `completed` + `verdict = rejected` | Vuelve a la etapa `reject_to` (al principio de la cola). Si supera `max_rejections`, queda «Esperando humano» |
| `exited`, `failed`, `stopped`, `interrupted` | «Esperando humano», con el motivo (p. ej. `run_exited` y «exit code 3») |

- **Veredicto**: `complete_task(summary, verdict)`. `rejected` solo vale en una etapa con `reject_to`; en otro caso, la herramienta devuelve un error al modelo y no registra nada.
- **«Dar por terminada»** con una ejecución viva: el scheduler apunta el resumen, se para la ejecución y, cuando termina, la etapa cuenta como aprobada.
- **Una ejecución interrumpida nunca se relanza sola.** Al arrancar, las tareas `running` sin ejecución viva pasan a «Esperando humano» (`interrupted`). Al cerrar la app, el scheduler se para **antes** que las ejecuciones: sus tareas aparecen como interrumpidas en el siguiente arranque, no como paradas por el usuario.
- **Cancelar** para la ejecución. El workspace se libera cuando el CLI ya se ha cerrado.
- **Historial** (`task_events`): cada paso queda registrado (creada, en cola, etapa iniciada o terminada, rechazo, revisión, esperando, reintento, cancelada, hecha). Los resúmenes y rechazos de las etapas anteriores se inyectan en el contexto de la siguiente ejecución.

### Contexto de cada ejecución de tarea
Las instrucciones de la ejecución añaden la tarea (código, título y descripción), la etapa («Etapa 2 de 3: Desarrollo»), el motivo de la vuelta si la hubo, el historial y, en las etapas que revisan, las reglas del veredicto. Las variables `$PROYECTO`, `$ETAPA`, `$TAREA`, `$MEMORIA` y `$WORKSPACE` se sustituyen en las instrucciones del agente. El prompt inicial es `T-142 · <título>` + descripción.

### Memoria del proyecto
La memoria pasa a ser una **tabla de notas** (`memory_notes`) con su autor. A los agentes les llegan las más recientes que caben en 12 000 caracteres, y la UI avisa cuando no caben todas.

### Migraciones en SQLite
Las migraciones se ejecutan con `PRAGMA foreign_keys=OFF` y comprueban `PRAGMA foreign_key_check` al terminar. El modo *batch* recrea las tablas con `DROP TABLE`; con las claves foráneas activas, eso disparaba las acciones `ON DELETE`. Con la migración `0004`, se habrían borrado todos los eventos de las ejecuciones y las notas recién convertidas, y las ejecuciones habrían perdido su proyecto.

### Workspaces
*(Se completa en el hito H4: layout `<proyecto>.wt\T-n`, rama `agentic/T-n`, commit de lo que quede sin commitear, limpieza de la confianza, plugin de agy excluido de git también en los worktrees.)*

### UI
La UI se actualiza consultando la API cada 2–3 s mientras hay tareas activas, y usa el WebSocket de cada ejecución para la terminal y los eventos. Un canal global de eventos queda para más adelante.

## Consecuencias
- ✅ Un agente encadena tareas de varios proyectos sin intervención, cada una en una sesión nueva y con el contexto de su proyecto (verificado e2e con el CLI falso).
- ✅ Los fallos nunca bloquean la cola: la tarea espera al usuario con el motivo y el agente sigue.
- ⚠️ Si el modelo no llama a `complete_task`, la tarea ocupa un hueco del agente hasta que el usuario la da por terminada o la cancela.
- ⚠️ El orden estricto se rompe a propósito en un caso (carpeta ocupada); la tarjeta lo indica.
