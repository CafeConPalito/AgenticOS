# Fase 04: Adapters y MCP · Validación

- **Rama**: `phase/04-adapters-mcp`
- **Fecha**: 2026-10-10

## Tests automáticos
`scripts/check.ps1`:

```
Step                            Result
----                            ------
Lint backend (ruff)             OK
Lint frontend (eslint+prettier) OK
Lint desktop (rustfmt)          OK
Lint spikes (ruff)              OK
Tests backend (pytest)          OK  121 passed  (+27 en esta fase)
Tests frontend (vitest)         OK   52 passed  (+2 en esta fase)
Tests desktop (cargo test)      OK    3 passed
Tests spikes (pytest)           OK   15 passed
```

**CLI falso**: el `fake_cli.py` usa lo mismo que un CLI real:
- en modo Claude lee `--mcp-config`/`--settings`; en modo agy lee el plugin del workspace;
- ejecuta los `hook.cmd` reales (con `curl`);
- habla con el MCP con el cliente oficial;
- en modo agy conecta el MCP solo con `/mcp`, como agy, y muestra su diálogo de permiso.

`test_runs_mcp.py` lo ejecuta contra un backend real (uvicorn) en un ConPTY real.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | **Claude Code real**: instrucciones y memoria del proyecto; `report_status`, `write_project_memory` y `complete_task` llegan a la BD; acaba «Completada» con resumen y cierra solo | ✅ | Claude Code 2.1.296 (`haiku`), agente en «Preguntar»: empieza con «Soy Dev (ask), de Agentic OS.» (sus instrucciones) y responde «pnpm» (la memoria). Llama a las tres herramientas y termina `completed`, código 0, con resumen. Eventos: inicio de sesión → MCP conectado → inicio de turno → las tres herramientas → cierre → fin de turno → fin de sesión. [`claude-context.json`](evidencias/claude-context.json), [`claude-context.screen.txt`](evidencias/claude-context.screen.txt), [captura](evidencias/ca1-ca7-claude-completada.jpg). Tests: `test_claude_reports_completes_and_closes_by_itself`, `test_mcp_server.py`, `test_context.py` |
| CA2 | **agy real**: lo mismo por el plugin; prompt tras conectar el MCP; el plugin desaparece al terminar y git no lo ve | ✅ | agy 1.3.3: `mcp_probe` → `mcp_connected` → `prompt_sent`. Sigue sus instrucciones («Soy Gema…»), usa la memoria, llama a las tres herramientas (diálogos aprobados por el backend) y termina `completed`, código 0. Sin plugin al terminar y `git status` limpio. [`agy-context.json`](evidencias/agy-context.json), [`agy-context.screen.txt`](evidencias/agy-context.screen.txt), [captura](evidencias/ca2-ca7-agy-completada.jpg). Tests: `test_agy_gets_its_prompt_after_mcp_and_our_dialogs_are_approved`, `test_adapters.py` |
| CA3 | **Permisos**: los tres modos se traducen; Claude en «Preguntar» pide permiso aunque la configuración global diga `auto`; en «Autónomo» no | ✅ / ⚠️ | Tests de argv y plugin por modo (`test_claude_permission_modes`, `test_agy_starts_without_the_prompt`). Con los CLIs reales: **Claude «Preguntar»** pide permiso para crear el archivo y no lo crea ([`claude-ask.screen.txt`](evidencias/claude-ask.screen.txt)), aunque la configuración global dice `defaultMode: auto`. **Claude «Autónomo»**: la primera vez Claude Code pide aceptar el modo `bypassPermissions` ([`claude-autonomous.screen.txt`](evidencias/claude-autonomous.screen.txt)). Agentic OS no lo acepta por el usuario: registra `waiting_for_human` y la UI pide tomar el control (ver retro). **agy «Autónomo»** crea el archivo sin preguntar. **agy «Preguntar»** también lo crea sin preguntar: es la política de agy, que en su modo por defecto permite editar en el workspace y solo pide permiso para comandos ([`agy-ask.screen.txt`](evidencias/agy-ask.screen.txt)) |
| CA4 | **Seguridad del MCP**: token por ejecución; 401 para un token desconocido o caducado; un token no toca otra ejecución | ✅ | `test_unknown_or_revoked_tokens_are_rejected`, `test_a_token_only_acts_on_its_own_run` (también con la cabecera interna falsificada), `test_bearer_header_works_like_the_path_token`; y el token de una ejecución terminada da 401 en `test_claude_reports_completes_and_closes_by_itself` |
| CA5 | **Hooks**: fin de turno → «Esperando», inicio → «Trabajando»; agy guarda su `conversationId`; con el backend caído el hook sale con 0 | ✅ | `test_hooks.py`: el `hook.cmd` real llega al backend desde una carpeta con espacios y sale con 0 en menos de 6 s con el backend caído. Interpretación por CLI y `conversationId`. Con los CLIs reales: los hooks aparecen en los eventos de las dos ejecuciones y agy guarda su `cli_session_id` |
| CA6 | **Configuración del usuario intacta** | ✅ | Comparación antes y después de las seis ejecuciones reales (`ConfigSnapshot` del spike). `~/.claude/settings.json` y los servidores MCP de `~/.claude.json` no cambian. En agy cambian dos cosas que no configura Agentic OS: su historial de prompts (`history.jsonl`) y `trustedWorkspaces` con la carpeta del proyecto, como ya preveía el ADR 0004. En el proyecto solo quedan los archivos que se pidió crear y la línea de `.git/info/exclude` |
| CA7 | **UI**: «Eventos MCP» en vivo y persistido; último estado, resumen y «Completada», fieles a `09a` | ✅ | `runs.test.tsx` (eventos guardados y un `complete_task` en vivo por el WebSocket que actualiza el resumen; «Completada»). Capturas de las ejecuciones reales de [Claude](evidencias/ca1-ca7-claude-completada.jpg) y de [agy](evidencias/ca2-ca7-agy-completada.jpg): columna derecha de eventos con hora, función y argumento, como en `09a` |
| CA8 | Una segunda ejecución de agy en la misma carpeta se rechaza; un plugin huérfano se limpia al arrancar | ✅ | `test_one_agy_run_per_folder` (409 `agy_folder_busy`), `test_recover_removes_a_plugin_left_by_a_crash`, `test_cleanup_only_removes_our_own_plugin` |
| CA9 | `check` en verde; ADR, README y roadmap | ✅ | Salida de arriba; [ADR 0008](../../adr/0008-agent-coordination.md); README (contexto, MCP y la API para los agentes); roadmap. **Sidecar empaquetado**: las ejecuciones de Claude y agy (CLI falso) terminan `completed` con MCP, hooks y memoria, y sin restos del plugin |

