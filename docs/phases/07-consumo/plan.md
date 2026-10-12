# Fase 07: Consumo · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado

## Diseño

### Visión general
```
CLI escribe su transcript ──► hook (Stop / SessionStart…) trae la ruta ──► runs.transcript_path
        │
        ├─ fin de turno (Stop) ──► UsageReader.refresh(run) ──► columnas de consumo en runs ──► WS + API
        └─ fin de la ejecución ──► UsageReader.refresh(run, final=True)

Arranque ──► backfill en segundo plano de las ejecuciones terminadas sin consumo

Scheduler._fill ──► CliGate.blocked(cli)? ── límite diario superado │ «Cuota agotada» pendiente ──► no lanza
Pantalla del CLI ──► ScreenState.quota_notice() ──► Inbox «Cuota agotada» + tarea «Esperando humano» (quota)
```

### Parsers (`services/usage/`)
- `parsers.py`: el prototipo `spikes/usage_probe.py` pasa a código de producción.
  - `Usage` (dataclass): `input`, `output`, `thinking`, `cache_read`, `cache_creation`, `cost_usd | None`, `models: dict`, `source` (`cost-state`, `assistant-rows`, `transcript_full`).
  - `claude_usage(path)` y `agy_usage(path)`. Leen el archivo línea a línea, toleran líneas corruptas y campos desconocidos, y devuelven `None` si el archivo no existe o no tiene ninguna fila útil.
  - Lectura incremental para no releer transcripts largos en cada turno: se guarda el *offset* del último byte leído y el acumulado (`UsageCursor`). En Claude se busca la última `cost-state` desde el *offset*; si no aparece ninguna nueva, se mantiene la anterior. Si el archivo encoge (rotación o reescritura), se relee entero.
- `paths.py`: ruta calculada cuando no ha llegado ningún hook. Claude: `<config>/projects/<slug(cwd)>/<session>.jsonl`, con `CLAUDE_CONFIG_DIR` si está definido. agy: `~/.gemini/antigravity-cli/brain/<conversation>/.system_generated/logs/transcript_full.jsonl`.
- **Fixtures** en `backend/tests/fixtures/transcripts/`: transcripts reales recortados y anonimizados (Claude con y sin `cost-state` y con subagente; agy con subagente), con la versión del CLI en el nombre.

