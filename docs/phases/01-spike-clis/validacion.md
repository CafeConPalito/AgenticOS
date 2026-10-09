# Fase 01: Spike de CLIs · Validación

- **Rama**: `phase/01-spike-clis`
- **Fecha**: 2026-10-09

## Tests automáticos
`scripts/check.ps1` (incluye ahora `spikes/`):

```
Step                            Result
----                            ------
Lint backend (ruff)             OK
Lint frontend (eslint+prettier) OK
Lint desktop (rustfmt)          OK
Lint spikes (ruff)              OK
Tests backend (pytest)          OK   10 passed
Tests frontend (vitest)         OK   14 passed
Tests desktop (cargo test)      OK   3 passed
Tests spikes (pytest)           OK   15 passed
```
Tests de `spikes/`: snapshot de configuración (2), servidor MCP con tokens (3), parser de diálogos de permiso de agy (4) y parsers de consumo con fixtures reales anonimizadas (6).

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | `spike.md` responde P1–P12 para los dos CLIs con estado, mecanismo y evidencia | ✅ | [`spike.md`](spike.md): matriz resumen + una sección por pregunta con enlaces a [`evidencias/`](evidencias/) |
| CA2 | `pty_run.py` lanza los dos CLIs en ConPTY con prompt inicial, salida en vivo, escritura desde fuera y log | ✅ | [`p1-claude-pty.md`](evidencias/p1-claude-pty.md) y [`p1-agy-pty.md`](evidencias/p1-agy-pty.md) (capturas de pantalla en texto por paso) + `*.raw.log` |
| CA3 | Los dos CLIs llaman a `report_status` y `complete_task` con configuración solo para esa ejecución; la configuración global no cambia | ✅ | Claude headless y PTY: [`p5-claude-mcp.md`](evidencias/p5-claude-mcp.md). agy headless: [`p5-agy-mcp.md`](evidencias/p5-agy-mcp.md); agy PTY: [`p5-agy-mcp-connected.md`](evidencias/p5-agy-mcp-connected.md). Las llamadas llegan con el token de cada ejecución (`*-calls.jsonl`) y `config_guard` informa «UNCHANGED» en todos los escenarios de MCP |
| CA4 | Documentado qué hacen Esc y Ctrl+C en cada CLI, con semántica propuesta de «Tomar control / Pausar» | ✅ | `spike.md` §P3 + [ADR 0003](../../adr/0003-execution-mode.md) |
| CA5 | `usage_probe.py` obtiene el consumo de una sesión de cada CLI y coincide con lo que reporta el CLI | ✅ | [`p8-usage.md`](evidencias/p8-usage.md): coincidencia exacta en coste y tokens (Claude, con y sin subagente) y en tokens (agy). También funciona en sesiones interactivas |
| CA6 | Decisiones registradas en ADRs y roadmap actualizado | ✅ | [ADR 0003](../../adr/0003-execution-mode.md), [ADR 0004](../../adr/0004-per-run-context-and-mcp.md), [ADR 0005](../../adr/0005-usage-source.md); [`roadmap.md`](../../roadmap.md) (fases 03, 04, 05 y 07) |

