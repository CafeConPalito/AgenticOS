# Fase 06: Subagentes y human-in-the-loop · Spec

- **Estado**: aprobada
- **Rama**: `phase/06-subagentes-hitl`

## Objetivo
Que los agentes puedan **pedirte cosas sin que tengas que vigilar su terminal**, y que **repartan trabajo**:
- **pedirte cosas**: aprobaciones, preguntas y bloqueos llegan a una **Inbox** y a una **notificación de Windows**. Respondes desde ahí y el agente sigue;
- **repartir trabajo**: lanzar subagentes en paralelo o crear subtareas. Todo se ve en el **árbol de ejecución** de la tarea, incluidos los subagentes nativos de cada CLI.

Cierra además el hueco que dejó la fase 05: un permiso pendiente del CLI dejaba la tarea en «Trabajando».

## Alcance
### Dentro
**Inbox** (pantalla `10-inbox`). Tipos de elemento:

| Tipo | Origen | Acciones |
|---|---|---|
| **Aprobación** | Diálogo de permiso del CLI detectado en pantalla, con el comando o la acción | Aprobar · Rechazar |
| **Pregunta** | `request_human` con opciones | Chips de opción · texto libre · Responder |
| **Bloqueo** | `request_human` sin opciones | Texto libre · Responder |
| **Revisión** | Etapa con «Requiere revisión» (fase 05) | Aprobar · Rechazar con motivo |
| **Sin terminar** | La ejecución lleva N minutos esperando sin `complete_task` | Dar por terminada · Abrir terminal |
| **Entrega** | Tarea terminada («Hecho») | Marcar como revisado |

- Todos los elementos llevan: agente, proyecto, enlace a la tarea, tiempo y «Abrir terminal» (abre el dock en esa ejecución).
- Vistas **Pendientes / Resueltas**. Lo resuelto muestra el resultado («✓ Aprobado por ti», «Respondido: «…»», «Respondido en la terminal»).
- **Contador de pendientes** en la barra lateral.
- Resolver desde la Inbox tiene el mismo efecto que hacerlo desde la tarea, y al revés: aprobar una revisión en la tarea la resuelve en la Inbox.

**`request_human`** (MCP), sin bloquear la llamada:
- `request_human(title, detail, options?)`: con `options` es una pregunta y sin ellas, un bloqueo;
- la herramienta crea el elemento en la Inbox y pide al agente que **termine su turno**. La tarea pasa a «Esperando humano» (`human_request`);
- al responder, Agentic OS **escribe la respuesta en la terminal** del agente como un mensaje nuevo, y la tarea vuelve a «En ejecución»;
- si el CLI ya no está vivo (se cerró o se reinició la app), la respuesta queda en el historial de la tarea y llega en el contexto del reintento.

**Permisos del CLI en la Inbox**:
- Agentic OS detecta en pantalla los diálogos de permiso de Claude Code («Do you want to proceed?» y similares) y de agy (permisos de comandos y de herramientas que no son de `agentic-os`), y extrae el comando o la acción;
- crea una «Aprobación» y la tarea pasa a «Esperando humano» (`permission`);
- **Aprobar** o **Rechazar** responde al diálogo en la terminal;
- si la persona responde directamente en la terminal, el elemento se resuelve solo («Respondido en la terminal»);
- los diálogos de nuestras herramientas MCP en agy se siguen aprobando solos (fase 04).

**Subagentes de Agentic OS** (`spawn_subagent`):
- `spawn_subagent(prompt, agent?)` lanza una **ejecución hija** del agente indicado (por defecto, el mismo) en el mismo workspace que la ejecución padre, en paralelo;
- solo pueden hacerlo los agentes con «Puede lanzar subagentes». Hay un máximo de subagentes vivos por ejecución (3);
- la hija recibe el contexto de la tarea y su propio prompt, y termina con `complete_task`. Su **resumen llega a la terminal del padre** como un mensaje, en cuanto el padre termina su turno;
- al cancelar o parar el padre, se paran sus hijas;
- los subagentes no cuentan para la concurrencia del agente (son parte de la tarea del padre);
- **límite de agy**: un subagente agy no puede trabajar en la misma carpeta que otra ejecución de agy, porque el plugin es por carpeta. Se rechaza con un error claro para el modelo.

**Subagentes nativos de los CLIs**:
- se detectan sin cambiar nada en los CLIs:
  - Claude Code: hooks `SubagentStart`/`SubagentStop` y la herramienta `Agent` en `PreToolUse`;
  - agy: `PreToolUse` con `invoke_subagent` (rol y prompt);
- aparecen en el árbol como nodos de la ejecución que los lanzó, con su descripción y su duración. No tienen terminal propia.

**Subtareas** (`create_subtask`):
- `create_subtask(title, description, agent?)` crea una tarea en el mismo proyecto, ligada a la tarea actual;
- solo pueden hacerlo los agentes con «Puede crear tareas»;
- entra en la cola como cualquier tarea (primera etapa del pipeline, o el agente indicado);
- en el detalle de la tarea padre se ve la lista **Subtareas n/m** (`09a`), con su estado.

**Árbol de ejecución** (columna derecha de `09a`):
- muestra la ejecución principal, sus subagentes de Agentic OS (con su terminal) y los subagentes nativos (sin terminal), con su estado y duración;
- al pulsar un nodo con terminal, la terminal central pasa a esa ejecución.