### Modelo (migración `0006`)
| Tabla | Cambio |
|---|---|
| `runs` | + `transcript_path`, `extra_transcripts` (JSON: transcripts de los subagentes nativos de agy), `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `cache_creation_tokens` (enteros, 0 por defecto), `cost_usd` (decimal, nulo = sin coste), `usage_models` (JSON), `usage_source`, `usage_status` (`pending` · `partial` · `final` · `unavailable`), `usage_read_at`, `cli_version` |
| `inbox_items` | `kind` admite `limit` y `quota` (se recrea el `CHECK` con `batch_alter_table`) |
| `app_state` | + `usage_limits` (JSON `{claude_usd, agy_tokens}`) |

- `WaitingReason.QUOTA` (la columna no tiene `CHECK`).
- `NotificationSettings` gana `limits: bool = True` (límites y cuota en un solo interruptor).
- Se guardan las cifras en `runs` (y no en una tabla aparte) porque todos los agregados parten de las ejecuciones y así se evitan *joins*. El cursor incremental vive en memoria; tras un reinicio se relee el archivo una vez.

### Lectura y actualización (`services/usage/reader.py`)
- `UsageReader.refresh(run_id, final=False)`:
  1. resuelve la ruta (`transcript_path` del hook, o la calculada) y la de los subagentes nativos de agy;
  2. lee, suma y guarda en `runs`; `usage_status` pasa a `partial` o `final` (o `unavailable` si `final` y no hay nada);
  3. publica el consumo por el WebSocket de la ejecución (mensaje `usage`) para la vista en vivo.
- Se llama desde un hilo propio (cola + *worker*), para no bloquear el hook ni el cierre: en `on_hook` con `Stop`, y en `_on_end` con `final=True`.
- **Momento de la `cost-state`**: si en la tarea 1 se ve que Claude la escribe después del `Stop`, el *worker* repite la lectura a los 2 s cuando no ha cambiado nada.
- **Ruta del transcript**: `interpret()` (`hooks.py`) extrae `transcript_path` (Claude) y `transcriptPath` (agy). La primera del run se guarda en `transcript_path`; en agy, las de conversaciones ajenas (subagentes nativos, que ya se detectan como `foreign`) van a `extra_transcripts`.
- **Versión del CLI**: la del `CliCatalog` en el momento del lanzamiento, en `runs.cli_version`.
- **Backfill**: al arrancar, un hilo recorre las ejecuciones terminadas con `usage_status = pending` y llama a `refresh(final=True)`, de una en una.

### Agregados (`services/usage/stats.py`)
- **Día de una ejecución**: el día local (zona horaria del sistema) de su `started_at`. Una ejecución que cruza la medianoche cuenta entera en el día en que empezó.
- **Horas de agente**: suma de `ended_at − started_at` (o `ahora − started_at` si sigue viva).
- Las consultas cargan las ejecuciones del periodo con sus columnas de consumo y agregan en Python: con cientos o pocos miles de ejecuciones es suficiente y evita depender de las funciones de fecha de SQLite. Se revisará en la fase 14 (Postgres).
- Funciones:
  - `summary(from, to, filtros)`: coste (solo filas con coste), tokens, % de caché, horas, sesiones, % sin error, y la variación del coste frente al periodo anterior de la misma longitud;
  - `daily(from, to, group)`: serie por día y por agente o proyecto (coste y tokens);
  - `breakdown(from, to, group)`: agente, proyecto o tarea, con coste, tokens y %;
  - `sessions(from, to, filtros, orden)` y su CSV;
  - `today()`: consumo de hoy, por agente, y el estado de los límites.
- **Tokens que cuentan**: entrada + salida + razonamiento + caché en «Tokens»; el % de caché es `cache_read / (entrada + cache_read + cache_creation)`. Para el límite de agy, solo entrada + salida + razonamiento (spec).

### Límites diarios y cuota (`services/usage/limits.py`)
- `CliGate.blocked(db, cli) -> str | None`: devuelve `limit` si el consumo de hoy de ese CLI llega a su límite, o `quota` si hay un elemento «Cuota agotada» pendiente de ese CLI.
- El scheduler lo consulta en `_fill` por agente (según su CLI) y no lanza si está bloqueado. Las tareas siguen en la cola.
- **Elemento «Límite diario alcanzado»** (`kind = limit`): uno por CLI y día, sin tarea, con el consumo y el límite. Lo crea el *housekeeping* del scheduler (cada minuto) o el `refresh` que hace cruzar el límite. Se resuelve solo (`dismissed`) al cambiar de día o al subir el límite, y en ese momento se hace `poke()` al scheduler.
- **Aviso del 80 %**: lo calcula `today()` y lo muestra el Dashboard; no crea elementos en la Inbox.
- **Lanzamiento manual** con el límite superado: se permite; la API devuelve el aviso en la respuesta y la UI lo muestra como toast.
- **Cuota agotada**:
  - `ScreenState.quota_notice() -> str | None`: el mensaje de cuota o de límite de uso al final de la pantalla, con sus patrones en `screen.py` (`QUOTA_PATTERNS[cli]`), a partir de los textos de la tarea 1;
  - `RunSession` lo comprueba en el *ticker* (como `_permission_step`) y llama a `on_quota(texto)` una vez por aparición;
  - el `RunManager` crea el elemento `quota` (con agente, proyecto, ejecución y el texto, que incluye la hora de reinicio si la da), pone la tarea en «Esperando humano» (`quota`) y registra un evento;
  - **Reanudar** (`POST /inbox/{id}/resume`): resuelve el elemento, devuelve la tarea a «En ejecución», hace `deliver(«continúa»)` si la ejecución vive y `poke()` al scheduler. Si la ejecución ya terminó, solo resuelve y desbloquea.

### API
| Ruta | Uso |
|---|---|
| `GET /usage/summary?from&to&agent_id&project_id` | KPIs del periodo |
| `GET /usage/daily?from&to&group=agent\|project` | Serie diaria apilada |
| `GET /usage/breakdown?from&to&group=agent\|project\|task` | Reparto (y «Consumo del mes» de Agentes, «Coste del mes» de Proyectos) |
| `GET /usage/sessions?from&to&agent_id&project_id&sort&dir&limit` | Tabla de sesiones |
| `GET /usage/sessions.csv?…` | Exportación |
| `GET /usage/today` | Bloque del Dashboard y estado de los límites |
| `GET/PUT /settings/usage-limits` | Límites diarios |
| `POST /inbox/{id}/resume` | Reanudar tras «Cuota agotada» |
| `RunRead` | + bloque `usage` (tokens, coste, fuente, estado, versión del CLI) |
| `TaskRead` | + `usage` total de sus ejecuciones (con hijas) |
| `POST /runs` | + `warning` si el límite del CLI está superado |

`from` y `to` son fechas locales (`YYYY-MM-DD`); por defecto, los últimos 30 días.

### UI
- **Dependencia nueva**: `recharts` (la recomienda el diseño). La tabla de sesiones se ordena con estado propio sobre el `Table` de shadcn, como el resto de tablas de la app (sin TanStack Table).
- `api/usage.ts`: clientes y tipos; `lib/format.ts`: `formatTokens` («1,33 M», «230,3 k») y `formatUsd` («2,84 $», «—»).
- **Consumo** (`/consumo`, `11-consumo`): cabecera con el segmentado 7 · 30 · 90 días; 4 KPIs; `DailyCostChart` (barras apiladas, segmentado Por agente · Por proyecto, tooltip «8 oct · 6,51 $»); «Reparto del periodo»; `SessionsTable` ordenable (clic en la fila → ejecución). Nota «Coste equivalente API» junto al KPI de coste. «Exportar CSV» en la cabecera (botón contextual ya previsto en `nav.ts`).
- **Dashboard**: tarjeta «Consumo de hoy» (KPIs, barras por agente, barras de los dos límites con el aviso del 80 %, «Ver detalle →»).
- **Detalle de tarea y página de ejecución**: panel «Consumo de la sesión» (rejilla 2×3 de `09a` + ID de sesión), en vivo con el mensaje `usage` del WebSocket. En la tarea, total y desglose por ejecución en el árbol.
- **Agentes**: «Consumo del mes» en la lista; Tokens y Coste en Historial. **Proyectos**: «Coste del mes» en Resumen; Coste en Tareas. **Ejecuciones**: Tokens y Coste.
- **Ajustes**: sección «Límites diarios» (USD de Claude, tokens de agy, con la nota de que la caché no cuenta) y el interruptor «Límites y cuota» en Notificaciones.
- **Inbox**: tipos `limit` (sin acciones; se resuelve solo) y `quota` («Reanudar» · «Abrir terminal»).
- Textos en `i18n/es.json`.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0006_usage.py` | nuevo |
| `backend/src/agentic_os/models/run.py`, `inbox.py`, `task.py`, `app_state.py` | columnas y valores nuevos |
| `backend/src/agentic_os/services/usage/` (`parsers.py`, `paths.py`, `reader.py`, `stats.py`, `limits.py`) | nuevo |
| `backend/src/agentic_os/services/hooks.py` | rutas de transcript en `HookEffect` |
| `backend/src/agentic_os/services/runs/manager.py`, `session.py`, `screen.py` | `refresh` en `Stop` y al cerrar, mensaje `usage`, `quota_notice`, `on_quota` |
| `backend/src/agentic_os/services/scheduler.py` | `CliGate` en `_fill`, elementos de límite en el *housekeeping* |
| `backend/src/agentic_os/services/inbox.py`, `api/inbox.py`, `schemas/inbox.py` | tipos `limit` y `quota`, `resume`, interruptor `limits` |
| `backend/src/agentic_os/api/usage.py`, `schemas/usage.py`; `api/runs.py`, `api/tasks.py`, `schemas/run.py`, `schemas/task.py` | nuevos / modificados |
| `backend/src/agentic_os/app.py` | *worker* de consumo y backfill al arrancar |
| `backend/tests/fixtures/transcripts/*`, `fixtures/screens/*quota*` | capturas reales |
| `backend/tests/fake_cli.py` | directivas `CONSUMO:` (escribe un transcript con el formato del CLI y lo anuncia en el hook) y `CUOTA:` (muestra el mensaje de cuota) |
| `backend/tests/test_usage_*.py`, `test_limits.py`, `test_quota.py` | nuevos |
| `frontend/package.json` | `recharts` |
| `frontend/src/api/usage.ts`, `lib/format.ts`, `pages/UsagePage.tsx` + `pages/usage/*`, `pages/DashboardPage.tsx`, `pages/SettingsPage.tsx`, `pages/runs/*`, `pages/tasks/*`, `pages/agents/*`, `pages/projects/tabs/*`, `pages/inbox/*`, `i18n/es.json` | nuevos / modificados |
| `docs/adr/0011-usage-and-limits.md` | nuevo |

