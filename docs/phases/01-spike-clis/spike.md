# Fase 01 · Spike de CLIs: matriz de capacidades

- **Versiones probadas**: Claude Code 2.1.295–2.1.296 (se actualizó solo durante el spike) · Antigravity CLI (`agy`) 1.3.1–1.3.2
- **Sistema**: Windows 11, ConPTY vía pywinpty 3.0.5
- **Fecha**: 2026-10-09
- **Prototipos**: [`spikes/`](../../../spikes/) · **Evidencias**: [`evidencias/`](evidencias/)
- **Coste total del spike**: unos 0,10 USD equivalentes en Claude (Haiku) y unos 40 prompts en Gemini Flash Low.

Leyenda: ✅ funciona tal cual · ⚠️ funciona con una condición o un matiz · ❌ no disponible

## Resumen

| # | Pregunta | Claude Code | Antigravity (`agy`) |
|---|---|---|---|
| P1 | Lanzamiento en PTY con prompt inicial | ✅ | ✅ |
| P2 | Fin de turno / esperando entrada | ✅ | ✅ |
| P3 | Interrumpir sin matar la sesión | ✅ Esc | ✅ Esc |
| P4 | Instrucciones por agente sin tocar archivos del usuario | ✅ `--append-system-prompt` | ✅ `rules/AGENTS.md` del plugin de workspace (también `AGENTS.md`/`GEMINI.md`) |
| P5 | MCP por ejecución sin tocar la configuración global | ✅ `--mcp-config` + `--strict-mcp-config` | ⚠️ plugin de workspace; en PTY hay que esperar a que conecte |
| P6 | Modos de permisos | ⚠️ hay que aislar la configuración del usuario | ✅ |
| P7 | ID de sesión y reanudación | ✅ `--session-id` / `--resume` | ✅ `conversation_id` / `--conversation` |
| P8 | Consumo por sesión | ✅ tokens + coste equivalente | ⚠️ tokens, sin coste |
| P9 | Hooks por sesión | ✅ `--settings` | ⚠️ `hooks.json` en el plugin de workspace (sin comillas en los comandos) |
| P10 | Detección de subagentes nativos | ✅ | ✅ |
| P11 | Modo headless (`-p` + stream-json) | ✅ | ✅ |
| P12 | Instalación, versión, sesión y modelos | ✅ `claude auth status` | ✅ `agy models` |

---

## P1 · Lanzamiento en pseudo-terminal
| | Claude Code | agy |
|---|---|---|
| Comando | `claude [opciones] "<prompt>"` | `agy [opciones] -i "<prompt>"` |
| Render | ✅ TUI completa en ConPTY; `pyte` la reproduce bien a 120×40 | ✅ ídem |
| Escritura desde fuera | ✅ texto + `\r`. Hay que dar unos 0,4 s entre el texto y el Enter para que la TUI lo pinte | ✅ ídem |
| Redimensionar | ✅ `setwinsize` → la TUI se reorganiza | ✅ |
| Confianza en la carpeta | ⚠️ diálogo «Do you trust the files in this folder?» en cada carpeta nueva (solo en interactivo). Hay que pulsar ↓ y Enter, **esperando a que el menú esté activo** (las teclas tempranas se pierden). Queda guardado en `~/.claude.json → projects` | ⚠️ «Do you trust the contents of this project?», con «Yes» preseleccionado (Enter). Se guarda en `settings.json → trustedWorkspaces` (global) |

Evidencia: [`p1-claude-pty.md`](evidencias/p1-claude-pty.md), [`p1-agy-pty.md`](evidencias/p1-agy-pty.md).

## P2 · Fin de turno y esperando entrada
| Señal | Claude Code | agy |
|---|---|---|
| En pantalla | `✻ <verbo> for Ns · done HH:MM` al acabar cada turno; pie con `esc to interrupt` mientras trabaja | Pie `esc to cancel` + `Generating...` mientras trabaja; `? for shortcuts` en reposo |
| Hook | `Stop` (y `SubagentStop`), con `session_id` y `transcript_path` | `Stop`, con `fullyIdle`, `terminationReason` y `conversationId` |
| Petición de permiso | Diálogo en la TUI (y hooks `PermissionRequest` / `Notification`) | Diálogo «Requesting permission for… Run this command?» con 4 opciones |

