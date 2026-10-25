# Fase 18: Conexiones MCP · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-24) · en desarrollo (bloques 1–11 hechos; faltan la prueba manual y el cierre)

## Lo que ya se sabe (revisado al escribir el plan)
- **Lanzamiento**: `RunManager._launch` (`services/runs/manager.py`) arma el `LaunchContext` (`services/adapters/base.py`) con el agente, el proyecto, la tarea, la etapa (`task.stage_id`) y el padre de un subagente, y llama a `adapter.prepare`. Las conexiones entran igual que las skills: un campo nuevo del contexto, preparado antes de `prepare` y limpiado en `cleanup`/`_on_end`.
- **Claude** (`adapters/claude.py`): escribe `<run_dir>/mcp.json` con solo `agentic-os` (HTTP con `Authorization: Bearer`) y lanza con `--mcp-config … --strict-mcp-config`. Los permisos salen de `claude_permissions`: en *Autónomo*, `bypassPermissions` + `--allowedTools mcp__agentic-os__*`; en los otros modos, `--allowedTools` con la lista del agente. Hoy no se usa `--disallowedTools`.
- **`agy`** (`adapters/agy.py`): escribe el plugin `.agents/plugins/agentic-os/` (`plugin.json` con `agenticOsRun`, `mcp_config.json` con `{"url": …}`, `hooks.json`, `rules/AGENTS.md`, `skills/`), lo excluye de git y lo borra al terminar (`remove_plugin`, también en `recover`). El entorno del proceso ya lleva variables propias (`agy_status.environment`).
- **Hooks** (`services/hooks.py`): `PreToolUse`/`PostToolUse` con *matcher* (`CLAUDE_TOOL_MATCHER = "Agent|Task|Skill"`, `AGY_TOOL_MATCHER = "invoke_subagent"`, más `read_file` con skills). Ampliar el *matcher* a las herramientas MCP externas es la forma más directa de registrar sus llamadas.
- **Procesos**: el backend está en un Job Object con `KILL_ON_JOB_CLOSE` (ADR 0007); los servidores `stdio` que arranque el CLI heredan el job. Falta comprobar que mueren al terminar **una** ejecución con el backend vivo (S1).
- **Cliente MCP**: la dependencia `mcp>=2.3` ya está (es la del servidor `agentic-os`) e incluye los clientes `stdio` y *streamable HTTP* y el proveedor OAuth (`mcp.client.auth`). Se usa para la prueba de conexión, el OAuth y la pasarela.
- **Niveles**: `KnowledgeScope` (`general` · `project` · `agent`) y su `CHECK` se reutilizan. Las vías de la fase 13 son etapas (`Stage`), así que quitar una conexión en una etapa sirve también para las ramas.
- **Registros**: `services/skills/registries/` (`base.py`, `service.py`, `sources.py`, `github.py`) ya resuelven caché, errores por fuente (`offline`, `unavailable`, `rate_limited`, `not_found`), activar o apagar fuentes y comprobar actualizaciones a diario. El explorador de conexiones sigue el mismo patrón y comparte la caché y los códigos de error.
- **Credenciales**: `gitx/credentials.py` sirve para un *token* por host. Las conexiones usan `keyring` (decisión 1); no es dependencia todavía.
- **Inbox**: `InboxKind` cerrado con `CHECK`; se añade `connection` (OAuth caducado).
- **Ajustes**: los de skills y conocimiento viven en `app_state` como JSON (`skills/config.py`); los de conexiones, igual.
- Última migración: `0019_skills`.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/mcp/`; evidencias en `evidencias/`. Servidores de prueba: uno `stdio` propio en Python (con herramientas de lectura y de escritura, y uno que se cae al arrancar), uno HTTP propio con cabecera obligatoria, y `@modelcontextprotocol/server-filesystem` por `npx`.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Claude**: (a) ¿`mcp.json` con un servidor `stdio` y otro HTTP junto a `agentic-os`, con `--strict-mcp-config`, funcionan en PTY en Windows (también `npx`, que es un `.cmd`)? (b) ¿Se expanden `${VAR}` en `command`, `args`, `env`, `url` y `headers` desde el entorno del proceso? (c) ¿`--disallowedTools mcp__srv__tool` bloquea la herramienta en los tres modos, también en `bypassPermissions`? ¿Qué pasa con una herramienta nueva que no esté en ninguna lista? (d) ¿Un servidor que no arranca bloquea la sesión o solo se pierde él? ¿Cuánto espera Claude? (e) ¿Mueren los procesos del servidor al cerrar la sesión con `/exit` y al matarla? (f) ¿`PreToolUse`/`PostToolUse` con *matcher* `mcp__.*` dan servidor, herramienta y error? (g) La configuración del usuario no cambia | (b) secretos escritos en `mcp.json` dentro de `<run_dir>` (que se borra); (c) pasarela para las conexiones con selección; (e) cerrar el árbol de procesos del CLI al terminar; (f) leer las llamadas del transcript |
| S2 | **`agy`**: (a) ¿El `mcp_config.json` del plugin admite `command`/`args`/`env` (`stdio`), `headers` y `${VAR}`? (b) ¿Varios servidores en el mismo plugin? ¿Cómo se llaman sus herramientas (prefijo)? (c) ¿Hay forma de filtrar herramientas por servidor? (d) ¿Los *hooks* de herramienta ven las llamadas MCP con su nombre? (e) ¿Cómo saber que **todos** los servidores han conectado antes de escribir el prompt? (f) Procesos al terminar, y configuración del usuario igual | (a) o (c): pasarela para `agy` (todas sus conexiones van por HTTP a `agentic-os`); (d) se registra desde la pasarela o el transcript; (e) esperar a la primera herramienta de cada servidor con un *timeout* |
| S3 | **OAuth**: con el proveedor de `mcp.client.auth` y un servidor remoto real (Linear, Notion o el MCP remoto de GitHub): descubrimiento, registro dinámico, PKCE, retorno a `http://127.0.0.1:<puerto>/…` (¿vale un puerto aleatorio o exige uno fijo?), renovación y revocación. ¿Qué servicios no admiten registro dinámico y qué piden para un *client id* propio (URI de retorno exacta)? | Puerto fijo configurable para el retorno; *client id* pegado como única vía en los servicios sin registro dinámico |
| S4 | **Registros**: el oficial (`registry.modelcontextprotocol.io`, `server.json`), Smithery, Glama y PulseMCP: API pública o con clave, búsqueda, orden «más usados» (¿quién da instalaciones o descargas?), formato de cómo se ejecuta (paquete npm/PyPI/OCI, remoto, variables), versiones, licencia, si marca los oficiales, límites y condiciones de uso | La fuente se cambia por otra o se deja apagada por defecto; «más usados» sale de la fuente que lo dé y se aplica a las demás por nombre de paquete |
| S5 | **`keyring` empaquetado**: con el *sidecar* de PyInstaller en Windows, guardar, leer y borrar en el Administrador de credenciales; tamaño máximo de un secreto (un *token* OAuth puede pasar de 2,5 KB); qué pasa si no hay almacén (Linux sin Secret Service, para la fase 22) | Trocear los secretos grandes en varias entradas; sin almacén, la conexión dice que no puede guardar secretos y solo admite `${VAR}` |
| S6 | **Importar**: estructura real de `~/.claude.json` (servidores globales y los de cada proyecto en `projects.<ruta>.mcpServers`), de `.mcp.json` y de la configuración MCP de `agy` (`~/.gemini/…`); qué campos aparecen (`type`, `env`, `headers`, OAuth) y cómo distinguir un secreto | Se importan solo los campos conocidos y el resto se enseña como «no importado» |

