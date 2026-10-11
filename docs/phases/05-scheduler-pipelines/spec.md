# Fase 05: Scheduler y pipelines · Spec

- **Estado**: aprobada
- **Rama**: `phase/05-scheduler-pipelines`

## Objetivo
Pasar de lanzar ejecuciones a mano a **asignar tareas** y que los agentes trabajen como empleados:
- cada agente tiene su **cola** y la recorre solo, respetando su concurrencia;
- cada tarea arranca una sesión nueva con el contexto de su proyecto, y nada más;
- un proyecto puede tener un **pipeline** (p. ej. Requisitos → Desarrollo → QA) que lleva cada tarea de una etapa a la siguiente;
- si QA rechaza, la tarea vuelve a Desarrollo con el motivo.

Se apoya en la señal de fin que dejó la fase 04: `complete_task` + resumen y el CLI cerrado solo ([ADR 0008](../../adr/0008-agent-coordination.md)).

## Alcance
### Dentro
**Tareas**:
- Campos:
  - ID corto legible (`T-142`), título y descripción (lo que se le pide al agente);
  - proyecto y prioridad (alta · normal · baja);
  - etapa actual y estado.
- Estados:

  | Estado | Significado |
  |---|---|
  | Backlog | Creada, sin encolar |
  | En cola | Esperando turno en la cola del agente de su etapa |
  | En ejecución | Hay una ejecución activa de la tarea |
  | Esperando humano | Necesita una acción del usuario: la ejecución terminó sin `complete_task`, falló, se interrumpió o se superó el máximo de rechazos. Se muestra el motivo |
  | En revisión | La etapa terminó y tiene revisión humana: espera tu aprobación |
  | Hecho | Terminó la última etapa |
  | Cancelada | La canceló el usuario |
- Cada tarea guarda su **historial**: ejecuciones por etapa, resúmenes, veredictos y motivos de rechazo.
- **Sin pipeline**, una tarea se asigna directamente a un agente (una sola etapa implícita).

**Colas y scheduler**:
- **Una cola por agente**, en orden estricto: por prioridad y, dentro de cada prioridad, por posición. El usuario puede reordenarla.
- El scheduler arranca la siguiente tarea en cuanto el agente tiene hueco (`max_concurrency`) y el workspace lo permite.
- Cuando la ejecución termina «Completada», la tarea avanza y el agente pasa a la siguiente de su cola, aunque sea de otro proyecto.
- **Sin contexto compartido**: cada tarea es una sesión nueva del CLI, con las instrucciones del agente, la memoria de **su** proyecto y la información de **su** tarea.
- Las colas y las tareas viven en la BD: sobreviven a un reinicio. Una ejecución interrumpida por el reinicio deja su tarea en «Esperando humano»; no se relanza sola.
- Interruptor global **Pausar / Reanudar el scheduler**: en pausa no arranca nada nuevo y las ejecuciones en curso siguen.
- Las ejecuciones manuales de la fase 03 siguen existiendo; no cuentan para la cola del agente.

**Pipelines**:
- **Un pipeline por proyecto**, opcional, con etapas ordenadas. Cada etapa tiene:
  - un nombre y un agente;
  - «Requiere revisión» (puerta humana): opcional;
  - «Puede rechazar», con una etapa de destino anterior.
- Máximo de rechazos por tarea, configurable (3 por defecto). Al superarlo, la tarea pasa a «Esperando humano».
- Plantilla inicial **«Desarrollo web»**: Requisitos → Desarrollo → QA, donde QA puede rechazar y la tarea vuelve a Desarrollo.
- Editar el pipeline no rompe las tareas en curso. No se puede borrar una etapa con tareas activas.

**Veredicto en `complete_task`**:
- `complete_task(resumen, resultado)`, con `resultado` = `aprobado` (por defecto) o `rechazado`.
- `rechazado` solo vale en etapas que pueden rechazar; en las demás, la herramienta lo devuelve como error al modelo.
- Si rechaza, la tarea vuelve a la etapa de destino y la nueva ejecución recibe el motivo en su contexto.

**Contexto por etapa** (amplía el context builder de la fase 04):
- la tarea (título y descripción) y la etapa actual;
- los resúmenes de las etapas anteriores y, si viene de un rechazo, el motivo;
- la carpeta de trabajo (proyecto o worktree);
- las variables `$PROYECTO`, `$ETAPA`, `$TAREA`, `$MEMORIA` y `$WORKSPACE` en las instrucciones del agente, como en el diseño (`03c`).
- `get_context` devuelve lo mismo.

**Revisión humana**:
- Cuando termina una etapa con «Requiere revisión», la tarea queda «En revisión».
- Desde la tarea puedes:
  - **Aprobar**: pasa a la siguiente etapa;
  - **Rechazar con un motivo**: vuelve a la etapa de destino o a la misma.