## Configuración global del usuario
- Todos los escenarios corrieron dentro de `config_guard`, que compara `~/.claude.json` (servidores MCP), `~/.claude/settings.json` y `~/.gemini/` (sin el estado de ejecución) antes y después.
- **Cambios detectados, todos de confianza en carpetas** al aceptar el diálogo en modo interactivo: `trustedWorkspaces` de `agy` y `projects` de `~/.claude.json`. Ningún escenario añadió MCP, hooks ni permisos globales.
- **Limpieza**:
  - Las 5 entradas de sandbox en `trustedWorkspaces` de `agy` se eliminaron con `spikes/cleanup.py`, con copia de seguridad en `%LOCALAPPDATA%\AgenticOS-spike\backup\`.
  - Las entradas de proyecto de `~/.claude.json` siguen ahí, porque ese archivo lo reescribe la sesión de Claude Code en curso. Se limpian con `uv run --project spikes python spikes/cleanup.py --claude` cuando no haya ninguna sesión abierta (el script se niega si Claude Code está en ejecución).
- **Proceso huérfano**: una de las primeras ejecuciones (sin `--strict-mcp-config`) arrancó el MCP global `godot_ai` del usuario, que quedó vivo escuchando en 8001/8002. No se ha cerrado porque podría estar en uso; el usuario decide.

## Code review
`/code-review high` sobre `main...phase/01-spike-clis`:

| Hallazgo | Severidad | Resolución |
|---|---|---|
| `agy_mcp_connected`: la aprobación miraba toda la pantalla y el prompt visible contiene «agentic-os», así que podía aprobar comandos de shell | Alta | **Corregido**: `agy_permission_request()` lee solo el diálogo («Allow calling this tool?» → nombre de la herramienta; «Run this command?» → comando) y `approve_only_agentic_os()` rechaza todo lo que no sea nuestro MCP; 4 tests con pantallas reales. Se comprobó que las dos aprobaciones de la evidencia original eran diálogos MCP auténticos. Al repetir el escenario apareció un caso real (línea en blanco entre nombre y pregunta), que se corrigió y se añadió como test. Se aplica también en `agy_mcp` y `agy_mcp_pretrusted`, que aprobaban cualquier diálogo (en `pretrusted` llegó a aprobar `Get-ChildItem` dentro del sandbox, documentado) |
| `context_perms`: un CLI que falla contaba como «permiso denegado» | Alta | **Corregido**: el caso exige `rc=0` + JSON y, si no se espera el archivo, una denegación registrada o una respuesta del agente. Repetida la batería: todos los casos con `rc=0`, conclusiones intactas, y un hallazgo nuevo (vetar `Write` en `bypassPermissions` no impide escribir por la shell), añadido al spike |
| `cli_probe`: «Not logged in» contaba como sesión iniciada | Media | **Corregido**: se parsea el JSON de `claude auth status` (`loggedIn`) |
| `clean_env` quitaba toda variable `CLAUDE*`, incluida configuración real (`CLAUDE_CODE_GIT_BASH_PATH`, Bedrock/Vertex…) | Media | **Corregido**: lista explícita de marcadores de sesión (`SESSION_MARKERS`) |
| `ConfigSnapshot.take` podía lanzar con archivos a medio escribir, dentro del `finally` del guard | Media | **Corregido**: reintentos, «unreadable» como valor y el guard nunca tapa el resultado del escenario |
| `cleanup.py` reescribía `~/.claude.json` sin atomicidad y con Claude Code abierto | Media | **Corregido**: escritura atómica (`os.replace`) y se niega a actuar si el CLI correspondiente está en ejecución (`--agy` / `--claude`) |
| `usage_probe`: un `null` en los contadores provocaba un `TypeError` | Media | **Corregido**: `_n()` trata ausente y `null` como 0; test añadido |
| `claude_mcp` / `usage`: `json.loads` sin protección ante salida no JSON | Media | **Corregido**: `run_cli()` común, que nunca lanza por salida no JSON y expone `rc`, `stderr` y eventos |
| Código duplicado (bucles de confianza, ejecución de subprocesos) | Baja | **Corregido**: `accept_trust()` en `pty_run` y `run_cli()` en `common`, usados por todos los escenarios. Repetidos `claude_pty` y `agy_pty` con éxito |
| `test_spike_mcp` importaba `httpx2` sin declararlo | Baja | **Corregido**: el test usa el cliente MCP con la URL de token en ruta, y `httpx` (declarado) para la cabecera Bearer y los 401 |
| `roadmap.md` enlazaba `validacion.md` sin estar committeado | Baja | **Corregido** en el commit de validación |

## Incidencias durante el spike
- **Variables `CLAUDE*` heredadas**: las primeras ejecuciones heredaban las variables de la sesión de Claude Code que dirigía el spike, lo que desactivaba los transcripts. Se corrigió con `clean_env()`; está documentado como requisito del adapter.
- **Diálogo de confianza**: las teclas enviadas antes de que el menú esté activo se pierden; hay que reintentar hasta ver la opción seleccionada.
- **Prompt tragado por `--allowedTools`**: las opciones variádicas de Claude se comen el prompt posicional que va detrás.
- **Hooks de agy entre comillas**: `cmd.exe` rompe las rutas entre comillas, y un hook que falla bloquea la herramienta.
- **MCP de agy en PTY**: conecta de forma asíncrona; hay que esperar antes del prompt. Un modelo sin las herramientas improvisó llamadas HTTP con un script. Requisito: el token solo da acceso a su propia ejecución.
- **Test en rojo committeado** (`45673ec` lo corrige): una tubería `pytest | tail` ocultó el código de salida. Lección: no encadenar pytest con `| tail` en comandos de verificación.

## Retro
### Cambios respecto a la spec y al plan
- **Prueba adicional**: verificar que `agy` carga las reglas de `plugins/<x>/rules/AGENTS.md`, para respaldar el ADR 0004.
- **`cleanup.py`** (no previsto): devuelve la configuración a su estado tras el spike.
- **Los snapshots de `~/.claude.json`** comparan solo los `mcpServers` (globales y por proyecto): el archivo cambia en cada arranque por contadores y cachés.
- **No se ha probado el SDK de Python de Antigravity**: queda anotado como opción en la fase 04.

### Impacto en fases futuras
- **Fase 03**: PTY + Esc para «Tomar control», aceptación automática de la confianza en la carpeta y estado desde el pie de la TUI.
- **Fase 04**: adapters según el ADR 0004; servidor MCP con validación de token; entorno limpio; evaluar el SDK de Antigravity.
- **Fase 05**: con carpeta directa, una sola ejecución de `agy` por carpeta.
- **Fase 07**: consumo desde transcripts (ADR 0005); el coste de Claude se presenta como equivalente API y `agy` solo muestra tokens.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.2`
- [ ] `docs/roadmap.md` actualizado