## Resultados de los spikes (bloque 0, 2026-10-24)
Evidencias en [`evidencias/s1-s6-conexiones.md`](evidencias/s1-s6-conexiones.md); scripts en `spikes/mcp/`. La configuración del usuario no cambió en ninguna prueba.

- **S1 · Claude**:
  - `stdio`, HTTP y `npx` junto a `agentic-os` con `--strict-mcp-config`: ✅;
  - `${VAR}` se expande en `command`, `args`, `env`, `url` y `headers`: ✅ (los secretos no se escriben en el fichero);
  - `--disallowedTools mcp__srv__tool` quita la herramienta en los tres modos, también en `bypassPermissions`: ✅; una herramienta en ninguna lista se deniega en *headless* y pide permiso en PTY;
  - un servidor que falla queda `failed` y la sesión sigue; Claude espera hasta **30 s** a uno lento (también en PTY, con el prompt posicional) y `MCP_TIMEOUT` lo amplía;
  - sin huérfanos tras `-p`, `/exit` y `terminate` del PTY; matar solo el lanzador (sin su árbol) sí los deja;
  - hooks `mcp__.*`: `PreToolUse` y `PostToolUse` con `tool_name`, `tool_input` y `tool_response`, y **`PostToolUseFailure`** con `error`, `mcp_server` y `duration_ms` si falla;
  - ⚠️ el servidor `stdio` hereda todo el entorno del CLI.
- **S2 · `agy`**:
  - `stdio` (`command`/`args`/`env`), HTTP con `headers` y `npx` en el `mcp_config.json` del plugin: ✅; **SSE no se admite**;
  - **`${VAR}` no se expande** (lo dice el propio binario);
  - `enabledTools` / `disabledTools` por servidor filtran las herramientas: ✅;
  - los servidores se llaman `agentic-os_<nombre>` y el hook ve `call_mcp_tool` con `ServerName`, `ToolName` y `Arguments` (`PostToolUse` con `error`);
  - un servidor caído no rompe la ejecución, pero el modelo se puso a investigar el equipo;
  - **no hay señal por servidor** de que hayan conectado, y escribir el prompt antes de que conecte funciona (el modelo reintenta, más despacio);
  - sin huérfanos.
- **S3 · OAuth**:
  - Linear, Notion, Atlassian, Sentry y Stripe anuncian registro dinámico, revocación y PKCE `S256`; **GitHub remoto y Asana no tienen registro dinámico**;
  - el proveedor del SDK completa el flujo con registro dinámico y un puerto aleatorio, renueva solo y se puede revocar; un *client id* pegado exige el **puerto exacto** registrado.
- **S4 · Registros**:
  - el registro oficial y Smithery son abiertos; el oficial no da métrica de uso y Smithery da `useCount`, `verified` y las herramientas;
  - **Glama exige clave de API** (y atribución) y **PulseMCP** retiró la `v0beta` y la `v0.1` exige clave;
  - npm y PyPI tienen API abierta.
- **S5 · `keyring`**: tope de **1 280 caracteres** por entrada en Windows; troceando en 1 000 funciona hasta 9 000, con Unicode y borrado; empaquetado con PyInstaller sin ajustes.
- **S6 · Importar**: `~/.claude.json` (`mcpServers` global y por proyecto), `.mcp.json` y la configuración de `agy` comparten el esquema `type`/`url`/`headers`/`command`/`args`/`env`; hay cabeceras `Authorization` en claro.