- Sin Inbox ni notificaciones (fase 06).

**Acciones del usuario sobre una tarea**:
- Crear (al backlog o directamente en cola), editar y cambiar la prioridad.
- **Reintentar**: nueva sesión en la misma etapa y el mismo workspace.
- **Dar la etapa por terminada a mano**, con un resumen: para cuando el modelo olvida llamar a `complete_task`.
- **Cancelar**: detiene la ejecución activa.
- Tomar el control de la terminal, como en la fase 03.

**Workspaces**, según el modo del proyecto:
- **Carpeta directa**: como máximo **una tarea en ejecución por proyecto**. Cubre también la limitación de agy (una ejecución por carpeta).
- **Git worktree por tarea**:
  - se crea en la primera etapa desde la rama base del proyecto (ajuste nuevo), con la rama `agentic/T-142`, bajo un directorio raíz por proyecto (`<proyecto>.wt\T-142`);
  - **lo comparten todas las etapas de la tarea**: QA ve lo que hizo Dev;
  - permite varias tareas del mismo proyecto en paralelo;
  - al terminar o cancelar la tarea, se borra el worktree y **se conserva la rama**: el merge lo hace el usuario;
  - se limpia la entrada de confianza de la carpeta (ADR 0004);
  - el plugin de agy va dentro del worktree, sin tocar `.git/info/exclude`.
  - El modo worktree requiere que el proyecto tenga git; si no, no se puede elegir.

**Memoria del proyecto como notas**:
- La memoria pasa de un único texto a **una lista de notas**: autor (agente o «Tú»), fecha y texto.
- En la pestaña Memoria se pueden añadir, editar y borrar, según el diseño (`06c`).
- `write_project_memory` añade una nota.
- La migración convierte el texto actual en una nota.
- Si la memoria pasa de un tamaño, la UI avisa. No hay resumen automático.

**UI** (fiel a los diseños):
- **Tablero** (`07a`, `07b`, `07c`):
  - vistas Por estado, Por etapa y Colas por agente, con filtros de proyecto y de agente;
  - en Colas, *drag & drop* para reordenar la cola de un agente.
- **Detalle de tarea** (`09a`):
  - cabecera con ID, título, estado, proyecto y agente, y las acciones;
  - a la izquierda: etapas del pipeline, descripción, resúmenes y rechazos, y las ejecuciones de la tarea;
  - en el centro, la terminal de la ejecución activa o de la última;
  - a la derecha, los eventos.
  - Reutiliza la página de ejecución de las fases 03 y 04.
- **Proyecto**:
  - pestaña **Tareas** (tabla);
  - **Pipeline** (editor visual `06b`, con flechas para reordenar y la flecha de rechazo);
  - **Memoria** (notas);
  - en **Ajustes**, el modo de workspace y la rama base;
  - los KPIs de **Resumen** con datos reales, salvo el coste.
- Diálogo **Nueva tarea**, accesible desde el proyecto y desde el tablero.
- Columna **«En cola»** en la lista de agentes.
- Estados de tarea, con sus colores, en toda la UI.

**Pruebas**:
- e2e con el CLI falso: cola de un agente en dos proyectos, pipeline con rechazo, revisión humana, worktrees, y fallos e interrupciones.
- Pruebas manuales con Claude Code y agy reales.

### Fuera
- `create_subtask`, `spawn_subagent`, `request_human`, Inbox y notificaciones (fase 06).
- Consumo y coste: las columnas de coste muestran «—» (fase 07).
- Resumen automático de la memoria.
- Merge de las ramas de los worktrees, PRs y resolución de conflictos.
- Pausar y reanudar una tarea concreta (el CLI no se puede congelar). Solo hay pausa global del scheduler.
- Programación por horario (cron) y tareas recurrentes.
- Varios pipelines por proyecto y pipelines con ramas paralelas.
- Rediseño del Dashboard con datos reales y «Asignar tarea» desde él.
- Adapters de Gemini CLI, Codex y OpenCode.
- El test intermitente de la fase 04 (anotado; se tratará aparte).

