# ADR 0004: Instrucciones, MCP, hooks y permisos por ejecución sin tocar la configuración del usuario

- **Estado**: aceptado
- **Fecha**: 2026-10-09
- **Contexto de decisión**: spike de la fase 01 ([`spike.md`](../phases/01-spike-clis/spike.md), P4–P6, P9)

## Contexto
Cada ejecución necesita:
- las instrucciones de su agente (rol, tarea, memoria del proyecto);
- el servidor MCP `agentic-os` con un token propio;
- hooks para conocer su estado;
- un modo de permisos.

Todo ello **sin modificar la configuración global del usuario** y sin que la configuración del usuario altere el comportamiento pedido.

## Decisión
### Claude Code: todo por flags
```
claude "<prompt>" \
  --session-id <uuid> \
  --setting-sources project,local          # ignora ~/.claude/settings.json (defaultMode, hooks…)
  --settings <run>/settings.json           # nuestros hooks (Stop, SubagentStart/Stop, PreToolUse…)
  --mcp-config <run>/mcp.json --strict-mcp-config   # solo nuestro MCP, con Authorization: Bearer <token>
  --append-system-prompt-file <run>/instructions.md # o --append-system-prompt
  --permission-mode <manual|acceptEdits|bypassPermissions>
  --allowedTools mcp__agentic-os__* [herramientas permitidas]
  --model <modelo>
```
- El prompt va **primero**: las opciones variádicas (`--allowedTools <tools...>`) se tragan un prompt posicional que vaya detrás.
- Los archivos de la ejecución (`<run>/…`) viven en la carpeta de datos de Agentic OS, nunca en el proyecto.
- Las reglas de permisos cubren `Bash(...)` **y** `PowerShell(...)` en Windows.

### Antigravity CLI: plugin de workspace
`agy` no tiene flags de instrucciones, MCP ni hooks por sesión, pero descubre **plugins de workspace** en `.agents/plugins/` de la carpeta de trabajo:
```
<workspace>/.agents/plugins/agentic-os/
  plugin.json        {"name": "agentic-os"}
  mcp_config.json    {"mcpServers": {"agentic-os": {"url": "http://127.0.0.1:<port>/r/<token>/mcp"}}}
  hooks.json         Stop / PreToolUse / PostToolUse / PreInvocation → comando sin comillas, que nunca falla
  rules/AGENTS.md    instrucciones del agente
```
- El token va en la **ruta** de la URL (el `mcp_config.json` de plugin no se ha probado con cabeceras).
- Permisos: `--dangerously-skip-permissions` (autónomo), `--mode accept-edits` (restringido) o el modo por defecto (preguntar).
- En PTY: lanzar sin `-i`, esperar a que el MCP del plugin esté conectado y escribir el prompt.
- **Dónde se escribe el plugin**:
  - workspace de tipo **worktree** → dentro del worktree, que es exclusivo de la ejecución;
  - **carpeta directa** del proyecto → `.agents/plugins/agentic-os/`, con `.agents/plugins/agentic-os/` añadido a `.git/info/exclude` para no ensuciar git. Se reescribe en cada ejecución (token nuevo) y se borra al terminar.

  Dos ejecuciones simultáneas de `agy` en la misma carpeta directa compartirían plugin, así que el scheduler no lo permite: la concurrencia en una carpeta directa es 1 por CLI.

### Servidor MCP `agentic-os`
- Streamable HTTP en `127.0.0.1`, puerto libre.
- Token por ejecución, en `Authorization: Bearer` o en la ruta `/r/<token>/mcp`. Se valida en cada petición; un token desconocido o caducado recibe 401.
- Cada token solo actúa sobre su propia ejecución y su tarea (un modelo puede leer el token del archivo de configuración e intentar usarlo por otros medios).

### Entorno
Los procesos de los CLIs se lanzan sin variables `CLAUDE*` heredadas (si heredan `CLAUDE_CODE_CHILD_SESSION`, Claude no guarda el transcript).

## Consecuencias
- ✅ La configuración global del usuario no se toca (verificado con snapshots antes y después en todos los escenarios del spike).
- ✅ Los permisos por agente se cumplen aunque el usuario tenga `defaultMode: auto` o hooks globales.
- ⚠️ En `agy`, la carpeta directa recibe un `.agents/plugins/agentic-os/` temporal y queda limitada a una ejecución simultánea.
- ⚠️ La confianza en carpetas se acumula en `~/.claude.json` y `~/.gemini/antigravity-cli/settings.json`. Mitigación: los worktrees cuelgan de un directorio raíz único, y al borrar un worktree se limpia su entrada.
- ⚠️ `--setting-sources project,local` también ignora las preferencias útiles del usuario (p. ej. el modelo por defecto). Agentic OS define explícitamente lo que necesita.

## Alternativas descartadas
- **`agy mcp add` / `remove` por ejecución**: escribe en la configuración global y deja restos si la ejecución se interrumpe.
- **`--bare` en Claude**: exige API key; no vale con suscripción.
- **HOME o `CLAUDE_CONFIG_DIR` aislados**: perderíamos la sesión iniciada del usuario y hay alternativas más simples.
- **SDK de Python de Antigravity**: prometedor (instrucciones nativas), pero sin terminal interactiva; queda como opción para revisar en la fase 04.
