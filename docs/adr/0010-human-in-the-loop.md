# ADR 0010: Human-in-the-loop y subagentes

- **Estado**: aceptado
- **Fecha**: 2026-10-11
- **Contexto de decisión**: fase 06 ([`spec.md`](../phases/06-subagentes-hitl/spec.md), [`plan.md`](../phases/06-subagentes-hitl/plan.md))

## Contexto
Los agentes tienen que poder pedir cosas a la persona (aprobaciones, preguntas, bloqueos) sin que esta vigile su terminal, y repartir trabajo en subagentes. Las decisiones dependen de cómo se comportan Claude Code y agy de verdad: la tarea 1 de la fase los capturó con Claude Code 2.1.296 y agy 1.3.3 (pantallas en `backend/tests/fixtures/screens`, cargas de hooks en `backend/tests/fixtures/hooks`).

## Decisión
### Diálogos de permiso de los CLIs
- **Claude Code** («Do you want to proceed?», «Do you want to create nota.txt?»):
  - opciones «1. Yes» (seleccionada), «2. Yes, and…», «3. No»;
  - pie «Esc to cancel · Tab to amend».
- **agy**: «Requesting permission for: <comando> / Run this command? / > 1. Yes, run command … 4. No, cancel / ↑/↓ Navigate · tab Amend · esc to cancel».
- **Teclas**, verificadas con los CLIs reales: **Enter aprueba** (la opción 1 viene seleccionada) y **Esc rechaza**.
  - Claude con Enter: crea el archivo y sigue.
  - agy con Esc: cancela el comando y vuelve a su entrada.
- **La pantalla emulada (pyte) descoloca parte del texto de Claude** (glifos anchos): «Tab to amend» aparece a veces como «Tab t  amend» y se pierden nombres de archivo. Por eso:
  - el diálogo de Claude se detecta por fragmentos cortos y estables al pie (`amend`, «1. Yes», «No»);
  - **el detalle se toma del hook `PermissionRequest` de Claude** (`tool_name` + `tool_input`: «Write: …\nota.txt»), no de la pantalla;
  - en agy, el comando se lee de la pantalla (la línea tras «Requesting permission for:»), que llega entera.
- Un diálogo cuenta cuando está **0,5 s** en pantalla, y se da por respondido cuando falta **1,5 s** (las TUI redibujan).
- **«Tomar control» ya no envía Esc si hay un diálogo de permiso**: Esc lo rechazaría.
- Comandos de solo lectura (`git --version`, `Get-ChildItem | Measure-Object`) no piden permiso en Claude.

### Hooks de los subagentes nativos
- **Claude**:
  - `PreToolUse` y `PostToolUse` con `matcher: "Agent|Task"` traen `tool_name: Agent` y `tool_input` con `description` y `prompt`. `PostToolUse` vuelve enseguida (`async_launched`);
  - `SubagentStart` y `SubagentStop` llevan `agent_id` y `agent_type`;
  - Claude también envía **`SubagentStop` de subagentes internos** (`agent_type` vacío, sin `SubagentStart` previo): solo cuentan los que tuvieron inicio.
- **agy**:
  - los eventos de herramienta en `hooks.json` **necesitan otro formato**: `{"matcher": "invoke_subagent", "hooks": [{"type": "command", …}]}`. Con la forma plana de `PreInvocation`/`Stop`, agy no los envía;
  - `PreToolUse` y `PostToolUse` de `invoke_subagent` traen `Subagents[]` con `Role`, `Prompt`, `TypeName` y un `toolSummary`. `PostToolUse` vuelve enseguida;
  - **el subagente tiene su propia conversación** y dispara `PreInvocation` con su `conversationId` por el mismo plugin, pero **nunca envía su `Stop`**. La conversación principal termina su turno con `fullyIdle: false` mientras el subagente sigue;
  - **corregido**: esos hooks no sustituyen el id de sesión de la ejecución ni marcan sus turnos (antes, el `conversationId` del subagente sobrescribía el de la ejecución).

### Escribir en la terminal del agente (`deliver`)
- Cada sesión tiene una **cola de mensajes**. Se escriben cuando el CLI espera entrada:
  - fuera de turno, según los hooks;
  - sin diálogos ni una persona con el control;
  - en agy, con «? for shortcuts» y después de su prompt inicial;
  - y con al menos 2 s entre mensajes.
- **Una sola línea**, con los saltos convertidos en « / » (Enter enviaría en el primero) y recortada a 1800 caracteres.
- Si en 20 s no empieza un turno, se registra `waiting_for_human` (`message_not_started`).
- La usan la respuesta a `request_human` y el resultado de un subagente para su padre.