## Tareas (en orden)
**C0 · Captura con los CLIs reales**
1. [ ] Transcripts reales de Claude (con subagente) y de agy (con subagente) como *fixtures*; comprobar cuándo escribe Claude la `cost-state` respecto al hook `Stop`; confirmar `transcript_path` / `transcriptPath` en los hooks de la versión actual.
2. [ ] Buscar los textos de cuota agotada de agy y de límite de uso de Claude: en pantalla, en el transcript y en la salida del modo headless (si se puede provocar, p. ej. con un modelo de cuota baja). Si no se consiguen reales, documentar los patrones esperados en el ADR y dejarlos centralizados en `screen.py`.

**C1 · Lectura del consumo**

3. [ ] `parsers.py` y `paths.py` con lectura incremental; tests con las *fixtures*.
4. [ ] Migración `0006` y modelos; `cli_version` y rutas de transcript desde los hooks.
5. [ ] `UsageReader` (*worker*, `Stop`, cierre, reintento), mensaje `usage` por WebSocket, subagentes nativos de agy, `RunRead`/`TaskRead`; backfill al arrancar; e2e con `CONSUMO:` del CLI falso.

**C2 · Agregados y API**

6. [ ] `stats.py` (días locales, periodo anterior, horas, % de caché y de éxito) y `api/usage.py` con el CSV; tests.