Conclusión: el adapter combina el **hook `Stop`** (fiable, estructurado) con el **estado del pie de la TUI** (para «esperando permiso» o «esperando entrada»).

## P3 · Interrumpir y salir
| | Claude Code | agy |
|---|---|---|
| Esc durante un turno | ✅ «Interrupted · What should Claude do instead?»; la sesión sigue viva y responde al siguiente prompt | ✅ «Interrupted · What should Antigravity CLI do instead?»; ídem |
| Ctrl+C | ⚠️ por ConPTY no tiene efecto visible (ni con dos pulsaciones) | ✅ el primero avisa con «press ctrl+c again to exit»; el segundo cierra |
| Salida limpia | ✅ `/exit` (imprime `claude --resume <id>`) | ✅ doble Ctrl+C |

→ **Semántica propuesta de «Tomar control»** (ADR 0003): enviar **Esc**, que interrumpe el turno en curso y deja la sesión viva esperando al humano, y pasar el stdin al usuario. «Devolver al agente» es solo devolver el stdin: el agente continúa cuando recibe el siguiente mensaje, sea del humano o del scheduler («continúa»).

## P4 · Instrucciones del agente
| Mecanismo | Claude Code | agy |
|---|---|---|
| Flag de sistema | ✅ `--append-system-prompt` (también `--system-prompt` para reemplazarlo) | ❌ no hay flag en el CLI |
| Archivo en la carpeta de trabajo | ✅ `CLAUDE.md` | ✅ `AGENTS.md` y `GEMINI.md` |
| Reglas `.agents/rules/*.md` | — | ⚠️ no se aplicaron con un prompt simple (se cargan al abrir archivos) |
| Reglas en plugin | — | ✅ `.agents/plugins/<x>/rules/AGENTS.md` ([evidencia](evidencias/p4-agy-plugin-rules.txt)) |
| Alternativa | — | SDK de Python `google-antigravity` con `system_instructions` |

⚠️ Escribir `AGENTS.md`/`GEMINI.md` en la carpeta del proyecto modifica el proyecto del usuario. Con workspaces de tipo worktree es aceptable (carpeta propia, se puede ignorar en git); con la carpeta directa hay que usar el plugin de workspace en `.agents/` (ADR 0004).

Evidencia: [`p4-p6-context-permissions.md`](evidencias/p4-p6-context-permissions.md).

## P5 · MCP por ejecución
| | Claude Code | agy |
|---|---|---|
| Mecanismo | `--mcp-config <json temporal>` + `--strict-mcp-config`; HTTP con cabecera `Authorization` | Plugin de workspace `.agents/plugins/agentic-os/` con `plugin.json` + `mcp_config.json` (`{"url": …}`); el token va en la ruta de la URL |
| Headless | ✅ | ✅ con permiso para la herramienta MCP (`--dangerously-skip-permissions` o una regla `mcp(...)`); por defecto se deniega |
| PTY | ✅ | ⚠️ el MCP del plugin **conecta de forma asíncrona** tras el arranque: un prompt enviado con `-i` llega antes y el modelo no ve las herramientas. Hay que lanzar sin `-i`, esperar a que esté conectado y escribir el prompt. Cada llamada pide permiso en la TUI |
| Config global | ✅ sin cambios | ✅ sin cambios (`~/.gemini/antigravity-cli/mcp/` es una caché de esquemas) |
| User-agent | `claude-code/<v> (cli)` / `(sdk-cli)` | `Go-http-client/1.1` |
| Efecto lateral | ⚠️ sin `--strict-mcp-config` arranca **todos los MCP globales del usuario**, que pueden quedar huérfanos (pasó con `godot_ai`) | — |

⚠️ Un modelo débil sin las herramientas MCP **improvisó**: leyó `mcp_config.json` del workspace y llamó al servidor con un script de Python (user-agent `Python-urllib`). El servidor debe validar el token, y el token no debe dar más permisos que los de la propia ejecución.

