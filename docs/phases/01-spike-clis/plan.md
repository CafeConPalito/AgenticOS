# Fase 01: Spike de CLIs · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-09)
- **Rama**: `phase/01-spike-clis`

## Diseño

### Estructura
```
spikes/                      # proyecto uv independiente: no contamina el backend
  pyproject.toml             # pywinpty, pyte, mcp, httpx (+ pytest, ruff)
  common.py                  # sandbox, snapshot/diff de configuración, utilidades de log
  pty_run.py                 # P1–P3: CLI en ConPTY, salida en vivo, escritura, resize, Esc/Ctrl+C
  spike_mcp.py               # P5: servidor MCP HTTP local (report_status, complete_task), log JSONL
  usage_probe.py             # P8: consumo por sesión (transcripts, stream-json, BD local)
  cli_probe.py               # P12: versión, sesión iniciada, modelos
  scenarios/                 # un script por experimento: claude_*.py, agy_*.py
  tests/                     # tests de parsers con fixtures reales (anonimizadas)
docs/phases/01-spike-clis/
  spike.md                   # matriz P1–P12 × CLI con evidencias
  evidencias/                # logs, capturas de pantalla de texto, diffs
docs/adr/0003-*.md …         # decisiones que salgan
```
`spikes/` queda en el repo como referencia para las fases 03, 04 y 07, pero no se importa desde la app.

### Reglas de seguridad y coste
- **Sandbox**: cada experimento corre en `%LOCALAPPDATA%\AgenticOS-spike\sandbox\<escenario>`, una carpeta nueva con un `README.txt` de prueba. Nunca sobre el repo ni sobre carpetas del usuario. Los modos sin permisos solo se usan ahí.
- **Coste**: Claude con `--model haiku` y `--max-budget-usd 0.25` cuando el modo lo admita; `agy` con `gemini-3.8-flash-low`. Prompts de una línea («crea hola.txt con la palabra hola», «responde OK»).
- **Configuración global intacta**: `common.snapshot_config()` guarda un hash y una copia antes y después de cada escenario de:
  - Claude: `~/.claude.json`, `~/.claude/settings.json`;
  - agy: todo `~/.gemini/` excepto caches, logs y conversaciones.

  Si algo cambia, el escenario falla y se muestra el diff. Si un experimento necesita tocar la configuración global (plan B de `agy`), se hace con copia de seguridad y restauración automática, y se documenta.

### Prototipos
**`pty_run.py`** (P1, P2, P3, P11):
- `PtyProcess.spawn(argv, cwd, env, dimensions=(cols, rows))` de pywinpty, con un hilo lector que escribe los bytes crudos en `<escenario>.raw.log` y alimenta un emulador `pyte` para hacer *snapshots* de la pantalla en texto (evidencia legible).
- API: `send(text)`, `send_key("esc" | "ctrl_c" | "enter")`, `resize(cols, rows)`, `wait_idle(seconds)` (sin salida durante N segundos), `snapshot()`.
- Escenarios:
  - (a) arrancar con prompt inicial y esperar la respuesta;
  - (b) escribir un segundo prompt desde fuera;
  - (c) Esc a mitad de un turno largo y después «continúa»;
  - (d) Ctrl+C una y dos veces;
  - (e) redimensionar;
  - (f) comparar con `-p --output-format stream-json`.

**`spike_mcp.py`** (P5, P9 parcial):
- `FastMCP` del SDK `mcp` con transporte *streamable HTTP* en `127.0.0.1:<puerto libre>/mcp`.
- Cada ejecución lleva un token: en la cabecera `Authorization: Bearer <run-token>` y, si el CLI no admite cabeceras, en la ruta `/mcp/<run-token>`.
- Herramientas `report_status(message)` y `complete_task(summary)`. Cada llamada se añade a `mcp-calls.jsonl` con token, herramienta, argumentos y hora.
- Inyección por sesión:
  - **Claude**: `--mcp-config <archivo temporal>` con `{"mcpServers":{"agentic-os":{"type":"http","url":…,"headers":{…}}}}` y `--strict-mcp-config`.
  - **agy**, por orden:
    1. Buscar un archivo de configuración a nivel de workspace (inspeccionar `~/.gemini/antigravity-cli`, `agy help`, la skill integrada `antigravity_guide` y `agy-customizations`).
    2. Directorio de configuración aislado mediante variable de entorno (HOME / USERPROFILE / variable propia) apuntando a una copia mínima.
    3. Plan B: `agy mcp add` con un nombre único por ejecución y `agy mcp remove` al terminar, con backup y restauración, documentando el impacto.