**Inactividad**: si una ejecución de tarea lleva **10 minutos** en «Esperando» sin llamar a `complete_task`, se crea un elemento «Sin terminar» en la Inbox. Nunca se cierra sola.

**Notificaciones de Windows**:
- con la app de escritorio, notificación nativa (plugin de notificaciones de Tauri). En el navegador (desarrollo), Web Notifications si el usuario las permite;
- se avisa de Aprobaciones, Preguntas y Bloqueos, Revisiones, Sin terminar, Entregas y rechazos entre etapas;
- en **Ajustes**, un interruptor por tipo y otro para el sonido, según el diseño (`12`). Se guardan en el backend;
- al pulsar la notificación se abre la Inbox en ese elemento.

**Estados de tarea**: dos motivos nuevos de «Esperando humano»: `human_request` y `permission`. La tarea vuelve sola a «En ejecución» al resolverse.

### Fuera
- Avisos externos: Telegram, email y Slack (fase 12).
- Rediseño del Dashboard con las aprobaciones pendientes.
- Consumo de los subagentes (fase 07).
- Pausar una tarea concreta.
- Subagentes en otro workspace o en otro proyecto.
- Políticas de aprobación automática («aprobar siempre `npm test`»).
- Respuestas desde la notificación sin abrir la app.

## Historias de usuario
- Como usuario, quiero que, si un agente necesita una decisión mía, me llegue un aviso y pueda contestar desde la Inbox sin buscar su terminal.
- Como usuario, quiero aprobar o rechazar desde la Inbox los comandos que un agente en «Preguntar» o «Restringido» quiere ejecutar.
- Como usuario, quiero que un agente pueda repartir trabajo en subagentes o subtareas, y ver ese reparto en el árbol de ejecución.
- Como usuario, quiero ver cuándo Claude Code o agy lanzan sus propios subagentes.
- Como usuario, quiero elegir de qué me avisa Windows.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **`request_human` con Claude real**: la pregunta llega a la Inbox y como notificación; la tarea queda «Esperando humano»; al responder desde la Inbox, el agente recibe la respuesta en su terminal, la usa y termina la tarea | Prueba manual + e2e con el CLI falso |
| CA2 | Lo mismo con **agy real** | Prueba manual + e2e |
| CA3 | **Permisos del CLI**: el diálogo de permiso de Claude y el de agy crean una Aprobación con el comando. Aprobar y Rechazar responden al diálogo; responder en la terminal la resuelve sola; la tarea entra y sale de «Esperando humano» | Tests de pantalla con textos reales + prueba manual con los dos CLIs |
| CA4 | **`spawn_subagent`**: crea una ejecución hija en el mismo workspace, visible en el árbol; su resumen llega al padre; parar al padre para a las hijas. Se rechaza sin el permiso del agente, por encima del máximo y con agy en una carpeta ocupada | e2e con el CLI falso + prueba manual con Claude |
| CA5 | **Subagentes nativos**: un subagente de Claude (`Agent`) y uno de agy (`invoke_subagent`) aparecen en el árbol con su descripción y su duración | Tests de hooks con cargas reales + prueba manual |
| CA6 | **`create_subtask`**: respeta el permiso, la subtarea entra en la cola correcta y la tarea padre muestra «Subtareas n/m» | Tests de la API y e2e |
| CA7 | **Revisiones, «Sin terminar» y entregas** en la Inbox; resolverlas desde la Inbox o desde la tarea da el mismo resultado | Tests |
| CA8 | **Notificaciones**: se envían según los interruptores de Ajustes, que persisten; al pulsar se abre la Inbox; no hay ninguna con el tipo desactivado | Tests + prueba manual en la app de escritorio |
| CA9 | **UI** fiel a `10-inbox`, al árbol de `09a` y a la sección de notificaciones de `12`; contador en la barra lateral | Tests de componentes + capturas |
| CA10 | `check` en verde; ADR, README y roadmap actualizados | Salida del `check` + revisión |

## Prerrequisitos
- Fase 05 cerrada (`v0.6`).
- Claude Code y agy instalados y con sesión iniciada; la app de escritorio para probar las notificaciones nativas.

## Riesgos y preguntas abiertas
- **Escribir en la terminal de un agente**: la respuesta solo se escribe cuando el CLI espera entrada (fin de turno y sin diálogo abierto), como el prompt diferido de la fase 04. Si nunca llega ese momento, se avisa en la Inbox.
- **El modelo puede no terminar su turno** tras `request_human` y seguir trabajando. Las instrucciones y la respuesta de la herramienta se lo piden; si sigue, la respuesta se escribe en su siguiente fin de turno.
- **Detectar los diálogos de permiso en pantalla** depende de los textos de cada TUI. Se centralizan en `screen.py` con textos reales capturados de los dos CLIs, como en la fase 04; la primera tarea del plan es capturarlos.
- **Varias ejecuciones en el mismo workspace** (subagentes): pueden pisarse archivos. Es responsabilidad del agente repartir bien; Agentic OS solo lo documenta en las instrucciones del subagente.
- **Notificaciones en Tauri**: hace falta el plugin oficial y su permiso en la *capability*. En Windows, el remitente de la notificación debe aparecer como «Agentic OS».
- **Límite de 3 subagentes y 10 minutos de inactividad**: valores iniciales. Se podrán configurar en el futuro.