### `request_human` sin bloquear
- La herramienta crea una «Pregunta» (con `options`) o un «Bloqueo» en la Inbox, pone la tarea en «Esperando humano» (`human_request`) y le dice al modelo que termine su turno.
- Al responder:
  - con el CLI vivo, se escribe «Respuesta de la persona a «…»: …» y la tarea vuelve a «En ejecución»;
  - si el CLI se cierra antes de la respuesta (o la app se reinicia), la tarea pasa a «Tiene una pregunta sin responder» (`question_pending`), que ya no ocupa al agente. Al responder, la pregunta y la respuesta quedan en el historial de la tarea (están en el contexto del siguiente intento) y la tarea vuelve a la cola, al principio;
  - si la pregunta era de un subagente que ya terminó, la respuesta se escribe en su padre;
  - descartar la pregunta también se le dice al agente, para que siga sin la respuesta.
- Mientras el CLI vive, «Reintentar» no está disponible (lanzaría una segunda ejecución).
- Verificado con Claude Code y agy reales: los dos preguntan, reciben la respuesta y la usan.

### Esperas «en vivo»
- Una tarea que espera con su CLI vivo (`human_request`, `permission`) **sigue ocupando el hueco de su agente y la carpeta directa**. Si no, el scheduler podría lanzar otra tarea en la misma carpeta.
- Cuando la espera se resuelve, vuelve sola a «En ejecución» (`task_ops.resume`).

### Inbox
- Tipos:
  - Aprobación (diálogo del CLI);
  - Pregunta y Bloqueo (`request_human`);
  - Revisión (etapa con revisión);
  - Sin terminar (10 minutos esperando entrada sin `complete_task`);
  - Entrega (tarea «Hecho»);
  - **Atención** (añadido en esta fase): una tarea en «Esperando humano» por un fallo (CLI terminado sin `complete_task`, demasiados rechazos, lanzamiento fallido…), con Reintentar.
- Los elementos siguen a la tarea:
  - una revisión resuelta desde la tarea se resuelve también en la Inbox, y al revés;
  - volver a la cola descarta «Atención» y «Sin terminar»;
  - terminar o cancelar la tarea descarta todo lo pendiente.
- Se copian el agente y el proyecto, para que lo resuelto siga siendo legible aunque se borren.

### Notificaciones
- **Las lanza el frontend**, porque el backend es un *sidecar* sin ventana:
  - en la app de escritorio, el plugin oficial de notificaciones de Tauri (permiso `notification:default`);
  - en el navegador, la API `Notification`.
- `GET /inbox/summary` se consulta cada 3 s, también con la ventana en segundo plano. Cada elemento se marca con `notified_at` al notificarlo, o al saltarlo si su tipo está desactivado: así nunca se avisa dos veces, aunque haya dos ventanas.
- Los ajustes (un interruptor por tipo y el sonido) se guardan en el backend (`app_state`).

### Subagentes de Agentic OS
- `spawn_subagent(prompt, agent)` lanza una **ejecución hija** (`parent_run_id`):
  - de la misma tarea y etapa, en la misma carpeta;
  - con una sección «Eres un subagente de <padre>» en sus instrucciones.
- Condiciones:
  - el agente necesita «Puede lanzar subagentes»;
  - como mucho 3 hijas vivas;
  - un subagente no lanza otros;
  - agy no puede trabajar en una carpeta ocupada por otro agy (el error vuelve al modelo).
- **El scheduler ignora el fin de las hijas**: no mueven la tarea. Su resultado se entrega al padre con `deliver`.
- Parar el padre (o que termine) para a sus hijas.
- `active_run_id` y `last_run_id` de la tarea son siempre sus ejecuciones principales, no las de los subagentes.
- Verificado con Claude real: el padre lanza al hijo, que crea el archivo, y el padre recibe su resultado y termina.

### Subtareas
`create_subtask` (con «Puede crear tareas») crea una tarea en el mismo proyecto con `parent_task_id`, que entra en cola como cualquier otra. La tarea padre muestra «Subtareas n/m».

## Consecuencias
- ✅ Las aprobaciones, las preguntas y los bloqueos llegan a la Inbox y como notificación, y la respuesta desbloquea al agente sin tomar el control (verificado con Claude Code y agy reales).
- ✅ Un diálogo respondido directamente en la terminal resuelve su elemento.
- ⚠️ Si el modelo no termina su turno tras `request_human`, la respuesta se escribe en su siguiente fin de turno.
- ⚠️ Varios agentes en la misma carpeta (subagentes) pueden pisarse archivos. Las instrucciones del subagente se lo advierten.
- ⚠️ La detección de los diálogos de permiso depende de textos de las TUI. Están centralizados en `screen.py` y cubiertos por tests con las pantallas reales.
- ⚠️ El fin de un subagente nativo de agy no se conoce con exactitud: se deduce del siguiente turno de la conversación principal, o del fin de la ejecución.

