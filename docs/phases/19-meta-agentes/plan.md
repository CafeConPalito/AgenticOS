# Fase 19: Meta-agentes · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-25) · en desarrollo (bloques 0–9 hechos)

## Lo que ya se sabe (revisado al escribir el plan)
- **Agente** (`models/agent.py`): ya tiene `status` (`active` · `draft`) y `template`. Los borradores no reciben tareas: el scheduler y `pipelines.from_template` filtran por `AgentStatus.ACTIVE`, y el editor desactiva «Asignar tarea» y «Lanzar» y muestra «Activar». No hay revisión ni registro de cambios de la configuración.
- **Plantillas** (`services/templates.py`): cinco `AgentTemplate` en código, servidas por `GET /agent-templates` y aplicadas en `POST /agents` con `template`. El diálogo es `NewAgentDialog` + `TemplatePicker`.
- **Ejecuciones en PTY** (fases 03, 04 y 08; ADRs 0003, 0004 y 0007): el `RunManager` lanza el CLI interactivo en un PTY con su contexto y su MCP por ejecución (Claude por flags aislados, `agy` por plugin de workspace), escribe el prompt (también diferido en `agy`), sabe cuándo acaba un turno por el *hook* `Stop`, lee el consumo del transcript (fase 07), retoma sesiones con `--resume` / `--conversation` (fase 08) y no deja huérfanos. **El Arquitecto es una ejecución más de ese tipo**, sin tarea, con su propio MCP y una conversación por proceso.
- **Resolución de cuenta y límites** (`services/decider.py`): `resolve_config` elige CLI, cuenta y modelo respetando `usage_limits.blocked` y la sesión de la cuenta; se reutiliza para el Arquitecto.
- **`Run.kind`** es `String(8)` con `CHECK` (`agent` · `decision` · `describe`): `architect` no cabe, así que la migración lo amplía a 12.
- **MCP `agentic-os`** (`services/mcp_server.py`): un `MCPServer` montado en `/r/<token>/mcp`, con `RunTokens` en memoria y un `TokenGate` que resuelve *token* → ejecución. `propose_skill` y `propose_knowledge` delegan en el `RunManager` (`services/runs/manager.py`), que limita a una propuesta por ejecución, crea la propuesta y el aviso en la Inbox y registra el evento MCP. `propose_agent` copia ese camino.
- **Inbox** (`models/inbox.py`): `InboxKind` cerrado con `CHECK`; se añade `proposal`.
- **Skills**: `Skill` con `scope`/`agent_id`, `review` (propuesta pendiente), versiones con autor (`VersionAuthor`) y `SkillMode` por agente y etapa. Una skill nueva del Arquitecto es una `Skill` de nivel agente con `review = pending` y una versión con autor `architect`.
- **Conocimiento**: los documentos van **por referencia** (ruta o URL) y tienen nivel (`general` · `project` · `agent`). Los generales y del proyecto ya llegan a todos los agentes, así que «elegir documentos para el agente» significa **vincular** al nivel del agente un documento de otro nivel: se crea un `KnowledgeDoc` de nivel agente con la misma fuente, procesado al aprobar.
- **Conexiones**: `McpAssignment` (nivel agente) y `McpExclusion` (agente o etapa).
- **Pipelines** (`services/pipelines.py`): uno por proyecto. `PipelineWrite` (etapas por índice, `links`, rechazos, decisor) se valida con `check()` y `_validate()` y se guarda con `save()`, que conserva las etapas por `id`, mueve las tareas en cola y rechaza quitar enlaces en uso (`_check_links_in_use`). El Arquitecto produce un `PipelineWrite` y reutiliza todo eso.
- **Equipos** (`models/team.py`): nombre, descripción y posición; API CRUD en `api/teams.py`.
- **Eventos en vivo**: cada dominio tiene su WebSocket (`/knowledge/events`, `/git/events`). El Arquitecto tendrá el suyo por conversación.
- **Dictado**: el componente de la fase 16 se añade a un campo con la prop `dictation`.
- **CLI falso** (`backend/tests/fake_cli.py`): imita las TUIs, la reanudación y los *hooks*, y llama al MCP con el cliente oficial. Gana órdenes para el Arquitecto (`FICHA: {json}` → `update_sheet`, `RESPUESTA: texto` escrita en su transcript) para guionizar conversaciones.
- Última migración: `0020_mcp_connections`.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/architect/`; evidencias en `evidencias/`. Se usa un servidor MCP de prueba con las herramientas del Arquitecto (lectura y `update_sheet`).

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Claude interactivo como Arquitecto**: (a) Mensajes de varias líneas escritos en el PTY (pegado *bracketed* o la vía de `safe_prompt`) llegan como **un solo turno**. (b) El *hook* `Stop` marca el fin de cada turno y el transcript JSONL tiene el texto de la respuesta: ¿cuándo se escribe (por bloque, al final del turno)? ¿Se puede leer mientras crece? (c) `--tools ""` (o `--disallowedTools` con todas las propias) + `--mcp-config` + `--strict-mcp-config` + `--allowedTools mcp__architect__*` en modo interactivo: solo nuestras herramientas y ningún diálogo de permiso. (d) Cerrar el proceso por inactividad y retomarlo con `--resume`: conserva la conversación y vuelve a cargar el MCP con un *token* nuevo. (e) Latencia por turno con `sonnet` y `opus`, y memoria del proceso en reposo. (f) La configuración del usuario no cambia | (a) un turno por línea con un marcador de fin; (b) si el transcript solo se escribe al final, la respuesta aparece entera al acabar el turno (la ficha sigue en vivo por el MCP); (c) se deniegan las propias con `--disallowedTools` y el modo `ask` sin preaprobaciones |
| S2 | **`agy` interactivo como Arquitecto**: lo mismo que S1 con el plugin de workspace en una carpeta propia: (a) varias líneas, (b) `Stop` y lectura de la respuesta del transcript de `agy`, (c) cómo limitar sus herramientas propias (que no edite ficheros ni ejecute comandos), (d) cerrar y retomar con `--conversation`, (e) latencia y memoria | (c) sin forma de limitar sus herramientas: el Arquitecto solo con Claude en esta fase, con aviso en Ajustes |
| S3 | **Calidad**: diez conversaciones de prueba (Redactor, Comercial, QA estricto, «mejora este agente», equipo de contenidos con pipeline de 3 etapas y una rama, equipo de desarrollo back/front con unión) con las instrucciones base del borrador, midiendo: preguntas antes de proponer, campos inventados, fichas válidas a la primera, pipelines válidos a la primera, turnos y coste por conversación | Ajustar instrucciones base, ejemplos y descripciones de herramientas; si el coste por conversación pasa de ~0,50 $ con `sonnet`, se recorta el catálogo devuelto por las herramientas |
| S4 | **Tamaño de las respuestas de herramientas**: con 200 skills, 300 documentos y 50 conexiones, ¿cuánto ocupan `list_*` y `search_*`? ¿Basta con buscar por texto o hace falta la búsqueda semántica de las fases 14 y 17? | Búsqueda semántica con los índices existentes y listas paginadas |

## Resultados de los spikes (bloque 0, 2026-10-25)
Evidencias en [`evidencias/s1-s4-arquitecto.md`](evidencias/s1-s4-arquitecto.md); scripts en `spikes/architect/`. Ninguno cambia la spec.

- **S1 · Claude**: ✅ en todo.
  - Un mensaje de varias líneas pegado (*bracketed paste*) es un solo turno.
  - Un `Stop` por turno, y el transcript crece bloque a bloque durante el turno.
  - Con `--tools ""` y `--allowedTools mcp__architect__*` solo usa nuestras herramientas, sin diálogos.
  - `--resume` conserva la conversación y conecta al MCP nuevo.
  - Turnos de 2–11 s (Sonnet y Opus), arranque ~13–16 s, **~285 MB** por proceso; la configuración del usuario no cambia.
- **S2 · `agy`**: ✅ con dos condiciones.
  - Necesita el paso **`/mcp`** antes del primer mensaje y tras retomar; sin él no ve el MCP en toda la sesión.
  - Sus herramientas propias se bloquean con un *hook* **`PreToolUse` que devuelve `deny`** para todo lo que no sea `call_mcp_tool` al servidor del Arquitecto.
  - Varias líneas, `Stop`, transcript (`transcript_full.jsonl`, entradas `PLANNER_RESPONSE`) y `--conversation` funcionan.
  - Turnos de 10–22 s, **~250 MB** por proceso.
  - ⚠️ Añade cada carpeta nueva a sus carpetas de confianza.
- **S3 · calidad (Sonnet)**: diez de diez fichas válidas y **ninguna referencia inventada**.
  - Pregunta en las peticiones vagas (como mucho tres preguntas) y rellena desde el primer turno.
  - Sugiere Notion en vez de inventarlo y descarta gpt-5.
  - Reutiliza agentes y equipos existentes; los pipelines salen válidos, y un ciclo intermedio se corrigió solo con el aviso de la herramienta.
  - Coste **0,25 $ de media** por conversación (0,11–0,58 $).
  - Dos fallos de contrato:
    - la cuenta por `id` frente a nombre;
    - en modo «un agente» llamó a `set_pipeline` y metió el agente en un pipeline.
- **S4 · tamaños**: listar 200 skills o 300 documentos cuesta ~10 000 tokens cada vez; una búsqueda de 8 resultados, ~300.

### Cambios al diseño por los spikes
1. **Claude** (§4): argv del Arquitecto = el del adapter con `--tools ""`, `--mcp-config` (solo el servidor `architect`), `--strict-mcp-config`, `--allowedTools mcp__architect__*` y las instrucciones en `--append-system-prompt-file`. Los mensajes se escriben con **pegado *bracketed*** + Enter (también los de una línea, por uniformidad). La respuesta se lee de los bloques `text` de las entradas `assistant` del transcript.
2. **`agy`** (§4):
   - se lanza con `--dangerously-skip-permissions` y un plugin `architect` cuyo `hooks.json` lleva un **`PreToolUse` guardián**: el *hook* de la app devuelve `deny` salvo para `call_mcp_tool` con `ServerName` `architect_architect`;
   - antes del primer mensaje y tras retomar se hace el paso **`/mcp`** que ya tiene `RunSession`;
   - la respuesta se lee de las entradas `PLANNER_RESPONSE` de `transcript_full.jsonl`.
3. **Carpetas de trabajo**: en lugar de una por conversación (que `agy` añadiría una a una a su confianza), **una por proceso vivo**: `datadir/architect/slot-1` y `slot-2` (`architect.max_live` = 2), reutilizadas. El plugin y `mcp.json` se reescriben en cada arranque con el *token* nuevo.
4. **Herramientas por modo**: en `agent` e `improve_agent` solo las de un agente (`update_sheet`, `draft_skill`, `suggest_connection`, `request_unlock` y las de lectura salvo pipelines); `update_team`, `use_existing_agent` y `set_pipeline` solo en `team`, `improve_team` e `improve_pipeline`.
5. **Cuentas**: `list_clis` devuelve cada cuenta con `id` y `label`, y el validador acepta el `id` (y el nombre visible como alias, normalizado al `id`).
6. **Catálogos**: `search_skills` y `search_knowledge_docs` devuelven **8 resultados** con la búsqueda híbrida existente (fases 17 y 14); `list_connections` va sin herramientas y `get_connection` da las de una. Nada lista catálogos enteros.
7. **Avisos en cada respuesta**: las herramientas de la ficha devuelven siempre los problemas pendientes y lo rechazado con el motivo; en S3 eso bastó para que el modelo se corrigiera solo.
8. **Modelo por defecto**: **Sonnet** (Claude) y `gemini-3.8-flash-high` (`agy`); Opus no mejora lo bastante para su coste.
9. **Instrucciones base**: las de `spikes/architect/instructions.md` + `modes.py` pasan a `services/architect/prompts.py` como punto de partida.

### Cambios al diseño durante el desarrollo
10. **Herramientas de las conexiones (bloque 3)**: la spec (apartado B) decía que el Arquitecto elige las conexiones «y sus herramientas permitidas». En la fase 18 las herramientas permitidas son de la conexión y valen para todos sus agentes, no por agente; cambiarlas desde una ficha afectaría a otros agentes. El Arquitecto asigna conexiones **sin** limitar herramientas; si lo intenta, la herramienta se lo rechaza explicando por qué, y puede decírselo al usuario. Limitar herramientas por agente queda para una fase futura.
11. **Skills de la ficha**: como en el editor, solo se guardan los modos `always` y `never`; `auto` es el comportamiento por defecto de toda skill visible.

## Diseño ([ADR 0026](../../adr/0026-meta-agents.md), nuevo)

### 1. Modelo de datos (migración `0021_architect`)
- **`ArchitectConversation`** (`architect_conversations`): `id`, `workspace_id`, `mode` (`agent` · `improve_agent` · `team` · `improve_team` · `improve_pipeline`), `title`, `status` (`open` · `proposed` · `applied` · `discarded`), destino (`agent_id`, `team_id`, `project_id`, según el modo), `cli`, `account_id`, `model`, `cli_session_id` (para retomar), `run_id` (la ejecución `architect` viva o la última), `sheet` (JSON, ver §2), `locked_fields` (JSON), `proposal_id`, fechas.
- **`ArchitectMessage`** (`architect_messages`): `conversation_id`, `role` (`user` · `architect` · `system`), `text`, `tool_events` (JSON: qué campos cambió en ese turno), `created_at`. Es lo que pinta el chat; el CLI tiene su propio transcript.
- **`Proposal`** (`proposals`): una propuesta pendiente de aprobación, venga del Arquitecto o de un agente.
  - `kind`: `new_agent` · `agent_changes` · `team` (compuesta: equipo + agentes + pipeline) · `team_changes` · `pipeline_changes`;
  - `origin`: `architect` · `agent`; `conversation_id`; `source_agent_id`, `source_run_id`, `source_task_id` y `reason` (para `propose_agent`);
  - `payload` (JSON): la ficha propuesta y, en las de cambios, el **valor de partida de cada campo** (para detectar conflictos);
  - `status`: `pending` · `applied` · `partial` · `rejected`; `decided_at`, `applied_fields` (JSON).
- **`Agent`**: `can_propose_agents` (bool, `false`), `proposal_id` (el borrador viene de una propuesta) y `archived_at` (rechazar puede archivar en vez de borrar; los archivados no salen en las listas).
- **`AgentChange`** (`agent_changes`): historial de la configuración del agente. `agent_id`, `source` (`user` · `architect` · `import`), `proposal_id`, `conversation_id`, `fields` (JSON antes/después, sin instrucciones enteras: diff), `created_at`. Lo escriben las propuestas aplicadas; la edición manual se registra solo como «editado a mano» con la lista de campos (sin diff), para no inflar la tabla.
- **`AgentTemplateRow`** (`agent_templates`): plantillas del usuario. `id`, `workspace_id`, `name`, `description`, `color`, `payload` (el formato de exportación de §6), fechas. Las fijas siguen en código.
- `Run.kind` pasa a `String(12)` y admite `architect`. `InboxKind` admite `proposal`.

### 2. La ficha (`services/architect/sheet.py`)
- Modelos Pydantic: **`AgentSheet`** (identidad, instrucciones, ejecución, `skills` [existentes con modo + nuevas con nombre, descripción y cuerpo], `knowledge` [ids de documentos a vincular], `connections` [ids + herramientas permitidas], `template_id`), **`TeamSheet`** (equipo nuevo o `team_id`, lista de agentes: `AgentSheet` nuevos o `agent_id` existentes con una clave local `ref`) y **`PipelineSheet`** (un `PipelineWrite` cuyas etapas apuntan a `ref` o a `agent_id`, más los ajustes por etapa de skills y conexiones).
- **Validación** (`validate(db, sheet) → list[Issue]`), la misma para el Arquitecto, `propose_agent` y la importación:
  - CLI instalado, cuenta del mismo CLI, modelo de la lista del CLI (`services/clis.py`), skills, documentos y conexiones existentes y activos, equipo existente;
  - el pipeline pasa por `pipelines.check()` y las reglas de `_validate()` con las `ref` resueltas;
  - cada problema dice el campo y el motivo con palabras (`Issue(field, code, message)`).
- **Completitud**: porcentaje de campos rellenos (para la barra del diseño) y `ready` (nombre, rol, CLI e instrucciones; en un equipo, todos sus agentes nuevos `ready` y el pipeline válido).

### 3. Propuestas (`services/proposals.py`)
- **Crear**: desde una conversación («Crear borrador» / «Crear propuesta») o desde `propose_agent`. Para `new_agent` y `team`, los agentes nuevos se crean ya como **`Agent` en borrador** (para que se vean, se editen y aparezcan con su chip), con `proposal_id`; las skills nuevas se crean como skills de nivel agente con `review = pending`; los documentos y conexiones se guardan en el `payload` y se aplican al aprobar. Se crea el aviso de la Inbox.
- **Aprobar** (`approve(db, proposal, fields | None, choices)`) en **una transacción**:
  - `new_agent`: activa el agente, acepta sus skills propuestas (salvo las desmarcadas), vincula documentos y asigna conexiones;
  - `team`: crea o actualiza el equipo, aprueba los agentes marcados, comprueba que ninguna etapa use uno desmarcado y guarda el pipeline con `pipelines.save()`;
  - `*_changes`: aplica solo los campos elegidos; un campo cuyo valor actual ya no es el de partida es **conflicto** y exige elegir (`choices`: propuesta o actual). Para el pipeline, el conflicto es de todo el pipeline (cambió desde la propuesta).
  - Escribe `AgentChange`, marca la propuesta y la conversación y resuelve el aviso. Si algo falla, *rollback* y error con palabras.
- **Rechazar**: borra o archiva los agentes nuevos, descarta sus skills propuestas, deja la conversación en `discarded`.
- Una propuesta de cambios **no** toca nada hasta aprobarla, así que el agente sigue trabajando; las ejecuciones ya leen la configuración al lanzarse (sin cambios en el `RunManager`).

### 4. El Arquitecto en marcha (`services/architect/`)
- **`config.py`**: Ajustes › Arquitecto en `app_state` (CLI, cuenta, modelo, instrucciones base editables). Por defecto: Claude si está, con `opus` (o `sonnet` según S3); `resolve_config` como el del decisor (límites y sesión de la cuenta).
- **`prompts.py`**: instrucciones base por modo, con las reglas («pregunta antes de suponer, como mucho dos o tres preguntas por turno», «usa solo lo que devuelvan las herramientas», «explica las decisiones importantes», «no cambies campos fijados») y ejemplos sacados de las plantillas fijas. Cada turno añade un bloque de estado: ficha actual, campos fijados y problemas de validación pendientes.
- **Herramientas MCP** (`tools.py`, un segundo `MCPServer` montado en `/a/<token>/mcp`, con *tokens* por conversación como `RunTokens`):
  - lectura: `list_clis` (CLIs, cuentas y modelos disponibles), `list_teams`, `list_agents` / `get_agent`, `search_skills`, `search_knowledge_docs`, `list_connections`, `search_connection_registry` (para **sugerir**), `list_templates` / `get_template`, `list_projects` / `get_pipeline`;
  - ficha: `update_sheet(patch)` (rechaza campos fijados con «campo fijado por el usuario»), `request_unlock(field, reason)` (un botón en el chat), `draft_skill(name, description, body)`, `set_pipeline(pipeline)`, `suggest_connection(registry_ref, reason)`;
  - todas devuelven los problemas de validación que queden.
- **Un CLI interactivo por conversación** (`session.py`, `ArchitectSessions`, sobre el `RunManager`):
  - al enviar el primer mensaje se lanza una ejecución de tipo **`architect`** (sin tarea ni proyecto) en un PTY, con el adapter del CLI: carpeta de trabajo propia en `datadir/architect/<conversación>`, MCP del Arquitecto en lugar de `agentic-os`, instrucciones base como *system prompt* (Claude) o reglas del plugin (`agy`) y sin herramientas propias del CLI (según S1/S2);
  - **cada mensaje se escribe en ese mismo proceso**; un turno a la vez (los mensajes que lleguen durante un turno esperan); «Detener» interrumpe el turno (Esc, como «tomar el control» de la fase 03) sin cerrar el CLI;
  - el **fin del turno** llega por el *hook* `Stop`; el texto de la respuesta se lee del **transcript** del CLI (por bloques según S1) y se guarda como `ArchitectMessage`;
  - eventos por WebSocket: `message` (bloque de texto del Arquitecto), `sheet` (una herramienta cambió la ficha, en el momento), `turn_done`, `state` (arrancando, pensando, en reposo, dormida), `error`;
  - **inactividad**: tras `architect.idle_minutes` (15 por defecto) sin mensajes, el proceso se cierra de forma ordenada y la conversación queda «dormida»; el siguiente mensaje la **retoma** con `--resume` / `--conversation` (fase 08) y un *token* MCP nuevo. Al cerrar la app pasa lo mismo;
  - **empezar de cero**: «Nueva conversación» abre otra con un CLI nuevo; «Reiniciar» cierra el CLI de esta y arranca uno limpio, conservando la ficha (o vaciándola si se pide) pero no el contexto;
  - como mucho `architect.max_live` (2 por defecto) procesos vivos a la vez; al abrir otro, se duerme el más antiguo en reposo;
  - el **consumo** de la ejecución `architect` se lee del transcript como el de cualquier agente (fase 07) y aparece en la pantalla; **antes de cada mensaje** se comprueban el límite diario y la sesión de la cuenta, y si no se puede seguir se dice con palabras sin escribir en el CLI;
  - **«Ver terminal»** abre el terminal real de la ejecución (solo lectura por defecto, con «tomar el control» de la fase 03).
- **Edición manual**: `PATCH` de la ficha desde la UI fija esos campos (`locked_fields`); el usuario puede soltarlos con el candado o aceptando un `request_unlock`.

### 5. `propose_agent` (MCP `agentic-os`)
- Herramienta nueva solo para ejecuciones cuyo agente tenga `can_propose_agents`; argumentos: ficha (`AgentSheet` sin skills nuevas) y `reason`.
- `RunManager.propose_agent`: una por ejecución, valida con §2 (devuelve los problemas al agente para que corrija), avisa si ya hay un agente o borrador con el mismo rol y crea la propuesta `new_agent` con origen `agent`.
- Las plantillas fijas: «Analista» y «Desarrollador» con `can_propose_agents = true`.

### 6. Plantillas y exportación (`services/agent_io.py`)
- **Formato** `agentic-os.agent` versión 1 (JSON): campos del agente sin ids locales, cuenta ni equipo; skills de nivel agente **embebidas** (SKILL.md y ficheros); skills generales y de proyecto, conexiones y documentos **por nombre** (conexiones sin secretos; documentos con su fuente).
- **Guardar como plantilla** = exportar a `agent_templates`. **Crear desde plantilla** amplía `POST /agents` (`template` acepta los ids del usuario).
- **Importar**: `POST /agents/import/preview` devuelve qué se crea y qué falta (skills, conexiones, documentos, CLI no instalado); `POST /agents/import` aplica con las elecciones (omitir o sustituir). Importar un agente lo deja en borrador.

### 7. API (`api/architect.py`, `api/proposals.py`, `api/agent_templates.py`)
- Conversaciones: `GET/POST /architect/conversations`, `GET/DELETE /architect/conversations/{id}`, `POST …/messages` (lo escribe en el CLI, arrancándolo o retomándolo si hace falta), `POST …/interrupt`, `POST …/reset`, `POST …/sleep`, `PATCH …/sheet` (edición manual), `POST …/unlock`, `POST …/propose`, `WS /architect/conversations/{id}/events`.
- Propuestas: `GET /proposals/{id}` (con el diff por campo y los conflictos), `POST /proposals/{id}/approve` (campos y elecciones), `POST /proposals/{id}/reject` (`archive` o `delete`).
- Plantillas e importación: `GET/POST/PATCH/DELETE /agent-templates`, `POST /agents/{id}/save-as-template`, `GET /agents/{id}/export`, `POST /agents/import/preview`, `POST /agents/import`.
- Ajustes: `GET/PUT /settings/architect`.

### 8. Frontend
- **`pages/architect/`**: `ArchitectPage` (rejilla del diseño §11), `ArchitectChat` (mensajes por bloques con indicador de «pensando», estado del CLI —arrancando, en reposo, dormido—, composer con dictado, «Detener», «Reiniciar», «Ver terminal», botones de `request_unlock` y sugerencias de conexiones), `SheetPanel` con pestañas **Ficha** (un agente) o **Equipo · Agentes · Pipeline** (modo equipo), campos con *skeleton* discontinuo, candado por campo y resalte breve al cambiar; `PipelinePreview` reutiliza el lienzo del editor de la fase 13 en solo lectura. Lista de conversaciones en un panel lateral.
- **Revisión de propuestas** (`components/proposals/`): `DraftBanner` (banner violeta del diseño), `ProposalReview` con diff por campo (instrucciones con diff de texto), casillas por campo, conflictos y, en equipos, la lista de agentes con casilla y el pipeline con los cambios coloreados.
- **Puntos de entrada**: «Crear con el Arquitecto» en Agentes, Inicio y la paleta; «Mejorar con el Arquitecto» en el editor del agente, en el equipo y en el editor de pipeline; «Abrir con el Arquitecto» en un borrador de `propose_agent`.
- **Agentes**: chip «Propuesto por el Arquitecto» / «Propuesto por <agente>», pestaña **Historial** con una sección de cambios de configuración (`AgentChange`), permiso «Puede proponer agentes» en Ejecución, menú «Guardar como plantilla» y «Exportar», botón «Importar» en la lista.
- **Plantillas**: `TemplatePicker` con las del usuario; pestaña «Plantillas» en Agentes para editarlas, duplicarlas y borrarlas.
- **Inbox**: tipo `proposal` con enlace a la revisión. **Ajustes › Arquitecto**.
- Textos en `i18n/es.json` (`architect.*`, `proposals.*`, `agentTemplates.*`).

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0021_architect.py` | nuevo |
| `backend/src/agentic_os/models/architect.py`, `models/proposal.py` | nuevos |
| `backend/src/agentic_os/models/agent.py`, `models/run.py`, `models/inbox.py`, `models/__init__.py` | modificados |
| `backend/src/agentic_os/services/architect/` (`config.py`, `prompts.py`, `sheet.py`, `tools.py`, `session.py`) | nuevos |
| `backend/src/agentic_os/services/proposals.py`, `services/agent_io.py` | nuevos |
| `backend/src/agentic_os/services/mcp_server.py`, `services/runs/manager.py`, `services/templates.py`, `services/inbox.py` | modificados |
| `backend/src/agentic_os/api/architect.py`, `api/proposals.py`, `api/agent_templates.py`, `schemas/architect.py`, `schemas/proposals.py` | nuevos |
| `backend/src/agentic_os/api/agents.py`, `schemas/agent.py`, `app.py` | modificados |
| `backend/tests/fake_cli.py` | órdenes del Arquitecto (`FICHA:`, `RESPUESTA:`) para guionizar conversaciones |
| `frontend/src/pages/architect/`, `frontend/src/components/proposals/`, `frontend/src/api/architect.ts`, `api/proposals.ts` | nuevos |
| `frontend/src/pages/agents/*`, `pages/projects/` (editor de pipeline), `pages/home/`, `pages/InboxPage.tsx`, `pages/settings/`, `components/agentic/shell` (paleta) | modificados |
| `frontend/src/i18n/es.json` | modificado |
| `docs/adr/0026-meta-agents.md` | nuevo |
| `spikes/architect/` | nuevo |

