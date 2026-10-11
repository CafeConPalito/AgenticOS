# Fase 04: Adapters y MCP · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado

## Diseño

### Visión general
```
RunManager.launch(agent, project, prompt)
  ├─ token = secrets.token_urlsafe(32)          registro en memoria token → run_id (muere con la ejecución)
  ├─ ContextBuilder → <data_dir>\runs\<id>\instructions.md
  ├─ adapter = adapters.for_cli(agent.cli)
  │    ├─ ClaudeAdapter: settings.json (hooks) + mcp.json + flags de permisos → argv
  │    └─ AgyAdapter: plugin .agents\plugins\agentic-os\ en el proyecto → argv sin -i
  └─ RunSession(…, adapter)                      la fase 03, más hooks, eventos y cierre al completar

Backend (mismo puerto):
  /r/<token>/mcp            servidor MCP (SDK oficial `mcp`, Streamable HTTP) tras un TokenGate
  /r/<token>/hook/<event>   recibe los hooks (cuerpo JSON del CLI), responde siempre 204
```
El backend conoce su URL pública (`http://127.0.0.1:<puerto real>`): `__main__` la guarda en `app.state` tras abrir el socket, porque en la app empaquetada el puerto es libre.

### Servidor MCP `agentic-os`
- **Librería**: el SDK oficial `mcp` (2.x, el mismo del spike), `MCPServer(...).streamable_http_app()` montado en FastAPI. Su `session_manager` se arranca en el lifespan del backend.
- **TokenGate** (ASGI, reutilizado del spike):
  - el token llega en la ruta `/r/<token>/…` o en `Authorization: Bearer`;
  - un token desconocido o de una ejecución terminada recibe **401**;
  - el `run_id` resuelto viaja a las herramientas en una cabecera interna que el gate siempre sobrescribe, así que el cliente no la puede falsificar.
- **Herramientas** (descripciones en castellano, porque las lee el modelo):

| Herramienta | Efecto |
|---|---|
| `get_context()` | Devuelve las instrucciones, el prompt y la memoria del proyecto de la ejecución |
| `report_status(message)` | Guarda `last_status` y un evento; se ve en vivo en la UI |
| `complete_task(summary)` | Guarda `summary` y un evento, y marca la ejecución «pendiente de cerrar»: en el siguiente hook de fin de turno (o a los 60 s si no llega) Agentic OS para el CLI de forma ordenada y la ejecución termina **`completed`** |
| `write_project_memory(note)` | Añade a `project.memory` un bloque `### <fecha> · <agente>` + nota (límite de tamaño) y guarda un evento |

- La primera petición con el token de una ejecución marca **«MCP conectado»**. agy lo necesita para enviar su prompt.

### Hooks
- **Transporte**: un `hook.cmd` por ejecución en `<data_dir>\runs\<id>\`, referenciado por su **ruta corta 8.3** (sin espacios ni comillas, como exige agy):
  ```bat
  @curl.exe -s -m 3 -o NUL -X POST -H "Content-Type: application/json" --data-binary @- http://127.0.0.1:<port>/r/<token>/hook/%1
  @exit /b 0
  ```
  - `curl.exe` viene con Windows 10/11 y arranca en milisegundos (el ejecutable empaquetado tardaría segundos en cada hook).
  - `exit /b 0` **siempre**: un hook que falla bloquea la herramienta en agy.
- **Eventos usados**:

| CLI | Eventos | Uso |
|---|---|---|
| Claude | `UserPromptSubmit` | actividad `busy` |
| Claude | `Stop` | actividad `idle` y disparo del cierre tras `complete_task` |
| Claude | `SessionStart` / `SessionEnd` | solo evento |
| agy | `PreInvocation` | `busy`; señal de que el prompt escrito ha llegado |
| agy | `Stop` | `idle` y cierre |
| agy | `conversationId` (cualquier evento) | → `cli_session_id` |

- **Actividad**: si llega algún hook, mandan los hooks; la pantalla solo cubre el arranque y el caso de que no lleguen.

### Adapters (`services/adapters/`)
Interfaz `CliAdapter`:
- `prepare(run, agent, project, ctx) -> LaunchSpec`: escribe archivos y construye el argv;
- `after_mcp_connected(session)`: en agy escribe el prompt;
- `cleanup(run)`;
- `recover(cwd)`.

Sustituye a `launcher.py` (se conservan `clean_env`, `resolve_executable` y `safe_prompt`).

**ClaudeAdapter**:
```
claude " <prompt>" --session-id <uuid> --setting-sources project,local
       --settings <run>\settings.json --mcp-config <run>\mcp.json --strict-mcp-config
       --append-system-prompt-file <run>\instructions.md
       --permission-mode <manual|acceptEdits|bypassPermissions>
       --allowedTools mcp__agentic-os__* [herramientas del agente] [--model m]
