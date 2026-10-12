# Fase 07: Consumo · Validación

- **Rama**: `phase/07-consumo`
- **Fecha**: 2026-10-12

## Tests automáticos
`scripts/check.ps1`:

```
Step                                Result
----                                ------
Lint backend (ruff)                 OK
Lint frontend (eslint+prettier+tsc) OK
Lint desktop (rustfmt)              OK
Lint spikes (ruff)                  OK
Tests backend (pytest)              OK  253 passed  (+42 en esta fase)
Tests frontend (vitest)             OK   74 passed  (+10 en esta fase)
Tests desktop (cargo test)          OK    3 passed
Tests spikes (pytest)               OK   15 passed
```

Tests nuevos:
- **Backend**:
  - `test_usage_parsers.py`: *fixtures* **reales** de Claude Code 2.1.296 (con y sin `cost-state`, con subagente) y agy 1.3.3 (con subagente); filas corruptas o desconocidas; lectura incremental y archivo que encoge;
  - `test_usage_reader.py`: *status line* → `assistant-rows` → `cost-state`; cierre brusco; ruta calculada con `CLAUDE_CONFIG_DIR`; subagentes de agy; backfill; reintento sin bloquear el *worker*; parada ordenada;
  - `test_usage_stats.py`: días locales, KPIs, serie diaria, reparto, sesiones, CSV, límites por CLI, el scheduler frena solo el CLI afectado, cuota en pantalla (textos y falsos positivos), «Reanudar» y regresiones del code review;
  - `test_usage_api.py`, `test_migration_0006.py`, `test_usage_e2e.py` (CLI falso en una ConPTY real: consumo en vivo y final en los dos modos, coste en vivo de la *status line*, aviso al lanzar por encima del límite, cuota agotada y «Reanudar» en los dos CLIs);
  - `test_hooks.py` y `test_adapters.py` ampliados (rutas de transcript, *status line*).
- **Frontend**: `format.test.ts` y `usage.test.tsx` (página Consumo, orden y periodo, CSV, «Consumo de hoy» con avisos, límites en Ajustes, «Cuota agotada» y «Límite diario» en la Inbox).

**CLI falso**: directivas `CONSUMO: n` (escribe el transcript en el formato de cada CLI, refresca la *status line* y, en Claude, escribe `cost-state` al cerrar) y `CUOTA:` (el aviso de cuota del CLI).

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Claude real: coste y tokens coinciden con el CLI | ✅ | **Claude Code 2.1.296** (`haiku`) con un subagente `Agent`: Agentic OS guarda 0,010201325 $ y 1754 · 1819 · 264 785 · 43 264 tokens (entrada · salida · caché lectura · caché escritura), **idénticos** a la fila `cost-state` que escribe el propio Claude, leída aparte sin nuestros parsers. [Evidencia](evidencias/ca1-ca4-clis-reales.json). La correspondencia `cost-state` = `total_cost_usd` del resultado JSON se verificó en el spike (P8) |
| CA2 | agy real: tokens coinciden, coste «—» | ✅ | **agy 1.3.3** con `invoke_subagent`: 101 935 de entrada · 3 233 de salida · 14 374 de caché = suma de su `transcript_full.jsonl` (78 074 · 2 289) **más el de su subagente** (23 861 · 944). Coste nulo, que se muestra «—». La equivalencia transcript = `usage` del resultado JSON se verificó en el spike (P8) |
| CA3 | Parsers con *fixtures* reales, respaldo, filas desconocidas, transcript inexistente | ✅ | `test_usage_parsers.py` |
| CA4 | En vivo por turno y fijo al terminar | ✅ | **Real** (Claude): el coste subió con cada *status line* (0 → 0,0031 → 0,0066 → … → 0,0102 $) y los tokens con cada fin de turno; al cerrar, `final` con `cost-state`. agy: `partial` → `final`. e2e `test_usage_goes_live_then_final[claude, agy]` y `test_claude_live_cost_from_the_status_line` |
| CA5 | Agregados por periodo, agente y proyecto en días locales; CSV | ✅ | `test_usage_stats.py` (zona UTC+2 con ejecuciones a las 00:30 y 23:30), `test_usage_api.py` |
| CA6 | Límites diarios por CLI | ✅ | `test_the_scheduler_skips_the_cli_over_its_limit` (Claude frenado, agy sigue; reanuda al subir el límite), `test_limits_block_per_cli_and_resolve_by_themselves` (un elemento por CLI y día; se resuelve al subir el límite y al cambiar de día), aviso al lanzar a mano (e2e). **Real**: con límites 0,012 $ y 100 000 tokens, el Dashboard avisó del 85 % en Claude y del límite de agy, y la Inbox recibió «Límite diario de Antigravity alcanzado» ([captura](evidencias/ca8-dashboard-limites.jpg)) |
| CA6b | Cuota agotada | ✅ / ⏳ | e2e `test_out_of_quota_waits_for_the_person[agy, claude]`: elemento, «Esperando humano» (`quota`), CLI bloqueado y «Reanudar» (la tarea sigue y el agente recibe «continúa»). Tests de pantalla con los textos de los binarios y falsos positivos. **No se ha podido ver una cuota agotada real**: los patrones pueden necesitar ajustes cuando aparezca (ADR 0011) |
| CA7 | Ejecuciones anteriores con su consumo | ✅ | `test_backfill_reads_finished_runs_never_read`; al arrancar, el backend lee las terminadas en `pending`/`partial` |
| CA8 | UI fiel a `11-consumo`, `01a`, `09a`; columnas; límites en Ajustes | ✅ | Tests de componentes y [captura de Consumo](evidencias/ca8-consumo.jpg) con los datos reales. Gráfica: colores de identidad del agente o proyecto (los elige el usuario) con codificación secundaria (leyenda en «Reparto», tooltip con nombres, 2 px entre segmentos y la tabla) |
| CA9 | `check` en verde; ADR, README y roadmap | ✅ | Salida de arriba; [ADR 0011](../../adr/0011-usage-and-limits.md); README («Consumo y límites» y API); roadmap |