Evidencia: [`p5-claude-mcp.md`](evidencias/p5-claude-mcp.md), [`p5-agy-mcp.md`](evidencias/p5-agy-mcp.md), [`p5-agy-mcp-connected.md`](evidencias/p5-agy-mcp-connected.md), [`p5-agy-mcp-pretrusted.md`](evidencias/p5-agy-mcp-pretrusted.md).

## P6 · Permisos
| Modo de Agentic OS | Claude Code | agy |
|---|---|---|
| Autónomo | `--permission-mode bypassPermissions` (o `auto`) | `--dangerously-skip-permissions` |
| Restringido | `--permission-mode acceptEdits` + `--allowedTools` / `--disallowedTools` | `--mode accept-edits` (edita, no ejecuta comandos) |
| Preguntar | `--permission-mode manual` (por defecto) | modo por defecto: pregunta en la TUI; en headless, deniega |

⚠️ **Claude hereda la configuración del usuario** (`~/.claude/settings.json`). En esta máquina hay `defaultMode: auto` y 13 hooks globales (incluido `PermissionRequest`), así que sin aislar escribía archivos sin ningún flag e ignoraba `--disallowedTools`. Con **`--setting-sources project,local`** se comporta según lo pedido. `--bare` aísla aún más, pero exige autenticación por API key (no vale con suscripción).

⚠️ En Windows, Claude usa la herramienta **`PowerShell`** además de `Bash`: las reglas tienen que cubrir las dos. `acceptEdits` permite redirecciones de shell que crean archivos.

⚠️ En `agy`, las denegaciones en headless salen en `denied_actions` (`write_file`, `command`, `mcp`).

## P7 · Sesiones
| | Claude Code | agy |
|---|---|---|
| Fijar el ID al lanzar | ✅ `--session-id <uuid>` (lo respeta) | ❌ se genera; se lee del evento `init` o del resultado (`conversation_id`) |
| Reanudar | ✅ `--resume <id>` mantiene el contexto | ✅ `--conversation <id>` mantiene el contexto |
| ID visible en PTY | `/exit` imprime `claude --resume <id>`; hook `SessionStart` | hooks (`conversationId` en cada evento) |

## P8 · Consumo
| | Claude Code | agy |
|---|---|---|
| Fuente | Transcript `~/.claude/projects/<slug-del-cwd>/<session-id>.jsonl`: la última fila `cost-state` trae `totalCostUSD` y `modelUsage` (entrada, salida, razonamiento, caché) de **toda la sesión, con subagentes incluidos** | `~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/transcript_full.jsonl` (tokens por paso); la ruta llega en los hooks (`transcriptPath`) |
| Coste | ✅ equivalente API (con suscripción no es un cargo real) | ❌ no se registra |
| Verificación | ✅ coincidencia exacta con `total_cost_usd` y `modelUsage` del resultado JSON (con y sin subagente) y funciona en sesiones interactivas | ✅ coincidencia exacta con `usage` del resultado JSON |
| Nota | El `usage` del resultado solo refleja el **último** turno; la fuente buena es `cost-state` | Los subagentes tienen su propia conversación (`conversation://<id>`) |

⚠️ Si el proceso hereda `CLAUDE_CODE_CHILD_SESSION` (p. ej. al lanzarse desde otra sesión de Claude Code), **no se guarda el transcript**. Agentic OS debe lanzar los CLIs con un entorno sin variables `CLAUDE*`.

Evidencia: [`p8-usage.md`](evidencias/p8-usage.md); parsers en `spikes/usage_probe.py` con tests.

## P9 · Hooks
| | Claude Code | agy |
|---|---|---|
| Por sesión | ✅ `--settings <json>` con `hooks` | ✅ `.agents/plugins/<x>/hooks.json` en la carpeta de trabajo |
| Eventos vistos | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop`, `SessionEnd` (+ `Notification`, `PermissionRequest`…) | `PreInvocation`, `PreToolUse`, `PostToolUse`, `PostInvocation`, `Stop` |
| Payload | JSON por stdin con `session_id`, `transcript_path`, `cwd`, `tool_name`… | JSON por stdin con `conversationId`, `toolCall {name, args}`, `transcriptPath`, `workspacePaths`… |
| Ejecución | — | ⚠️ por `cmd.exe`: las rutas entre comillas se rompen (hay que usar rutas sin espacios o un `.cmd` envolvente). **Un hook que falla bloquea la herramienta** |
| Efecto lateral | ⚠️ los hooks globales del usuario también se ejecutan, salvo con `--setting-sources project,local` | — |

## P10 · Subagentes nativos
| | Claude Code | agy |
|---|---|---|
| Detección | Herramienta `Agent` en `PreToolUse` + `SubagentStart`/`SubagentStop`; en stream-json, mensajes con `parent_tool_use_id` | `toolCall.name = invoke_subagent` en `PreToolUse` (con `Role`, `Prompt` y `Model`); tipo de paso `subagent` en stream-json |
| Transcript propio | `<session-id>/subagents/` | conversación propia (`conversation://<id>`) |