### Cambios al diseño por los spikes
1. **Sin pasarela.** Los dos CLIs admiten la inyección directa y el filtrado de herramientas por servidor, así que se elimina `gateway.py`, `RunConnection.via` y todo lo que dependía de ella.
2. **Claude**: los secretos van como `${AOS_MCP_<N>_<CLAVE>}` en `mcp.json` y como variables del proceso. `CLAUDE_TOOL_MATCHER` gana `mcp__.*` (menos `mcp__agentic-os__`), y se registra además `PostToolUseFailure`. `MCP_TIMEOUT` = `connections.startup_timeout` (60 s por defecto, para el primer `npx`).
3. **`agy`**: como no expande variables, los valores secretos de `env` y `headers` se escriben **literales** en el `mcp_config.json` del plugin (que ya vive solo durante la ejecución, fuera de git y con el token de la ejecución dentro; ADR 0004). El filtrado va con `disabledTools` (las no permitidas) en el mismo fichero. `AGY_TOOL_MATCHER` gana `call_mcp_tool`; el hook se descarta si `ServerName` es `agentic-os_agentic-os`, y el nombre de la conexión es `ServerName` sin el prefijo `agentic-os_`.
4. **`agy` y SSE**: una conexión SSE se omite en `agy` con un aviso (`RunConnection.status = skipped`, «`agy` no admite SSE: usa la versión HTTP o un puente `stdio`»).
5. **`agy` y la espera**: sin señal por servidor, `deferred_prompt` espera a `agentic-os` como hasta ahora y añade una pausa fija `connections.agy_grace` (5 s si hay conexiones). Las instrucciones de toda ejecución con conexiones dicen: «si una herramienta de una conexión no aparece o falla, reinténtalo y, si sigue sin funcionar, continúa sin ella y dilo; no investigues el equipo».
6. **Procesos**: `_on_end` cierra el árbol del CLI con `psutil` tras la salida ordenada como red de seguridad (matar solo el lanzador deja huérfanos); en PTY no hacía falta, pero cuesta poco.
7. **OAuth**:
   - la escucha del retorno usa un puerto fijo `connections.oauth_port` (53682 por defecto), abierto solo mientras dura «Conectar»; si está ocupado y la conexión usa registro dinámico, se prueba otro y se vuelve a registrar; con *client id* pegado se avisa de que hay que liberarlo o cambiarlo y registrar esa URI de retorno;
   - GitHub (remoto) y Asana no tienen registro dinámico: la UI pide el *client id* (y dice qué URI de retorno registrar), y para GitHub ofrece también el token personal en una cabecera;
   - renovar antes de lanzar = hacer una petición autenticada con el proveedor (`initialize`) y leer el almacén; la renovación es automática.
8. **Secretos en el almacén**: se trocean en piezas de 1 000 caracteres (entrada principal con el número de piezas y `nombre#i`).
9. **Registros**: las fuentes iniciales son el **registro oficial** y **Smithery**, más la instalación desde un paquete npm o PyPI o un repositorio de GitHub. «Más usados»: el `useCount` de Smithery y, para el registro oficial, las descargas semanales de npm de sus paquetes; los paquetes `latest` se fijan a la versión exacta al instalar. **Glama y PulseMCP quedan fuera**: exigen clave de API (Glama además, atribución visible), lo que choca con «registros que exijan cuenta» de la spec. *Aprobado por el usuario (2026-10-24).*
10. **API del SDK 2.x**: `httpx2` para cabeceras y autenticación, `streamable_http_client(url, http_client=…)`, `ToolAnnotations` en *snake_case* y `MCPServer` en lugar de `FastMCP`.
11. **Importar**: se leen `~/.claude.json` (global y por proyecto), el `.mcp.json` de cada proyecto y `~/.gemini/config/mcp_config.json`; los valores de `headers` y `env` con aspecto de secreto (y todo `Authorization`) pasan al almacén.

## Diseño ([ADR 0025](../../adr/0025-mcp-connections.md), nuevo, y ampliación de [ADR 0018](../../adr/0018-forges-and-credentials.md))

### 1. Modelo de datos (migración `0020_mcp_connections`)
- **`McpConnection`** (`mcp_connections`):
  - identidad: `name` (*slug* `a-z0-9_-`, máx. 40 caracteres, único, distinto de `agentic-os`), `description`, `icon`;
  - transporte: `transport` (`stdio` · `http` · `sse`), `command`, `args` (JSON), `cwd`, `url`;
  - valores: `env` y `headers` (JSON `{clave: valor}`), donde cada valor es texto plano, `{"secret": "<id>"}` (en el almacén) o `{"env": "NOMBRE"}` (variable del sistema). Las contraseñas dentro de un argumento o una URL se escriben como `${secreto}` y se guardan igual;
  - `auth` (`none` · `oauth`) y `enabled`;
  - herramientas: `tools` (JSON de la última prueba: nombre, descripción, esquema, `readOnlyHint`, `destructiveHint`), `tested_at`, `test_error`, `tools_changed` (bool), `tool_mode` (`all` · `selected`), `allowed_tools` y `preapproved_tools` (JSON);
  - `origin` (`user` · `template` · `import` · `registry`), `revision` (sube con cada cambio de configuración, para el registro de la ejecución), `created_at`, `updated_at`.
- **`McpAssignment`** (`mcp_assignments`): `connection_id` (`CASCADE`) y el nivel (`scope`, `project_id`, `agent_id`, con el `CHECK` de `KnowledgeScope`); única por `(connection_id, scope, project_id, agent_id)`. Una conexión puede estar en varios proyectos o agentes a la vez.
- **`McpExclusion`** (`mcp_exclusions`): `connection_id` y un `agent_id` **o** un `stage_id` (`CHECK`: uno de los dos), las dos FK `CASCADE`.
- **`McpOAuth`** (`mcp_oauth`, 1:1): `issuer`, `client_id`, `client_registered` (dinámico o pegado), `scopes`, `account_label`, `expires_at`, `status` (`connected` · `needs_reauth` · `disconnected`). Los *tokens* y el secreto del cliente van al almacén.
- **`McpOrigin`** (`mcp_origins`, 1:1, solo las instaladas desde un registro): `registry`, `ref`, `package_type` (`npm` · `pypi` · `oci` · `remote`), `package`, `version`, `repo_url`, `license`, `official`, `latest_version`, `checked_at`, y `manifest` (JSON del `server.json` o equivalente que se instaló, para enseñar qué cambia en una actualización).
- **`RunConnection`** (`run_connections`): `run_id` (`CASCADE`), `connection_id` (`SET NULL`) y `connection_name` (copia), `revision`, `status` (`sent` · `connected` · `failed` · `skipped`) y `detail` (motivo en palabras: «OAuth caducado», «no arrancó: …»).
- **`RunToolCall`** (`run_tool_calls`): `run_id` (`CASCADE`), `connection_name`, `tool`, `started_at`, `duration_ms`, `ok`, `error` (recortado y sin secretos). Índices por `run_id` y por `(connection_name, started_at)`.
- `InboxKind.CONNECTION` (`connection`) con `connection_id` en el elemento (`SET NULL`).
- `downgrade` borra lo nuevo. Los secretos del almacén se borran al borrar cada conexión, no en la migración.