**C3 · Límites y cuota**

7. [ ] Ajustes de límites, `CliGate` en el scheduler, elementos `limit` (creación y resolución por día y por cambio de límite), aviso en el lanzamiento manual; tests.
8. [ ] `quota_notice`, `on_quota`, elemento `quota`, motivo `quota`, `resume`; directiva `CUOTA:`; e2e.

**C4 · UI**

9. [ ] `api/usage.ts`, formateadores y página Consumo (KPIs, gráfica, reparto, sesiones, CSV).
10. [ ] Consumo de hoy en el Dashboard, consumo de la sesión en tarea y ejecución, columnas en Agentes, Proyectos, Tareas y Ejecuciones.
11. [ ] Ajustes (límites y notificación) e Inbox (`limit` y `quota`).

**C5 · Cierre**

12. [ ] Pruebas manuales con los CLIs reales (CA1, CA2, CA4) con evidencias; ADR 0011, README, roadmap, `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_usage_parsers.py`: *fixtures* reales de Claude (`cost-state`, respaldo `assistant` sin duplicar, subagente) y agy (con subagente); líneas corruptas, campos desconocidos, archivo inexistente o vacío → `None`; lectura incremental y archivo que encoge | CA1, CA2, CA3 |
| `test_usage_reader.py`: rutas del hook frente a calculadas, `CLAUDE_CONFIG_DIR`, `partial` → `final` / `unavailable`, `extra_transcripts`, backfill, un fallo de lectura no rompe la ejecución | CA3, CA4, CA7 |
| `test_usage_e2e.py` (backend real + CLI falso con `CONSUMO:`): el consumo cambia en cada fin de turno, llega por el WebSocket y queda `final` al cerrar | CA4 |
| `test_usage_api.py`: KPIs, periodo anterior, serie diaria por agente y proyecto, reparto, sesiones ordenadas, filtros, CSV, días locales en el cambio de día, filas sin coste (agy) fuera del coste | CA5 |
| `test_limits.py`: el scheduler no lanza tareas del CLI que supera su límite y sigue con el otro; las ejecuciones vivas siguen; un elemento `limit` por CLI y día; se reanuda al subir el límite y al cambiar de día; aviso en el lanzamiento manual | CA6 |
| `test_screen.py` (ampliado) y `test_quota.py`: `quota_notice` con los textos de la tarea 2; `CUOTA:` → elemento, motivo `quota`, scheduler bloqueado para ese CLI; «Reanudar» lo deshace | CA6b |
| `test_migrations.py` (ampliado): `0006` sobre una base con datos de la fase 06 | CA9 |
| Frontend: formateadores; página Consumo (KPIs, cambio de periodo, agrupación, orden de la tabla, CSV); Dashboard con los límites y el 80 %; panel de la sesión en vivo; Ajustes de límites; Inbox `limit` y `quota` | CA8 |
| Pruebas manuales con Claude y agy reales, comparando con `/cost` y con el resultado JSON | CA1, CA2, CA4 |

## Decisiones (ADR)
**[ADR 0011](../../adr/0011-usage-and-limits.md) · Consumo y límites**:
- las cifras en columnas de `runs`, con lectura incremental del transcript desde un *worker*;
- la ruta del hook manda sobre la calculada; subagentes nativos de agy sumados a su ejecución;
- el día de una ejecución es el día local de su inicio;
- agregados en Python sobre las ejecuciones del periodo;
- límites por CLI (USD en Claude, tokens sin caché en agy) que solo frenan al scheduler;
- la cuota agotada, detectada en pantalla, como elemento de la Inbox que bloquea al CLI hasta «Reanudar».