```
El prompt va primero (ADR 0004). `mcp.json` usa la cabecera `Authorization: Bearer`.

**AgyAdapter**:
- Escribe en `<proyecto>\.agents\plugins\agentic-os\`:
  - `plugin.json` con `{"name": "agentic-os", "agenticOsRun": "<id>"}` (marca para la limpieza);
  - `mcp_config.json` con la URL `/r/<token>/mcp`;
  - `hooks.json` con el formato verificado en el spike, apuntando a `hook.cmd` por ruta corta;
  - `rules\AGENTS.md` con las instrucciones.
- Añade `.agents/plugins/agentic-os/` a `.git/info/exclude` si el proyecto es un repo (una sola vez, sin duplicar la línea).
- argv: `agy [--model m] [--dangerously-skip-permissions | --mode accept-edits]`, **sin `-i`**.
- Tras «MCP conectado», escribe el prompt y Enter, y verifica que llega un `PreInvocation`. Si no llega en 10 s, lo reintenta una vez. Si el MCP no conecta en 45 s, envía el prompt igualmente y lo registra como evento `mcp_timeout`.
- **Una ejecución de agy por carpeta**: si ya hay una viva en esa ruta, devuelve 409 `agy_folder_busy`.
- `cleanup` borra el plugin solo si su `agenticOsRun` coincide. `recover()` borra los plugins huérfanos de las ejecuciones marcadas `interrupted`.

**Permisos**:

| `permission_mode` | Claude | agy |
|---|---|---|
| `autonomous` | `bypassPermissions` | `--dangerously-skip-permissions` |
| `restricted` | `acceptEdits` + `--allowedTools` según `allowed_tools` | `--mode accept-edits` |
| `ask` | `manual`, solo con `mcp__agentic-os__*` preaprobado | modo por defecto |

Traducción de `allowed_tools` en Claude:
- `read` → `Read Glob Grep`;
- `edit` → `Edit Write NotebookEdit`;
- `terminal` → `Bash PowerShell`;
- `git` → `Bash(git:*) PowerShell(git *)`;
- `web` → `WebFetch WebSearch`;
- `mcp_agentic_os` → siempre incluido;
- `browser` → sin equivalente, se ignora (queda documentado).

En `autonomous` la lista no se aplica: el spike demostró que denegar no es una barrera (ADR 0004).

**Aprobaciones MCP en agy: resultado de la tarea 1 → plan B.** agy tiene reglas `mcp(<servidor>/<herramienta>)` en `permissions.allow`, pero en las pruebas con agy real (headless, modo preguntar) **ningún archivo de proyecto ni de plugin las aplica**. Se probaron:
- `.agents/settings.json`;
- `.agents/config.json`;
- `.gemini/settings.json`;
- `settings.json` dentro del plugin;
- `plugin.json` con `permissions`.

En todos los casos la llamada sale en `denied_actions` y la configuración global no cambia. Evidencia: `docs/phases/01-spike-clis/evidencias/p04-agy-preapproval.md`.

Se aplica el plan B:
- el ticker reconoce el diálogo «Allow calling this tool?» de una herramienta `agentic-os_agentic-os/<herramienta>`;
- elige la opción 2, «Yes, and always allow tool … in this conversation»: un diálogo como mucho por herramienta y ejecución;
- cualquier otro diálogo de permiso queda para el usuario.

El transporte de hooks también se verificó: `hook.cmd` por ruta corta + `curl` recibe `PreInvocation`/`PostInvocation`/`Stop` con `conversationId` (`p04-agy-hook-cmd.md`). En headless con una herramienta denegada no hay `Stop`, porque el turno termina antes.

Texto original de la duda: la **tarea 1** comprueba con agy real si existe una regla persistente a nivel de workspace o plugin para preaprobar herramientas MCP.
- **Si existe**, el plugin la incluye.
- **Si no**, plan B: `ScreenState` reconoce el diálogo «Requesting permission for» de una herramienta de `agentic-os` y el ticker elige «Yes, and always allow in this conversation», como ya hace con el diálogo de confianza. Solo para nuestras herramientas.

### Context builder (`services/context.py`)
`instructions.md`, en castellano:
```
# Tu rol: <nombre> · <rol>
<instrucciones del agente>

