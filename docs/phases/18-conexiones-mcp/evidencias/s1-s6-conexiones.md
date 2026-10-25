# Fase 18 · Bloque 0 · Spikes S1–S6 (2026-10-24)

Scripts en `spikes/mcp/` (servidores de prueba en `spikes/mcp/servers/`); datos crudos en los `.json` de esta carpeta. Claude Code 2.1.310 y `agy` 1.4.7 en Windows 11. Modelo barato (`haiku`) y `-p` salvo donde se indica PTY. La configuración del usuario (`~/.claude.json`, `~/.claude/`, `~/.gemini/`) **no cambió** en ninguna prueba (`ConfigSnapshot` antes y después).

## S1 · Claude Code (`s1_claude.py`, `s1_pty.py`)
| Pregunta | Resultado |
|---|---|
| (a) `stdio`, HTTP y `npx` en `mcp.json` junto a `agentic-os`, con `--strict-mcp-config` | ✅ Los tres conectan y se llaman (`npx -y @modelcontextprotocol/server-filesystem` también, aunque en Windows sea un `.cmd`). Solo salen los servidores del `mcp.json`. |
| (b) `${VAR}` | ✅ Se expande desde el entorno del proceso en `command`, `args`, `env`, `url` y `headers`. El secreto no tiene por qué escribirse en el fichero. ⚠️ El servidor `stdio` **hereda todo el entorno** del CLI: `show_env AOS_SECRET` devolvió el valor aunque no estuviera en su bloque `env`. Un servidor puede leer los secretos de otra conexión (y el agente, con `Bash`, los de todas). |
| (c) `--disallowedTools mcp__srv__tool` | ✅ La herramienta **desaparece** de las del modelo en `default`, `acceptEdits` y `bypassPermissions` (también el modelo respondió «no disponible»). Una herramienta en ninguna lista: en `-p` se deniega (`permission_denials`), en PTY pedirá permiso por el diálogo normal. |
| (d) servidor que falla | ✅ `failed` en el `init` y la sesión sigue con los demás (comando inexistente o proceso que se cae). Un servidor lento: Claude **espera** (12 s → primer turno a los 17 s, también en PTY con el prompt posicional) hasta **30 s**; pasado eso lo da por `failed`. `MCP_TIMEOUT=90000` en el entorno lo amplía (servidor de 45 s: `connected`, 52 s en total). |
| (e) procesos | ✅ Sin huérfanos tras salida limpia (`-p`), tras `/exit` en PTY y tras `terminate(force)` del PTY (ConPTY cierra el árbol). ⚠️ Matar **solo** el proceso lanzador con `psutil` (sin árbol) dejó vivos 2 procesos del servidor. |
| (f) hooks `mcp__.*` | ✅ `PreToolUse`/`PostToolUse` traen `tool_name` = `mcp__<servidor>__<herramienta>`, `tool_input` y `tool_response`. Una llamada que **falla** no genera `PostToolUse` sino `PostToolUseFailure` (con `error`, `mcp_server`, `duration_ms`). |
| (g) configuración del usuario | ✅ sin cambios |

## S2 · `agy` (`s2_agy.py`, `s2_pty.py`)
| Pregunta | Resultado |
|---|---|
| (a) plugin `mcp_config.json` | ✅ `stdio` (`command`/`args`/`env`), HTTP con `url` + `headers` y `npx` funcionan. **SSE no está soportado** (la documentación del binario manda usar un puente `stdio` como `mcp-remote`). |
| (b) `${VAR}` | ❌ No se expande: *«MCP configs don't expand environment variables»* y *«Agent Plugins plugins don't expand variables»* (cadenas del binario; con `${AOS_PY}` como `command` el servidor no arranca). El servidor `stdio` sí hereda el entorno del proceso (`AOS_SECRET` visible). |
| (c) filtrar herramientas | ✅ `disabledTools: [...]` y `enabledTools: [...]` por servidor en el `mcp_config.json` ocultan la herramienta (el modelo respondió «no disponible»). |
| (d) hooks | ✅ Con `matcher: ".*"` la llamada llega como `toolCall.name = "call_mcp_tool"` con `args.ServerName` (**`agentic-os_<servidor>`**: el plugin pone su prefijo), `args.ToolName` y `args.Arguments`; `PostToolUse` trae `error`. Nuestro propio servidor será `agentic-os_agentic-os`. |
| (e) servidores caídos | ✅ La ejecución termina bien con un servidor que se cae y otro con comando inexistente. ⚠️ El modelo se puso a **investigar** el equipo (`Get-Process`, leer ficheros fuera del workspace) durante 158 s: hace falta una línea en las instrucciones («si una conexión no está disponible, sigue sin ella; no la investigues»). |
| (e2) cuándo han conectado | ❌ No hay señal por servidor: `~/.gemini/antigravity-cli/mcp/<servidor>/` no se reescribe al conectar. ✅ Pero escribir el prompt **antes** de que conecte un servidor de 40 s funcionó (el modelo reintenta; tardó 71 s). |
| (f) procesos y configuración | ✅ Sin huérfanos (headless, salida con Ctrl+C y `terminate`); configuración del usuario sin cambios. |
| Lentitud | Con herramientas MCP, `agy` suele leer los esquemas de `~/.gemini/antigravity-cli/mcp/…` antes de llamar: 33–50 s para tres llamadas (317 s con un prompt largo). |