### 2. Secretos (`services/connections/secrets.py`)
- `keyring` con el servicio `agentic-os` y el usuario `mcp:<connection_id>:<id>`. `put`, `get`, `delete`, `delete_all(connection_id)`. Los secretos grandes se trocean si S5 lo pide.
- `resolve(connection) -> (valores, secretos)`: sustituye `{"secret"}` por el valor del almacén y `{"env"}` por la variable del sistema. Un secreto que falta da un motivo en palabras («falta el *token* de GitHub»).
- **Ocultar**: el conjunto de valores secretos de la ejecución (de 6 o más caracteres) se pasa a la sesión, que los cambia por `•••` antes de escribir el log, enviar al WebSocket y guardar diagnósticos. El filtro guarda una cola de bytes del tamaño del secreto más largo para no dejar escapar uno partido entre dos lecturas del PTY. El terminal emulado (pyte) recibe la salida ya filtrada.
- La API nunca devuelve un valor: solo `{"secret": true, "set": true|false}`.

### 3. Catálogo (`services/connections/`)
- **`format.py`**: parser del bloque `mcpServers` (uno o varios servidores; el formato de Claude, el de `agy` y el `server.json` del registro oficial) a conexiones, marcando como secretos los valores de claves que parecen secretas (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `Authorization`…), con la marca editable. Validación con motivo en palabras (CA2).
- **`library.py`**: crear, editar (sube `revision`), activar o apagar, borrar (con sus secretos y sus asignaciones; las cifras de uso quedan por nombre), listar con su uso.
- **`templates.py`**: las plantillas fijas (GitHub, Playwright, PostgreSQL, SQLite, Filesystem, Fetch, Context7 y uno remoto con OAuth, según S4), cada una con su formulario: campos, cuáles son secretos, ayuda y enlace para conseguir el *token*. Las de paquete van fijadas a una versión.
- **`importer.py`**: `scan()` lista lo que hay en `~/.claude.json` (global y por proyecto), en el `.mcp.json` de cada proyecto y en la configuración de `agy` (S6), con si ya está importado; `import(items)` crea las conexiones al nivel elegido y pasa los secretos al almacén. Solo lee los originales (CA9).
- **`export.py`**: el bloque `mcpServers` con los secretos como `${NOMBRE}`.

### 4. Prueba de conexión (`services/connections/probe.py`)
- Con el cliente de `mcp`: `stdio_client` (con el entorno resuelto y `stderr` capturado) o `streamablehttp_client`/`sse_client` (con las cabeceras y, si es OAuth, el *token* vigente). `initialize`, `list_tools`, `list_resources` y `list_prompts`, con *timeout* (`connections.probe_timeout`, 60 s la primera vez por `npx`).
- Errores con código estable y texto en palabras (CA4): `command_not_found` (con «falta Node» si el comando es `npx`/`node`, «falta Python» con `uvx`/`python`, «falta Docker»), `crashed` (con las últimas 20 líneas de `stderr`, filtradas), `timeout`, `unauthorized` (401/403; con OAuth, «Vuelve a conectar»), `unreachable`, `protocol`.
- Guarda `tools`, `tested_at` y `test_error`; si la lista cambia respecto de la anterior, `tools_changed` y el aviso. Con `tool_mode=selected`, las herramientas nuevas quedan **fuera** de la selección hasta que el usuario las añada.
- `requirements()` comprueba `node`, `npx`, `uvx`, `python` y `docker` en el `PATH` (lo usa también la ficha del explorador).
- La prueba se lanza en segundo plano y su resultado llega por evento; se puede cancelar.

### 5. Qué conexiones recibe una ejecución (`services/connections/resolve.py`)
- Activas (`enabled`), asignadas al nivel general, al proyecto de la ejecución o a su agente; menos las excluidas para el agente y para la etapa de la ejecución (`Run.stage_id`) (CA5, CA6).
- Un subagente usa su propio agente (no el padre). Las ejecuciones *headless* internas (decisor, describidor) no pasan por aquí.
- Una conexión OAuth con `status != connected` o cuya renovación falla, o con un secreto que falta, queda `skipped` con su motivo (CA12), y el resto sigue.
- `try_run(agent, project, stage)` devuelve lo mismo para la pestaña «Conexiones» del agente: qué recibiría, de qué nivel viene cada una, las excluidas y por qué, y el total de herramientas con una estimación de *tokens*.

### 6. Inyección (`services/connections/runtime.py`, adapters)
- `prepare_run(db, run, agent, project, stage) -> RunConnections`, llamado en `_launch` antes de `adapter.prepare`: resuelve, renueva los *tokens* OAuth que caduquen en menos de 10 min, crea las filas `RunConnection` y devuelve, por conexión, la configuración, las variables de entorno con los secretos (`AOS_MCP_<N>_<CLAVE>`) y los nombres de herramientas permitidas, preaprobadas y prohibidas. `LaunchContext` gana `connections` y la sesión, `secrets` (para ocultar).
- **Claude** (según S1):
  - cada conexión entra en `<run_dir>/mcp.json` con su nombre, y los secretos como `${AOS_MCP_…}` (o en claro dentro de `<run_dir>` si S1(b) falla; la carpeta se borra al terminar);
  - las variables van en el `env` de `LaunchSpec`;
  - `claude_permissions` gana `connections`: en *Restringido* y *Preguntar*, `mcp__<n>__<herramienta>` preaprobadas en `--allowedTools`; en todos los modos, las no permitidas en `--disallowedTools` (si S1(c) confirma que bloquea también con `bypassPermissions`).
- **`agy`** (S2): las conexiones entran en el `mcp_config.json` del plugin junto a `agentic-os`, con el prefijo del plugin (`agentic-os_<nombre>`). Los valores secretos de `env` y `headers` van literales (el CLI no expande variables) y las herramientas no permitidas, en `disabledTools`. Las conexiones SSE se omiten con aviso. `deferred_prompt` espera a `agentic-os` y una pausa fija `connections.agy_grace` (5 s).
- **Pasarela**: descartada (S1 y S2). Los dos CLIs admiten la inyección directa y el filtrado por servidor.
- **Fin de la ejecución**: `_on_end` cierra el árbol de procesos del CLI (`psutil`) tras la salida ordenada de ADR 0007, como red de seguridad (S1(e): matar solo el lanzador deja huérfanos) (CA11).
- La configuración del usuario no se toca (CA10: *snapshots* como en el spike de la fase 01).