# Proyecto: <nombre> (<carpeta>)
## Memoria del proyecto
<memoria o «(vacía)»>

# Cómo trabajar con Agentic OS
- Usa la herramienta report_status para contar en qué estás cuando empieces algo relevante.
- Cuando termines la tarea, llama a complete_task con un resumen de lo hecho y lo pendiente.
- Si descubres algo útil para futuras tareas en este proyecto, guárdalo con write_project_memory.
```
La memoria se recorta si supera un límite, quedándose con lo más reciente. Plantilla en código, con tests.

### Modelo y API
**Migración `0003`**:
- `runs`:
  - estado `completed` en el `CHECK` del estado;
  - columnas `summary` (texto, nullable), `last_status` (texto, nullable) y `mcp_connected_at`.
- tabla nueva **`run_events`**:
  - `id`, `run_id` (FK con `CASCADE`), `at`;
  - `kind` (`mcp` / `hook` / `system`);
  - `name` (`report_status`, `Stop`…);
  - `detail` (texto corto).

  Los hooks de herramientas (`PreToolUse` / `PostToolUse`) no se guardan, para no inflar la tabla.

**API**:
- `GET /api/runs/{id}/events`;
- `RunRead` gana `summary` y `last_status`;
- el WebSocket emite `{"type":"event", ...}` en vivo;
- `state` ya lleva la actividad;
- `ACTIVE_STATUSES` no cambia (`completed` es terminal).

### Frontend
- `api/types.ts`: estado `completed`, `summary`, `last_status`, `RunEvent`. `api/runs.ts`: `useRunEvents(id)`, actualizado también por el WebSocket.
- `RunPage`:
  - **columna derecha «Eventos MCP»** (rejilla `40px 1fr`: hora mono, función en mono violeta y argumento), como en `09a`;
  - en el panel izquierdo, «Estado actual» (`last_status`) y la caja «Resumen del agente» (`--subtle`).

  La rejilla pasa a `300px minmax(0,1fr) 316px`.
- `RunStatusBadge`: `completed` → tono `done`, «Completada». En la lista y en el Historial, `last_status` aparece como subtítulo de la tarea.
- Al recibir un evento `write_project_memory`, se invalida la consulta del proyecto para que la pestaña Memoria se actualice.
- Textos en `es.json`: `runs.events.*`, `runs.summary`, `runs.lastStatus`, `runs.status.completed` y los errores `agy_folder_busy` / `mcp_*`.

### CLI falso
`tests/fake_cli.py` se amplía para usar lo mismo que un CLI real:
- **modo Claude**: lee `--mcp-config` y `--settings`;
- **modo agy**: lee `.agents\plugins\agentic-os\` de la carpeta de trabajo.

Habla con el MCP con el cliente oficial (`mcp`), ejecuta los `hook.cmd` configurados con el JSON por stdin (prueba el transporte de verdad) y reacciona a palabras clave del prompt:
- `ESTADO: x` → `report_status`;
- `MEMORIA: x` → `write_project_memory`;
- `TERMINA: x` → `complete_task`.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/services/mcp_server.py` | nuevo: `MCPServer`, herramientas, TokenGate, registro de tokens |
| `backend/src/agentic_os/services/adapters/{__init__,base,claude,agy}.py` | nuevos (absorben `runs/launcher.py`) |
| `backend/src/agentic_os/services/context.py` | nuevo |
| `backend/src/agentic_os/services/hooks.py` | nuevo: `hook.cmd`, ruta corta, interpretación de eventos |
| `backend/src/agentic_os/services/runs/{session,manager,screen}.py` | modificados: hooks, eventos, prompt diferido, cierre al completar, diálogo de permiso MCP (si hace falta) |
| `backend/src/agentic_os/api/{runs,hooks}.py`, `app.py`, `__main__.py` | modificados / nuevo (montaje MCP, URL pública, eventos) |
| `backend/src/agentic_os/models/run.py`, `models/run_event.py`, `db/migrations/versions/0003_*.py`, `schemas/run.py` | modificados / nuevos |
| `backend/pyproject.toml`, `scripts/build-backend.ps1` | `mcp` como dependencia; `--collect-submodules mcp` |
| `backend/tests/fake_cli.py`, `tests/test_{mcp_server,hooks,adapters,context,runs_mcp}.py` | modificados / nuevos |
| `frontend/src/api/{types,runs}.ts`, `lib/terminal-socket.ts`, `pages/runs/{RunPage,RunsTable,RunStatusBadge,RunEventsPanel}.tsx`, `i18n/es.json` | modificados / nuevo |
| `docs/adr/0008-agent-coordination.md`, `README.md`, `docs/roadmap.md` | nuevos / modificados |