## Code review
`/code-review high` sobre `main...phase/04-adapters-mcp`: _pendiente_.

## Incidencias durante el desarrollo
Las pruebas con los CLIs reales encontraron cuatro cosas que ni el spike ni el CLI falso habían mostrado. Todas tienen ya un test con textos reales:

1. **agy conecta el MCP de los plugins de forma perezosa**: solo al abrir `/mcp` o al empezar el modelo. Sin eso, la ejecución esperaba una conexión que no llegaba. Ahora la sesión escribe `/mcp` cuando la entrada está lista, espera la conexión, cierra el panel y escribe el prompt.
2. **agy deja dibujado el diálogo de confianza ya respondido** encima de su TUI, y la sesión creía que seguía abierto. Ahora los diálogos solo cuentan si están al final de la pantalla.
3. **Claude Code en «Autónomo» pide un consentimiento la primera vez.** Se decidió no responderlo nunca por el usuario: la ejecución lo avisa.
4. **En agy, «Preguntar» no pregunta al editar archivos** (política de agy). Queda documentado.

Otras:
- **Ningún archivo de proyecto ni de plugin preaprueba herramientas MCP en agy** (tarea 1, cinco candidatos probados con agy real). Se aplicó el plan B: el backend aprueba desde la pantalla solo los diálogos de nuestras herramientas.
- En los tests con `TestClient`, cada hook del CLI falso tardaba ~2 s: en Windows, conectar con un puerto cerrado tarda en ser rechazado. Ahora esos tests usan un receptor local que responde 404 al momento.
- El primer Ctrl+C de una parada puede perderse si llega mientras el CLI ejecuta un hook. Los reintentos de la parada lo cubren.
- PyInstaller no podía recoger todo `mcp`: `mcp.cli` necesita `typer`. Se recogen `mcp.server` y `mcp.shared`.
- Los heredocs del entorno siguen estropeando `\n` y `\x03`; esos cambios se hicieron con el editor.

## Retro
### Cambios respecto a la spec y al plan
- **Plan B en agy** (aprobación desde la pantalla) y **sondeo con `/mcp`** antes del prompt, en lugar de esperar a que el MCP conectara solo.
- **Prompt de varias líneas en agy**: se escribe la primera línea, y la tarea completa va a las reglas del plugin.
- **Evento `waiting_for_human`** para los diálogos que solo debe responder el usuario.
- **Las ejecuciones terminadas se reproducen al tamaño en que se dibujaron** (antes se ajustaban al panel y la TUI salía descolocada).

### Impacto en fases futuras
- **Fase 05**:
  - el scheduler puede usar `completed` + `summary`, y la ejecución cerrada sola, como señal de tarea terminada;
  - la memoria escrita por los agentes ya existe; falta resumirla;
  - con workspaces de tipo worktree, el plugin de agy irá dentro del worktree y no hará falta `.git/info/exclude`.
- **Fase 06**: `waiting_for_human` es el embrión de `request_human` y la Inbox.
- **Fase 07**: los hooks ya traen la ruta del transcript de cada CLI.

## Comprobaciones pendientes del usuario
- Aceptar una vez, con «Tomar control», el aviso de Claude Code al lanzar un agente «Autónomo».
- Las pendientes de fases anteriores (app instalada: cerrar con una ejecución activa; «Examinar…»; F5 en una subruta; `cleanup.py --claude`).

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.5`
- [ ] `docs/roadmap.md` actualizado