## Code review
`/code-review` de la rama: 10 hallazgos, todos corregidos.

| # | Hallazgo | Corrección | Test |
|---|---|---|---|
| 1 | Descartar «Límite diario» hacía que se creara otro en la siguiente comprobación | Descartarlo lo marca como visto (`reviewed`) y no se vuelve a crear ese día | `test_a_seen_limit_item_is_not_created_again_the_same_day` |
| 2 | Descartar «Cuota agotada» dejaba la tarea esperando y al agente ocupado | Descartar reanuda la tarea (sin escribir «continúa») | `test_dismissing_a_quota_item_lets_the_task_go_on` |
| 3 | Comprobaciones de límites simultáneas desde tres hilos podían duplicar el elemento | Candado en `check_limits` | Cubierto por el siguiente |
| 4 | Una comprobación descartada por el *throttle* podía retrasar el aviso hasta 60 s | Comprobación final con temporizador | `test_a_throttled_limit_check_runs_once_more_later` |
| 5 | Falsos positivos de cuota con la salida del propio agente («rate limit», `RESOURCE_EXHAUSTED`) | Patrones solo con la redacción de cada CLI, sin códigos genéricos | `test_quota_notice_on_screen` |
| 6 | Tras «Reanudar», una cuota que se repetía no se volvía a avisar | `quota_resumed()`: 10 s de margen y vuelve a avisar | Revisión; la ruta de «Reanudar» con el CLI vivo está en el e2e |
| 7 | El total de la tarea no contaba el razonamiento de agy | Usa `totalTokens()` | `format.test.ts` |
| 8 | Los límites leían las ejecuciones de hoy varias veces por consulta | `used_by_cli` y `blocked_all`: una lectura (y ninguna sin límites) | `test_blocked_all_reads_today_once` |
| 9 | El reintento de 2 s bloqueaba el *worker* | Temporizador que vuelve a encolar | `test_the_retry_waits_without_blocking_the_worker` |
| 10 | Al cerrar, el *worker* podía seguir con el backfill después de cerrar la base de datos | La parada termina las lecturas finales, deja el backfill para el siguiente arranque y espera hasta 15 s | `test_stopping_leaves_the_backfill_for_the_next_start` |

## Incidencias durante el desarrollo
1. **Claude solo escribe `cost-state` al cerrar** (C0), y las filas `assistant` se quedan cortas. Para el coste en vivo se usa la *status line* del propio Claude (ADR 0011). En la prueba real coincidió con `cost-state` al cerrar.
2. **La última fila de cada mensaje de Claude trae la salida final**: las anteriores pueden tener una cifra parcial (1491 frente a 891 tokens en la *fixture*).
3. **Cuota agotada**: no se pudo provocar con los CLIs reales. Los textos salen de sus binarios.
4. La suite completa, con la máquina cargada, tuvo un fallo de tiempos en `test_two_viewers_and_control`, que pasa aislado (no tiene relación con esta fase).
5. Los heredocs siguieron estropeando barras invertidas y `\r\n` en Python embebido. Se corrigieron con scripts en archivo.
6. Como en la fase 06, una prueba real añade la carpeta del proyecto a `trustedWorkspaces` de agy y al historial de agy (confianza automática de la fase 03).

## Retro
### Cambios respecto a la spec y al plan
- **Coste en vivo de Claude por la *status line***, no por el transcript (descubierto en C0; plan y ADR actualizados).
- El **Dashboard** solo recibe «Consumo de hoy». El resto sigue como «próximamente» y cambia el texto del marcador, que decía «Aún no tienes agentes».
- Con solo agy (sin coste), la gráfica y el reparto muestran **tokens** en lugar de un coste vacío.
- «Descartar» un «Límite diario» lo marca como visto y no se repite ese día. Descartar una «Cuota agotada» reanuda la tarea sin escribir «continúa».

### Impacto en fases futuras
- **Fase 08**: comprobar la exportación CSV en la app empaquetada (descarga de WebView2); ajustar los patrones de cuota si aparece un aviso real.
- **Fase 09 (UX/UI)**: el Dashboard completo (agentes, aprobaciones, actividad) junto a «Consumo de hoy».
- **Fase 14 (Postgres)**: pasar los agregados a SQL si el volumen lo pide.

## Comprobaciones pendientes del usuario
- Revisar **Consumo**, «Consumo de hoy» y el consumo de la sesión con datos propios.
- Probar «Exportar CSV» en la app de escritorio.
- Si algún CLI se queda sin cuota, comprobar que llega la «Cuota agotada». Si no llega, guardar el texto de la pantalla para ajustar los patrones.

## Cierre
- [x] OK del usuario (2026-10-12)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v0.8`
- [x] `docs/roadmap.md` actualizado