## S3 · OAuth (`s3_oauth.py`)
- **Servicios reales** (solo lectura, sin registrar ni iniciar sesión): **Linear, Notion, Atlassian, Sentry y Stripe** anuncian registro dinámico (`registration_endpoint`), revocación y PKCE `S256`. **GitHub (remoto) y Asana no tienen registro dinámico** (hace falta un *client id* propio o, en GitHub, un token personal en cabecera). Context7 no pide autenticación.
- **Flujo con el proveedor del SDK** (`mcp.client.auth.OAuthClientProvider`, servidor de autorización simulado):
  - registro dinámico con un puerto de retorno **aleatorio** (cada puerto, un cliente nuevo): ✅;
  - *client id* pegado (sin registro): ✅ solo con el **puerto exacto** registrado; con otro, el servidor rechaza la redirección;
  - renovación **automática** al caducar el token de acceso (`refresh_token`): ✅;
  - revocación (`/revoke`): ✅;
  - el SDK 2.x usa `httpx2` (las cabeceras y la autenticación se pasan con un `httpx2.AsyncClient`) y `ToolAnnotations` en *snake_case* (`read_only_hint`).

## S4 · Registros (`s4_registries.py`)
| Fuente | Estado |
|---|---|
| Registro oficial `registry.modelcontextprotocol.io/v0.1/servers` | ✅ Abierto, sin clave. Búsqueda (`search`), paginación y `server.json`: `packages[]` (`registryType` npm/pypi/oci, `identifier`, `version` —a veces `latest`—, `transport`, `environmentVariables`) y `remotes[]` (`type`, `url`, `headers[]` con `isSecret`). **Sin métrica de uso.** Incluye entradas de Smithery. |
| Smithery `registry.smithery.ai/servers` | ✅ Abierto. `useCount` (usos), `verified`, `remote`, `bySmithery`, orden por uso, y ficha con las herramientas y su esquema. Los remotos de Smithery pasan por su pasarela. |
| Glama `glama.ai/api/mcp/v1` | ❌ 401: **exige clave de API** y su licencia de datos pide atribución visible en cada página y enlace a su ficha. |
| PulseMCP | ❌ `v0beta` retirado (100 % de fallos desde septiembre de 2026); la `v0.1` exige `X-API-Key`. |
| npm / PyPI | ✅ APIs abiertas (búsqueda y versión exacta); sirven para «instalar desde un paquete» y para resolver `latest` a una versión fija. |

## S5 · `keyring`
- Windows Credential Manager (`WinVaultKeyring`): **1 280 caracteres como máximo por entrada** (2 560 bytes en UTF-16; con 1 281 falla con `CredWrite 1783`). Un JWT de OAuth puede pasarlo.
- Troceado en piezas de 1 000 caracteres (entrada principal con el número de piezas + `nombre#i`): ✅ hasta 9 000 caracteres, Unicode (`tókén-ñ-日本-🔑`) y borrado completo.
- Empaquetado con **PyInstaller** (`--onefile` de un script con `keyring`, sin ajustes): ✅ misma salida que sin empaquetar.

## S6 · Importar
- `~/.claude.json`: `mcpServers` global y `projects.<ruta>.mcpServers` (vacío en los 71 proyectos de esta máquina) más `enabledMcpjsonServers` / `disabledMcpjsonServers` / `disabledMcpServers` por proyecto. Campos reales: `type` (`stdio` o `http`), `command`, `args`, `env`, `url`, `headers`. **Hay cabeceras `Authorization` en claro** en la configuración del usuario: el importador las trata como secretos.
- `.mcp.json` del proyecto: mismo formato (ninguno en los proyectos de esta máquina). `~/.gemini/config/mcp_config.json`: existe y está vacío; mismo esquema `mcpServers`.