## Historias de usuario
- Como usuario, quiero dejarle a «Dev» tres tareas de dos proyectos y que las haga una detrás de otra sin que yo lance nada.
- Como usuario, quiero que cada tarea pase sola por Requisitos → Desarrollo → QA, y que si QA encuentra fallos vuelva a Desarrollo con el motivo.
- Como usuario, quiero poder revisar el resultado de una etapa antes de que siga, cuando lo marque en el pipeline.
- Como usuario, quiero ver en un tablero qué tiene cada agente en curso y en cola, y cambiar el orden arrastrando.
- Como usuario, quiero que en un proyecto con worktrees varias tareas avancen en paralelo, cada una en su rama.
- Como usuario, quiero que, si algo falla o el agente no termina bien, la tarea me espere con el motivo y pueda reintentarla, darla por terminada o cancelarla.
- Como usuario, quiero editar la memoria del proyecto nota a nota.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Cola de un agente en dos proyectos**: con concurrencia 1 y tareas de los proyectos A y B, el agente hace la de A y, al completarla, empieza sola la de B. Cada ejecución solo ve la memoria y la tarea de su proyecto | e2e con el CLI falso + prueba manual con Claude Code |
| CA2 | **Orden**: la cola respeta prioridad y posición; reordenar (API y *drag & drop*) cambia la siguiente tarea que arranca y persiste tras reiniciar | Tests del scheduler y de la API + test de componente |
| CA3 | **Concurrencia**: se respeta `max_concurrency`; en carpeta directa nunca hay dos tareas del mismo proyecto en ejecución; en worktree, sí | Tests del scheduler |
| CA4 | **Pipeline con rechazo**: una tarea recorre Requisitos → Desarrollo → QA; QA rechaza y vuelve a Desarrollo con el motivo en el contexto; a la segunda, QA aprueba y la tarea queda «Hecho». Al superar el máximo de rechazos, queda «Esperando humano» | e2e con el CLI falso + prueba manual con los CLIs reales (al menos una etapa con agy) |
| CA5 | **Revisión humana**: una etapa con «Requiere revisión» deja la tarea «En revisión»; aprobar la hace avanzar y rechazar la devuelve con el motivo | e2e + tests de la API |
| CA6 | **Worktrees**: se crea uno por tarea desde la rama base con la rama `agentic/T-n`, lo comparten sus etapas, se borra al terminar conservando la rama y se limpia la confianza de la carpeta. El plugin de agy va dentro del worktree | e2e con un repo git temporal + prueba manual |
| CA7 | **Fallos**: si una ejecución termina sin `complete_task`, falla o la interrumpe un reinicio, su tarea queda «Esperando humano» con el motivo y el agente sigue con su cola. Reintentar, dar por terminada y cancelar funcionan | e2e con el CLI falso |
| CA8 | **Memoria en notas**: la migración conserva la memoria actual; las notas se añaden, editan y borran desde la UI; las de los agentes aparecen con su autor y se inyectan en la siguiente tarea | Tests de la migración, de la API y de componentes |
| CA9 | **UI**: tablero (3 vistas, filtros y *drag & drop*), detalle de tarea, editor de pipeline, pestaña Tareas y diálogo Nueva tarea, fieles a `06b`, `06c`, `07a`, `07b`, `07c` y `09a` | Tests de componentes + capturas |
| CA10 | `check` en verde; ADR del scheduler y los workspaces; README y roadmap actualizados | Salida del `check` + revisión |

## Prerrequisitos
- Fase 04 cerrada (`v0.5`).
- Claude Code y agy instalados y con sesión iniciada; git instalado (para los worktrees).

## Riesgos y preguntas abiertas
- **Cola estricta y workspace ocupado** (decidido al aprobar la spec): si la primera tarea de la cola de un agente no puede arrancar porque su carpeta directa está ocupada, el agente **adelanta** la siguiente que sí pueda, y la tarjeta de la bloqueada lo indica («Carpeta ocupada»). Es la única causa por la que se salta el orden.
- **El modelo no llama a `complete_task`** y deja la ejecución abierta en «Esperando»: la tarea se queda «En ejecución» y ocupa un hueco del agente.
  - El usuario la resuelve con «Dar por terminada» o «Cancelar».
  - El plan valorará un aviso tras N minutos de inactividad (sin cerrarla sola).
- **Bucles de rechazo** que gastan tokens: el máximo de rechazos lo acota.
- **Worktrees en Windows**:
  - rutas largas;
  - dependencias sin instalar en el worktree (el agente debe instalarlas);
  - bloqueos de archivos al borrarlo con un proceso vivo.

  El borrado se hace cuando el CLI ya está cerrado y, si falla, se reintenta y se avisa.
- **Confianza de carpetas**: cada worktree nuevo es una carpeta que Claude y agy no conocen. La confianza automática de la fase 03 debe cubrirla, y hay que limpiar las entradas al borrar el worktree.
- **El scheduler en un backend con SQLite**: un único bucle dirigido por eventos (fin de ejecución, cambios en las colas) evita carreras al elegir la siguiente tarea. Se fijará en el plan.
- **Tamaño de la fase**: es la más grande hasta ahora. El plan la dividirá en hitos que se puedan probar por separado (tareas y colas → pipelines → worktrees → tablero).