**`usage_probe.py`** (P8):
- Claude: leer el transcript `~/.claude/projects/<slug-del-cwd>/<session-id>.jsonl` (campo `message.usage` de cada respuesta) y compararlo con `total_cost_usd` y `usage` de `-p --output-format json` para el mismo prompt. Con `--session-id <uuid>` fijado sabemos qué archivo leer.
- agy: explorar `--output-format json/stream-json`, `~/.gemini/antigravity-cli/conversations/`, `conversation_summaries.db` (SQLite, solo lectura) y los logs (`--log-file`), y localizar dónde aparecen tokens y modelo.

**`cli_probe.py`** (P12): `--version`, detectar si hay sesión iniciada (Claude: archivo de credenciales o `claude auth status` si existe; agy: `agy models` y el error «not logged in» del log) y lista de modelos.

### Hooks y subagentes (P9, P10)
- Claude: `--settings <json temporal>` con hooks `Stop`, `Notification`, `PreToolUse`/`PostToolUse` (matcher `Task`) y `SubagentStop`, que ejecutan un script que añade el evento a un JSONL. Sin tocar `~/.claude/settings.json`.
- agy: buscar un mecanismo equivalente (plugins, `agy-customizations`) y documentar si no existe.

## Archivos
| Archivo | Cambio |
|---|---|
| `spikes/**` | nuevos (prototipos, escenarios y tests) |
| `docs/phases/01-spike-clis/spike.md`, `evidencias/**` | nuevos |
| `docs/adr/0003-*.md` (y siguientes según hallazgos) | nuevos |
| `package.json`, `scripts/check.ps1` | lint y tests de `spikes/` dentro de `check` |
| `docs/roadmap.md`, `docs/vision.md` | ajustes según los hallazgos |

## Tareas (en orden, cada una en su commit)
1. [ ] Rama, proyecto uv `spikes/`, `common.py` (sandbox, snapshot/diff de configuración), `cli_probe.py` → P12.
2. [ ] `pty_run.py` + escenarios a–e con Claude → P1–P3.
3. [ ] Escenarios a–e con agy → P1–P3.
4. [ ] Modo headless (`-p` + stream-json) en ambos → P11; comparación con el PTY.
5. [ ] Contexto e instrucciones (P4) y permisos (P6) en ambos, en el sandbox.
6. [ ] `spike_mcp.py` + inyección en Claude → P5 (Claude), con diff de configuración.
7. [ ] Inyección de MCP en agy (vías 1 → 2 → 3) → P5 (agy).
8. [ ] Sesiones y reanudación (P7) y hooks y subagentes (P9, P10).
9. [ ] `usage_probe.py` + tests de parsers con fixtures → P8 en ambos.
10. [ ] `spike.md` completo, ADRs, ajustes del roadmap y `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `tests/test_usage_claude.py`: parser de transcript con fixture real (anonimizada) → totales correctos | CA5 |
| `tests/test_usage_agy.py`: ídem con la fuente que se encuentre | CA5 |
| `tests/test_spike_mcp.py`: cliente MCP de prueba → `report_status` queda en el JSONL con su token; token inválido → 401 | CA3 |
| `tests/test_config_snapshot.py`: el snapshot detecta un archivo modificado | CA3 |
| Ejecuciones reales de los escenarios con logs y snapshots en `evidencias/` | CA1, CA2, CA4 |

## Decisiones (ADR) previstas
- **0003: Modo de ejecución** (PTY interactivo, headless o híbrido) y semántica de «Tomar control / Pausar».
- **0004: Inyección de contexto y MCP por CLI** (incluida la solución para `agy`).
- **0005: Fuente de consumo por CLI**.
(Se crean solo las que aporten una decisión real.)

## Riesgos
- **Escenarios de la TUI que no se pueden automatizar**: si una TUI necesita interacción (p. ej. aceptar la confianza en la carpeta), se automatiza enviando teclas y se documenta como requisito del adapter.
- **Coste de la exploración**: lo marca el número de escenarios (unos 30 prompts mínimos en total).
- **Formatos internos no documentados** (transcripts, SQLite de `agy`): pueden cambiar entre versiones. Se registra la versión y el ADR lo trata como dependencia frágil.