## P11 · Modo headless
| | Claude Code | agy |
|---|---|---|
| Comando | `-p "<prompt>" --output-format stream-json --verbose` | `-p "<prompt>" --output-format stream-json` |
| Eventos | `system/init` (herramientas, MCP, sesión), `assistant`, `user` (resultados de herramientas), `result` (coste, usage, denegaciones) | `init` (modelo, herramientas), `step_update` (tipo y estado), `result` (estado, respuesta, usage, `denied_actions`) |
| Sin TUI ni diálogos | ✅ | ✅ |
| Entrada continua | `--input-format stream-json` | `--input-format stream-json` |

→ El PTY es la base del producto (terminal real + «Tomar control»). El headless sirve para tareas sin intervención humana posible y como modo degradado (ADR 0003).

## P12 · Estado del CLI
| | Claude Code | agy |
|---|---|---|
| Ruta / versión | `where claude` · `claude --version` | `where agy` · `agy --version` |
| Sesión iniciada | `claude auth status` → JSON con `loggedIn`, `authMethod`, `configDirectory` | `agy models` lista los modelos (sin sesión falla) |
| Modelos | alias (`haiku`, `sonnet`, `opus`) o IDs completos | 14 modelos, incluidos Gemini 3.x, `claude-sonnet-4-6`, `claude-opus-4-6-thinking` y `gpt-oss-120b-medium` |

Evidencia: [`p12-cli-probe.json`](evidencias/p12-cli-probe.json).

---

## Requisitos que salen del spike para el adapter
1. **Entorno limpio**: lanzar los CLIs sin variables `CLAUDE*` heredadas.
2. **Claude aislado**: `--setting-sources project,local`, `--strict-mcp-config` + `--mcp-config` propio, `--permission-mode` explícito y `--session-id` generado por nosotros. El prompt va **antes** de las opciones variádicas (`--allowedTools <tools...>` se traga un prompt posicional que vaya detrás).
3. **agy por plugin de workspace**: `.agents/plugins/agentic-os/` con `mcp_config.json` (token en la URL), `hooks.json` (comandos sin comillas que nunca fallen) y `rules/AGENTS.md` con las instrucciones. En PTY, lanzar sin `-i`, esperar a que el MCP esté conectado y escribir el prompt.
4. **Diálogo de confianza**: automatizarlo en el PTY. En `agy` se acumulan entradas en `trustedWorkspaces`; con worktrees por tarea, conviene un directorio raíz de worktrees de confianza o limpiar las entradas al borrar el worktree.
5. **Permisos de nuestras propias herramientas MCP**: preaprobarlos (`--allowedTools mcp__agentic-os__*` en Claude; en `agy`, aprobar desde el PTY o en modo autónomo).
6. **Señales de estado**: hook `Stop` + estado del pie de la TUI; consumo desde el transcript (`cost-state` / `transcript_full.jsonl`).
7. **Servidor MCP**: validar el token de la ejecución en cada petición y limitar lo que puede hacer cada token.

## Pendiente o fuera de este spike
- SDK de Python de Antigravity (`google-antigravity`): alternativa para `agy` con `system_instructions` nativas. No se ha probado; queda como opción para la fase 04.
- Configuración aislada de Claude con `CLAUDE_CONFIG_DIR`: no hace falta, porque `--setting-sources` basta.
- Limpieza de `~/.claude.json`: las 5 entradas de proyecto de los sandboxes se limpian con `uv run python spikes/cleanup.py` cuando no haya ninguna sesión de Claude Code abierta.