### 7. OAuth (`services/connections/oauth.py`)
- Basado en `mcp.client.auth.OAuthClientProvider` con un `TokenStorage` sobre el almacén del sistema.
- **Conectar** (`POST /api/connections/{id}/oauth/start`): descubre el servidor de autorización desde la URL de la conexión, registra el cliente (dinámico) o usa el *client id* pegado, genera PKCE y `state`, y devuelve la URL de autorización. La UI la abre en el navegador del sistema (Tauri `shell.open`). El retorno llega a `GET /oauth/callback` del backend (`127.0.0.1`, puerto del backend o el fijo que decida S3), que cambia el código por los *tokens*, los guarda, rellena `account_label` y `expires_at` y responde con una página «Ya puedes volver a Agentic OS». La UI se entera por evento.
- **Renovar**: antes de cada ejecución (§6) y al probar; en segundo plano cada hora para las que caducan pronto. Si falla: `needs_reauth`, elemento `connection` en la Inbox («Vuelve a conectar Linear») y las ejecuciones siguen sin ella (CA8).
- **Desconectar**: revoca si el servidor tiene `revocation_endpoint`, borra los *tokens* y deja `disconnected`.
- Una ejecución recibe el *token* de acceso como cabecera `Authorization: Bearer ${AOS_MCP_…}`; nunca el de renovación.

### 8. Registro y uso (`services/connections/usage.py`)
- Las llamadas a herramientas externas llegan por los *hooks* (S1(f), S2(d)): el *matcher* gana `mcp__.*` (sin las de `agentic-os`, que ya se registran en el servidor) y `PreToolUse`/`PostToolUse` crean y cierran la fila `RunToolCall` y el evento `mcp_external`. Los fallos llegan por `PostToolUseFailure` (Claude) o por el campo `error` de `PostToolUse` (`agy`, `call_mcp_tool` con `ServerName`/`ToolName`). Si un CLI no da la información, se lee del transcript (`usage/parsers.py`) al cerrar la ejecución.
- El estado `connected`/`failed` de cada `RunConnection` sale de la primera llamada, o del aviso del CLI (`init` de Claude, S1(d)); en `agy` no hay aviso y queda `sent` hasta la primera llamada.
- Uso de la tarjeta: ejecuciones distintas, llamadas y última fecha, por `connection_name` (sobrevive al borrado de la conexión).

### 9. Registros públicos (`services/connections/registries/`)
- Protocolo `ServerRegistry` como el de skills: `popular(page)`, `search(query, category, transport, page)` → tarjetas (id, nombre, descripción, autor, uso, actualizado, transporte, oficial); `detail(id)` → paquete o URL, versión, comando exacto, variables y cabeceras (con cuáles son secretas), OAuth, herramientas declaradas, licencia, repo y seguridad.
- Fuentes según S4: `official.py` y `smithery.py` (Glama y PulseMCP, fuera de la fase); y `package_url.py` para un repo de GitHub (busca `server.json` o el bloque `mcpServers` del README), un paquete npm o uno de PyPI.
- Se reutilizan la caché de 10 min, los códigos de error por fuente, el *token* opcional de GitHub y la comprobación diaria de actualizaciones de `skills/registries/service.py` (se extrae a un módulo común si hace falta).
- **Instalar** (`POST /api/connections/registries/install`, con `id`, nivel y valores del formulario): crea la conexión `origin=registry` con el comando fijado a la versión (`npx -y paquete@1.2.3`, `uvx paquete==1.2.3`, `docker run … imagen:1.2.3`) y su `McpOrigin`. No ejecuta nada: la prueba la lanza el usuario (CA14).
- **Actualizaciones**: si `latest_version` ≠ `version`, aviso; «Ver cambios» compara el `manifest` instalado con el nuevo (versión, comando, variables, herramientas declaradas); «Actualizar» cambia la versión, sube `revision` y pide volver a probar (CA15).
- Ajuste `connections.registries` con cada fuente activada o no (y su clave si la pide, en el almacén).

### 10. API (`api/connections.py`, `schemas/connections.py`)
- `GET/POST /api/connections`, `GET/PATCH/DELETE /api/connections/{id}`, `PUT /api/connections/{id}/secrets/{key}` y `DELETE …`, `POST /api/connections/parse` (bloque JSON → borrador), `GET /api/connections/templates`, `GET /api/connections/{id}/export`.
- `GET /api/connections/import/scan`, `POST /api/connections/import`.
- `POST /api/connections/{id}/test` (devuelve el id de la prueba), `DELETE /api/connections/tests/{id}`, `PUT /api/connections/{id}/tools` (modo, permitidas, preaprobadas), `GET /api/connections/requirements`.
- `GET/PUT /api/connections/{id}/assignments`, `GET/PUT /api/agents/{id}/connections` (efectivas y exclusiones) y `GET/PUT /api/stages/{id}/connections` (exclusiones).
- `POST /api/connections/{id}/oauth/start`, `POST …/oauth/disconnect`, `GET /oauth/callback`.
- `GET /api/connections/registries`, `GET /api/connections/registries/search`, `GET /api/connections/registries/detail`, `POST /api/connections/registries/install`, `POST /api/connections/updates/check`, `GET /api/connections/{id}/update` (diferencias) y `POST …/update`.
- `GET /api/runs/{id}/connections` (recibidas y llamadas).
- `GET/PUT /api/settings/connections`.
- Eventos: `connection_changed`, `connection_tested`, `connection_oauth`.