## Tareas (en orden)
Bloques pequeños con commits y tests; cada uno deja la app funcionando.

0. [x] **Spikes S1–S4** y cambios al diseño que salgan (⛔ OK del usuario si cambian algo de la spec).
1. [x] **Modelo de datos**: migración `0021_architect`, modelos y `CHECK`s; tests de migración.
2. [x] **Ficha y validación** (§2) con tests de cada regla, sin LLM.
3. [x] **Propuestas** (§3): crear, aprobar (total y parcial, conflictos, transacción) y rechazar, para `new_agent` y `agent_changes`; `AgentChange`; Inbox.
4. [x] **Arquitecto en marcha** (§4): configuración, herramientas MCP, ejecución `architect` en PTY con un CLI por conversación, mensajes escritos en el proceso, fin de turno por `Stop`, respuesta desde el transcript, interrumpir, dormir y retomar, reiniciar, consumo y límites; órdenes del Arquitecto en el CLI falso.
5. [x] **API y WebSocket** del Arquitecto y de las propuestas (§7).
6. [x] **UI del Arquitecto de un agente**: pantalla, ficha en vivo, candados, conversaciones, banner de borrador, revisión, Inbox, Ajustes › Arquitecto, dictado. *(A–C, E)*
7. [x] **Plantillas y exportar/importar** (§6) con su UI. *(D)*
8. [x] **Mejorar agentes activos**: modo `improve_agent`, revisión con diff y aplicación parcial, Historial. *(F)*
9. [x] **`propose_agent`** (§5) y su permiso. *(G)*
10. [ ] **Equipos y pipelines**: `TeamSheet`/`PipelineSheet`, propuesta `team` y `*_changes` de equipo y pipeline, pestañas Equipo · Agentes · Pipeline, `PipelinePreview`, entradas desde equipo y editor de pipeline. *(H)*
11. [ ] **e2e** con el CLI falso (CA1, CA15) y con el binario empaquetado (CA11); prueba manual con `claude` (y `agy` si S2 lo permite).
12. [ ] **Cierre**: `/code-review`, ADR 0026, README, validación y roadmap.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_architect_e2e.py`: conversación con el CLI falso → borrador → aprobar → tarea completada | CA1 |
| `test_architect_session.py`: un solo proceso para varios turnos, eventos `message`/`sheet`/`turn_done`, interrumpir sin cerrar, dormir por inactividad y retomar con la conversación intacta, reiniciar con un proceso limpio, tope de procesos vivos, sin huérfanos, campos fijados y `request_unlock` | CA2, CA6 |
| `test_architect_sheet.py`: cada regla de validación (modelo, cuenta de otro CLI, skill/documento/conexión inexistentes, pipeline inválido) | CA3, CA16 |
| `test_architect_tools.py`: las herramientas solo leen o cambian la ficha de su conversación; un *token* de otra conversación da 401 | CA4 |
| `test_proposals.py`: aprobar y rechazar `new_agent` (borrador sin tareas, skills propuestas aprobadas o descartadas), Inbox | CA5, CA14 |
| `test_architect_api.py` + UI: cerrar y retomar una conversación, enlaces borrador ↔ conversación | CA6 |
| `test_architect_usage.py`: ejecución `architect` con consumo en el panel; límite alcanzado y cuenta sin sesión sin escribir en el CLI | CA7 |
| `test_agent_templates.py`: guardar como plantilla, crear desde ella con otra cuenta, las fijas no se editan | CA8 |
| `test_agent_io.py`: exportar sin secretos, importar en base limpia con faltantes omitidos o sustituidos | CA9 |
| `architect.test.tsx`: composer con dictado, ficha en vivo, candados | CA2, CA10 |
| `test_proposals_changes.py`: aplicación parcial, conflictos, ejecución en marcha intacta, `AgentChange` | CA12 |
| `test_propose_agent.py` (CLI falso): con y sin permiso, segunda propuesta rechazada, ficha inválida, aviso de rol repetido | CA13 |
| `test_architect_team_e2e.py`: equipo + agentes nuevos y existentes + pipeline, «Aprobar todo» y una tarea que recorre el pipeline | CA15 |
| `test_proposals_team.py`: agente desmarcado usado por una etapa, fallo a medias sin nada aplicado | CA16 |
| `test_proposals_pipeline.py`: diff de etapas y ramas, tareas en curso conservadas, etapa con tareas activas no se quita, cambios de equipo | CA17 |
| e2e empaquetado (`scripts/e2e-packaged`) con el flujo conversación → borrador → aprobación → tarea | CA11 |

## Decisiones (ADR)
- **ADR 0026 (nuevo): meta-agentes.**
  1. El Arquitecto es **un CLI interactivo por conversación** (una ejecución `architect` en PTY que vive entre turnos, se duerme por inactividad y se retoma), con un **MCP propio** de lectura y edición de su ficha; nunca escribe fuera de ella.
  2. Todo lo que propone (el Arquitecto o un agente) es una **`Proposal`** que solo se aplica al aprobarla, en una transacción, total o parcialmente, con **conflictos por valor de partida**.
  3. Los agentes nuevos de una propuesta existen como **borradores** desde el principio (se ven y se editan); las propuestas de cambios no tocan nada hasta aplicarse.
  4. Formato de exportación `agentic-os.agent` v1, sin secretos ni ids locales; las plantillas del usuario usan ese mismo formato.
  5. Cada conversación (cada proceso del CLI) es una ejecución `architect` que cuenta en el consumo y en el límite diario, comprobado antes de cada mensaje.

## Estado (2026-10-26)
- **Hechos**: bloques 0–4. El Arquitecto funciona de punta a punta con Claude y `agy` (CLI falso en ConPTY):
  - un CLI por conversación, mensajes pegados enteros, respuesta leída del transcript por bloques, ficha editada por las herramientas MCP (`/a/agent/mcp` y `/a/team/mcp`), dormir y retomar con la misma sesión, reiniciar con una limpia, interrumpir sin cerrar, límite diario comprobado antes de cada mensaje y consumo como ejecución `architect`;
  - el guardián de `agy` deniega todo lo que no sea su MCP, y los *tokens* de agente y de Arquitecto no abren el servidor del otro.
- **Hallazgo del bloque 4**: con una lectura de consola como la de `msvcrt`, ConPTY quita las marcas del pegado y entrega los saltos pegados como `\n` y el Enter como `\r`; los CLIs reales sí ven el pegado completo (spikes S1–S2). El CLI falso distingue `\n` de `\r` en modo Arquitecto.
- **Bloque 5 hecho**: API y WebSocket de conversaciones y propuestas, ajustes del Arquitecto; borrar un borrador rechaza su propuesta y no se activa a mano si tiene una pendiente.
- **Bloque 6 hecho**: pantalla «Crear con el Arquitecto» (`/agentes/arquitecto`: lista de conversaciones y conversación con chat y ficha en vivo), respuestas por bloques y estado del CLI por WebSocket, edición a mano con candado, «Ver terminal», reiniciar, detener, dictado en el composer, banner del borrador con aprobar (eligiendo sus skills) y rechazar (borrar o archivar), chip en la lista, aviso de la Inbox con «Revisar», accesos desde Agentes, Inicio y la paleta, y Ajustes › Arquitecto.
- **Bloque 7 hecho**: formato `agentic-os.agent` v1 (sin secretos ni ids locales; skills propias embebidas, el resto por nombre), «Guardar como plantilla» y «Exportar» en el editor, «Mis plantillas» (renombrar, duplicar, borrar; las fijas no se tocan), las plantillas propias en el selector de nuevo agente (crear desde una trae sus skills, conexiones y documentos, con otra cuenta si se quiere) e «Importar» con vista previa de lo que falta, que entra como borrador.
- **Bloque 8 hecho**: «Mejorar con el Arquitecto» en el editor de un agente activo; la ficha marca qué cambia respecto al agente; aviso «Cambios propuestos» con revisión campo a campo (instrucciones como diff, conflictos con elección del valor que se queda, skills nuevas), aplicación parcial; historial de configuración en la pestaña Historial (`GET /agents/{id}/config-history`) y propuestas pendientes de un agente (`GET /proposals?target_agent_id=&status=`).
- **Bloque 9 hecho**: `propose_agent` en el MCP `agentic-os` (solo con «Puede proponer agentes»: sin él la herramienta se quita del CLI —`--disallowedTools` en Claude, `disabledTools` en `agy`— y el backend la rechaza), una por ejecución, la misma validación que la ficha, sin roles repetidos y sin poder dar permisos (`can_propose_agents`, cuenta, equipo ni skills nuevas); borrador con origen y motivo, aviso en la Inbox con el agente que lo propuso, chip «Propuesto por <agente>», «Seguir con el Arquitecto» (la nueva propuesta sustituye a la anterior y su borrador), permiso en la pestaña Ejecución y activado en las plantillas Analista y Desarrollador; orden `PROPONE_AGENTE` en el CLI falso.
- **Siguiente**: bloque 10 (equipos y pipelines).