## Tareas (en orden)
1. [x] **Comprobación con agy real**: ¿existe una regla persistente (plugin o workspace) que preapruebe herramientas MCP? ¿Funciona `hook.cmd` con ruta corta y `curl` en agy y en Claude? Resultado en el plan y en el ADR; se decide el plan A o el B.
2. [x] Modelo: migración `0003` (`completed`, `summary`, `last_status`, `mcp_connected_at`, `run_events`), schemas, `GET /events`; tests de migración y de la API.
3. [x] Servidor MCP montado en el backend: TokenGate, registro de tokens, las cuatro herramientas y la URL pública; tests con el cliente MCP oficial (401, aislamiento entre ejecuciones, efectos en la BD).
4. [x] Hooks: endpoint, `hook.cmd` (ruta corta, `exit /b 0`) e interpretación por CLI; tests, incluido «backend caído → el hook termina con 0».
5. [x] Context builder y adapters (Claude, agy), traducción de permisos, plugin con `.git/info/exclude`, limpieza y recuperación, una ejecución de agy por carpeta; tests de argv y archivos por modo.
6. [x] Integración en `RunSession`/`RunManager`: actividad por hooks, prompt diferido de agy, cierre tras `complete_task` → `completed`, eventos por WebSocket y, si aplica, autoaprobación del diálogo MCP. CLI falso ampliado; tests de extremo a extremo de los dos adapters.
7. [x] Frontend: tipos y API, panel «Eventos MCP», estado actual, resumen, «Completada», refresco de la memoria; tests.
8. [x] Pruebas manuales con Claude y agy reales (CA1, CA2, CA3, CA5) y comparación de la configuración del usuario antes y después (CA6), con capturas en `evidencias/`. Comprobación con el sidecar empaquetado (MCP + hooks).
9. [x] ADR 0008, README, `validacion.md`, `/code-review`, correcciones y puerta 3.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_mcp_server.py`: cliente MCP real contra el backend; `get_context`, `report_status`, `write_project_memory`, `complete_task`; 401 con token desconocido o de una ejecución terminada; un token no ve otra ejecución; la cabecera interna no se puede falsificar | CA1, CA4 |
| `test_hooks.py`: `hook.cmd` con el backend arriba y caído (sale con 0); ruta corta sin espacios; `Stop` → `idle`, `UserPromptSubmit`/`PreInvocation` → `busy`; `conversationId` → `cli_session_id` | CA5 |
| `test_adapters.py`: argv de Claude por modo de permisos y herramientas; archivos de la ejecución; plugin de agy (contenido, `.git/info/exclude` sin duplicar, limpieza solo de lo nuestro, recuperación de huérfanos); agy ocupado → 409 | CA2, CA3, CA8 |
| `test_context.py`: instrucciones con rol, memoria (recortada) y reglas de las herramientas | CA1 |
| `test_runs_mcp.py` (CLI falso, ConPTY real): Claude y agy de extremo a extremo; agy recibe el prompt tras conectar; `TERMINA` → `completed` con resumen y el CLI cerrado solo; eventos por WebSocket; memoria escrita | CA1, CA2, CA5, CA7 |
| `test_migrations.py` actualizado | CA9 |
| `runs.test.tsx`: panel de eventos (inicial y en vivo), resumen, estado actual, «Completada» | CA7 |
| Manual: Claude y agy reales en los tres modos; snapshot de `~/.claude/settings.json`, `~/.claude.json` y `~/.gemini/antigravity-cli/settings.json` antes y después | CA1, CA2, CA3, CA6 |

## Decisiones (ADR)
- **0008: Coordinación agente ↔ Agentic OS**:
  - MCP montado en el backend con token por ejecución en la ruta o en la cabecera;
  - hooks por `hook.cmd` + `curl` que siempre sale con 0;
  - actividad guiada por hooks;
  - estado `completed` con cierre en el fin de turno;
  - prompt de agy diferido hasta que conecta el MCP;
  - una ejecución de agy por carpeta;
  - cómo se aprueban las herramientas MCP en agy (resultado de la tarea 1).