### 11. Frontend
- **API** (`api/connections.ts`) y tipos.
- **Navegación**: entrada «Conexiones» (`/conexiones`) con las pestañas **Catálogo · Explorar**; también en Ajustes › Conexiones (nivel general y ajustes).
- **Catálogo** (`components/connections/ConnectionList.tsx`): tarjetas con icono, transporte, estado (probada, error, «Hay que volver a conectar», «Actualización disponible», «Herramientas nuevas»), interruptor, niveles asignados y uso («12 ejecuciones · hace 2 días»).
- **Editor** (`ConnectionEditor.tsx`): hoja con pestañas Formulario y JSON; campos por transporte, lista de variables y cabeceras con la marca «secreto» (valor oculto, «Reemplazar», «Borrar», o «Usar variable del sistema»), aviso al crear una `stdio`, «Conectar» si es OAuth (con la cuenta conectada y la caducidad, y «Desconectar»). «Nueva desde plantilla» abre el editor relleno.
- **Prueba y herramientas** (`ConnectionTools.tsx`): botón «Probar», progreso, error en palabras con el `stderr` desplegable, y la lista de herramientas (lectura/escritura) con «Todas» o «Seleccionar», y la casilla «Preaprobar» por herramienta. Recursos y prompts en una lista de solo lectura.
- **Importar** (`ConnectionImportDialog.tsx`): lista de `scan` con casilla y nivel por fila.
- **Asignación**:
  - pestaña **«Conexiones»** del agente (`pages/agents/tabs/ConnectionsTab.tsx`): lo que recibe, de qué nivel viene, el interruptor para quitarla, el total de herramientas y *tokens* estimados, y «Añadir al agente»;
  - pestaña **«Conexiones»** del proyecto (`pages/projects/tabs/ConnectionsTab.tsx`) con las del proyecto y «Añadir»;
  - en el editor de pipeline, el panel de la etapa (`pipeline/Panels.tsx`) gana «Conexiones» con las que recibiría el agente de la etapa y el interruptor para quitarlas.
- **Ejecución**: sección «Conexiones» en la página de la ejecución (recibidas, estado, vía, motivo) y, en «Eventos MCP», las llamadas externas con su conexión, duración y error, distinguidas de las de `agentic-os`.
- **Inbox**: clase `connection` con el botón «Volver a conectar».
- **Explorador** (`components/connections/registry/`): «Más usados» por defecto, búsqueda, filtros de fuente, categoría y transporte, tarjetas con la marca «Oficial», ficha (hoja) con descripción, comando exacto, requisitos (los que faltan en rojo), variables y secretos, OAuth, herramientas declaradas, licencia, repo y seguridad, el aviso fijo sobre servidores de terceros, «Instalar en…» con el nivel (abre el editor relleno), estados «Sin conexión» y «Fuente no disponible», y «Ver cambios» / «Actualizar» en las instaladas.
- **Ajustes** (`pages/settings/ConnectionsSection.tsx`): conexiones generales, fuentes de registros, *timeouts* y el estado del almacén de credenciales.
- i18n en `es.json` y `test/fake-backend.ts` ampliado.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0020_mcp_connections.py` | nuevo |
| `backend/src/agentic_os/models/connection.py`, `models/__init__.py`, `models/inbox.py` | nuevo / modificado |
| `backend/src/agentic_os/services/connections/` (`secrets.py`, `format.py`, `library.py`, `templates.py`, `importer.py`, `export.py`, `probe.py`, `resolve.py`, `runtime.py`, `oauth.py`, `usage.py`, `config.py`, `events.py`) | nuevo |
| `backend/src/agentic_os/services/connections/registries/` (`base.py`, `official.py`, `smithery.py`, `package_url.py`, `service.py`) | nuevo |
| `backend/src/agentic_os/services/skills/registries/` (caché y errores comunes, si se extraen) | modificado |
| `backend/src/agentic_os/services/adapters/base.py`, `claude.py`, `agy.py` | modificado |
| `backend/src/agentic_os/services/runs/manager.py`, `runs/session.py` (ocultar secretos), `services/hooks.py`, `services/inbox.py`, `services/mcp_server.py` | modificado |
| `backend/src/agentic_os/api/connections.py`, `schemas/connections.py`, `api/agents.py`, `api/pipelines.py`, `api/runs.py`, `api/settings.py`, `app.py` | nuevo / modificado |
| `backend/pyproject.toml` | `keyring` como dependencia |
| `backend/agentic_os.spec` (o el fichero de PyInstaller que corresponda) | *backends* de `keyring` incluidos |
| `backend/tests/test_connections_*.py`, `backend/tests/fixtures/mcp_servers/` | nuevo |
| `frontend/src/api/connections.ts` | nuevo |
| `frontend/src/components/connections/` (`ConnectionList`, `ConnectionCard`, `ConnectionEditor`, `SecretField`, `ConnectionTools`, `ConnectionImportDialog`, `OAuthButton`, `registry/ServerExplorer`, `registry/ServerSheet`) | nuevo |
| `frontend/src/pages/connections/ConnectionsPage.tsx`, `pages/agents/tabs/ConnectionsTab.tsx`, `pages/projects/tabs/ConnectionsTab.tsx`, `pages/projects/tabs/pipeline/Panels.tsx`, `pages/runs/*`, `pages/InboxPage.tsx`, `pages/settings/ConnectionsSection.tsx`, `SettingsPage.tsx`, navegación | nuevo / modificado |
| `frontend/src/i18n/es.json`, `test/fake-backend.ts` | modificado |
| `docs/adr/0025-mcp-connections.md` | nuevo |
| `docs/adr/0018-forges-and-credentials.md` | ampliado (almacén del sistema para las conexiones) |
| `spikes/mcp/` | nuevo |

## Tareas (en orden)
1. [x] **Bloque 0 · Spikes** S1–S6 hechos; evidencias y cambios al diseño anotados arriba. Glama y PulseMCP fuera de la fase y SSE omitido en `agy`: aprobado por el usuario (2026-10-24).
2. [x] **Bloque 1 · Datos y secretos**: migración `0020`, modelos, `InboxKind.CONNECTION`, `secrets.py` con `keyring` y troceado en piezas de 1 000, filtro de ocultación en la sesión (`redact.py`, que retiene el final de cada trozo por si el secreto llega partido) y almacén en memoria en los tests (`conftest`). Cambio: los valores secretos son marcadores de texto `${secret:CLAVE}` / `${env:NOMBRE}` en `env`, `headers`, `args` y `url`, no `{"secret": id}`.
3. [x] **Bloque 2 · Catálogo (backend)**: parser y validación, CRUD con `revision`, secretos por campo, plantillas, importar de los CLIs con nivel, exportar sin secretos, API.
4. [x] **Bloque 3 · Prueba de conexión**: cliente `stdio`/HTTP/SSE, errores en palabras con `stderr`, requisitos, herramientas guardadas, aviso de cambios, modos de herramientas y preaprobadas. Hecho. El SDK 2.x esconde el estado HTTP dentro de un `MCPError` genérico: se anotan los estados con un *hook* del cliente HTTP (`httpx2`) para distinguir 401/403/404. Prueba en segundo plano con `wait=true` opcional, cancelable; `npx` real verificado en Windows (test con `AGENTIC_OS_REAL_NPX=1`).
5. [x] **Bloque 4 · Asignación**: asignaciones por nivel, exclusiones por agente y por etapa, resolución para una ejecución (subagente, *headless*), «qué recibiría» del agente, API. Hecho. Se añaden `POST/DELETE /api/connections/{id}/assignments` (en lugar de un `PUT` que reemplaza todo) y `POST /api/connections/try`.
6. [x] **Bloque 5 · Inyección**: `prepare_run`, Claude (`mcp.json`, entorno, `--allowedTools`/`--disallowedTools`), `agy` (plugin, espera de conexión), conexión que falla sin tumbar la ejecución, cierre de procesos, *snapshots* de la configuración del usuario. Hecho. Sin pasarela ni cierre de árbol de procesos (ConPTY lo hace: comprobado con el servidor `stdio` real al parar y al cerrar el backend). `cwd` de una conexión `stdio` no se inyecta (ninguno de los dos CLIs lo admite). Una selección de herramientas sin prueba previa deja la conexión `skipped`. No hay *preflight*: el estado `failed` se decide con la primera llamada (bloque 7).
7. [x] **Bloque 6 · OAuth**: inicio, retorno, registro dinámico y *client id* pegado, renovación antes de lanzar y en segundo plano, `needs_reauth` con elemento en la Inbox, desconectar y revocar. Hecho. Escucha de retorno propia (puerto `connections.oauth_port`, abierta solo durante «Conectar»; con registro dinámico, otro puerto si está ocupado); el renovador en segundo plano y la renovación antes de lanzar usan el mismo proveedor del SDK. Pendiente de la prueba manual con un servicio real (Linear o Notion) en el bloque 12.
8. [x] **Bloque 7 · Registro y uso**: *matcher* `mcp__.*`, `RunToolCall`, estado de cada `RunConnection`, uso de la tarjeta, API de la ejecución. Hecho. *Matchers* `mcp__.*` (Claude, más `PostToolUseFailure`) y `call_mcp_tool` (agy, con el fallo en el campo `error` de `PostToolUse`); `GET /api/runs/{id}/connections`. Las llamadas no son `RunEvent`: la página de la ejecución las mezcla en «Eventos MCP» desde este endpoint.
9. [x] **Bloque 8 · Registros (backend)**: fuentes según S4, búsqueda y «más usados», ficha con comando y requisitos, instalar fijado a versión, actualizaciones con diferencias, ajustes de fuentes. Hecho con el registro oficial, Smithery y paquete / repositorio (npm, PyPI, GitHub con `server.json` o README). «Más usados»: `useCount` de Smithery y descargas semanales de npm; el oficial publica sobre todo servidores recientes, así que su lista pesa poco. Comprobado de solo lectura contra los servicios reales (40 fichas del oficial sin fallos).
10. [x] **Bloque 9 · Catálogo (frontend)**: página «Conexiones», tarjetas, editor (formulario y JSON, secretos, plantillas, OAuth), prueba y herramientas, importar, Ajustes › Conexiones. Hecho: página «Conexiones» (`/conexiones`, pestañas Catálogo · Explorar), tarjetas, hoja de la conexión con Configuración · Herramientas · Dónde se usa · Uso, formulario con filas de variables/cabeceras y casilla «Secreto» (el valor va a una lista de secretos aparte, nunca se devuelve), pegar JSON con vista previa, plantillas, importar de los CLIs, prueba y selección de herramientas, OAuth (conectar, client id propio, renovar, desconectar), actualizaciones, Ajustes › Conexiones. La interfaz no tiene *shell* de Tauri, así que el navegador de inicio de sesión lo abre el backend (`POST /api/connections/oauth/flows/{id}/open`, añadido). Pruebas y logins se siguen por consulta cada segundo, sin eventos en vivo.
11. [x] **Bloque 10 · Asignación y ejecución (frontend)**: pestañas del agente y del proyecto, panel de la etapa, sección y eventos en la ejecución, Inbox. Hecho: pestaña «Conexiones» del agente (lo que recibe, de qué nivel, coste en herramientas y *tokens*, interruptor para quitarla y «dar otra»), pestaña del proyecto (con «dar una existente»), sección en el panel de la etapa del pipeline, panel «Conexiones MCP» en la ejecución (estado, motivo y llamadas aparte de las de `agentic-os`) y el botón «Volver a conectar» de la Inbox, que abre la conexión (`/conexiones?conexion=<id>`).
12. [x] **Bloque 11 · Explorador (frontend)**: más usados, búsqueda y filtros, ficha, instalar en un nivel, sin conexión y fuentes caídas, actualizaciones. Hecho: más usados, búsqueda con filtros de registro y tipo, ficha con el comando exacto, requisitos que faltan, campos y secretos, forma de ejecutarlo a elegir, nivel opcional, aviso permanente, estados «sin conexión» y «fuente caída», y buscar actualizaciones.
13. [ ] **Bloque 12 · e2e y prueba manual**: CLI falso con cliente MCP real contra los servidores de prueba (CA1), y `claude` y `agy` reales con el MCP de GitHub y un servicio OAuth (CA1, CA7, CA8, CA10).
14. [ ] **Bloque 13 · Cierre**: e2e con el binario empaquetado (CA16), `/code-review`, ADR 0025 definitivo y ampliación de ADR 0018, README, validación.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_connections_e2e.py`: CLI falso con cliente MCP real recibe la conexión `stdio` y la HTTP de prueba en su configuración y llama a sus herramientas; filas `RunConnection` y `RunToolCall` | CA1 |
| `test_connections_library.py`: CRUD de `stdio` y HTTP, `parse` de bloques `mcpServers` (Claude, `agy`, `server.json`), nombre repetido, inválido o `agentic-os` → error en palabras; `connections.test.tsx` (formulario y JSON) | CA2 |
| `test_connections_secrets.py`: con un `keyring` en memoria, el secreto no está en la BD, ni en la API, ni en la exportación; el filtro oculta un secreto también partido entre dos lecturas; el servidor de prueba recibe el valor real | CA3 |
| `test_connections_probe.py`: herramientas con esquema del servidor de prueba; comando inexistente (con «falta Node» para `npx`), proceso que se cae (con `stderr`), *timeout*, 401 y URL inaccesible | CA4 |
| `test_connections_resolve.py`: niveles general, proyecto y agente, exclusión por agente, subagente con su agente, *headless* sin conexiones, apagadas fuera | CA5 |
| ídem: exclusión en una etapa y en una vía de la fase 13; las demás etapas la reciben | CA6 |
| `test_connections_permissions.py`: argumentos de Claude por modo (`--allowedTools` con las preaprobadas, `--disallowedTools` con las no permitidas), herramientas nuevas fuera de una selección; `disabledTools` en el plugin de `agy`; manual con `claude` en *Restringido* | CA7 |
| `test_connections_oauth.py`: servidor de autorización simulado (descubrimiento, registro dinámico y *client id* pegado, PKCE, retorno, renovación antes de lanzar, fallo → `needs_reauth` + Inbox, desconectar borra); manual con un servicio real | CA8 |
| `test_connections_import.py`: `~/.claude.json` y `.mcp.json` falsos con servidores globales y por proyecto; secretos al almacén; *hash* del original igual | CA9 |
| `test_connections_isolation.py`: *snapshots* de `~/.claude`, `~/.claude.json` y la carpeta de `agy` (falsos) antes y después de preparar y limpiar una ejecución con conexiones; manual con los CLIs reales | CA10 |
| `test_connections_lifecycle.py`: ejecución con el servidor `stdio` de prueba terminada y cancelada → ningún proceso suyo vivo | CA11 |
| ídem: servidor que se cae al arrancar y OAuth caducado → la ejecución sigue, `RunConnection` `failed`/`skipped` con motivo, aviso en la ejecución | CA12 |
| `test_connections_usage.py`: *hooks* `PreToolUse`/`PostToolUse` de `mcp__…` → `RunToolCall` y evento; uso de la tarjeta, también tras borrar la conexión; `run-connections.test.tsx` | CA13 |
| `test_connections_registries.py` con fuentes simuladas (`httpx.MockTransport`): más usados, búsqueda, filtros, ficha con comando exacto y requisitos, instalar al nivel con la versión fijada y `McpOrigin`; `server-explorer.test.tsx`; manual con las fuentes reales | CA14 |
| ídem: versión nueva → aviso y diferencias, sin cambios sin confirmación; sin red → «Sin conexión» y el catálogo va; una fuente que falla no tira las demás | CA15 |
| `test_connections_e2e.py` con `AGENTIC_OS_E2E_BINARY`: instalar desde el explorador simulado (o una plantilla) → probar → asignar → ejecución que la usa | CA16 |

## Decisiones (ADR)
- [ADR 0025](../../adr/0025-mcp-connections.md) (borrador):
  - conexiones como catálogo global con asignaciones por nivel y exclusiones por agente y por etapa (no una copia por nivel, para que el *token* de GitHub se dé una vez y valga para varios proyectos);
  - secretos en el almacén del sistema, pasados al CLI por variables de entorno y ocultados en la salida;
  - inyección directa en la configuración por ejecución de cada CLI, sin pasarela (descartada en los spikes);
  - OAuth hecho por la app con el proveedor del SDK de MCP;
  - registros detrás de un protocolo, con la instalación fijada a una versión.
- **Ampliación de ADR 0018**: «la app no guarda secretos propios» pasa a «la app no guarda secretos en sus ficheros»: los *tokens* de git siguen en el *helper* de git y los de las conexiones van al almacén del sistema.
- **Límite conocido**: el agente puede leer las variables de entorno de su proceso (el servidor `stdio` hereda todo el entorno del CLI, y en `agy` los secretos de `env` y `headers` están en el `mcp_config.json` del plugin, durante la ejecución). Es inevitable si el CLI arranca el servidor. Se documenta en el ADR y en el aviso al crear una conexión.
- Resuelto en los spikes: `${VAR}` en Claude sí y en `agy` no, filtrado de herramientas en los dos, sin pasarela, puerto fijo de OAuth, fuentes de los registros, troceado de secretos y formatos de importación (ver arriba).

## Estado al cerrar la sesión (2026-10-24)
- **Rama** `phase/18-conexiones-mcp`, todo commiteado (último: `feat(mcp): public registries explorer (phase 18, block 8)`). Árbol de trabajo limpio.
- **Hecho**: bloques 0–8 (spikes y todo el backend). Tests propios en `backend/tests/test_connections_*.py` y `test_migration_0020.py`, todos en verde.
- **Pendiente de comprobar**: la suite completa del backend (`cd backend && uv run pytest -q -p no:warnings`) estaba corriendo y no llegó a terminar; sin fallos hasta donde llegó. Hay que relanzarla y arreglar lo que salga (se tocaron `hooks.py`, `inbox.py`, `session.py`, `manager.py`, `adapters/*`, `fake_cli.py`, `conftest.py`).
- **Siguiente**: bloques 9–11 (frontend: página «Conexiones», editor con secretos y OAuth, prueba y herramientas, importar, pestañas del agente/proyecto/etapa, sección en la ejecución, Inbox, explorador, Ajustes), luego 12 (e2e y prueba manual con `claude`/`agy` reales y un servicio OAuth real) y 13 (cierre: binario empaquetado, `/code-review`, ADR 0025, ampliar ADR 0018, README, validación).
- **Tener en cuenta**: la UI consulta cada segundo `GET /api/connections/tests/{id}` y `/oauth/flows/{id}` (no hay eventos en vivo); en la prueba con el binario empaquetado los tests escribirían en el Administrador de credenciales real (hay que borrar lo que creen); los tests de `npx` real van con `AGENTIC_OS_REAL_NPX=1`.
