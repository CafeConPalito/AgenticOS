# ADR 0011: Consumo y límites

- **Estado**: aceptado
- **Fecha**: 2026-10-12
- **Contexto de decisión**: fase 07 ([`spec.md`](../phases/07-consumo/spec.md), [`plan.md`](../phases/07-consumo/plan.md), [captura C0](../phases/07-consumo/evidencias/c0-captura.md))
- **Amplía**: [ADR 0005](0005-usage-source.md)

## Contexto
El ADR 0005 decidió leer el consumo de los transcripts que escribe cada CLI. Para mostrarlo en vivo, agregarlo y frenar el trabajo con límites diarios, hacía falta saber **cuándo** escribe cada CLI sus cifras. La captura C0 con Claude Code 2.1.296 y agy 1.3.3 mostró que:
- Claude solo escribe la fila `cost-state`, con sus cifras exactas, **al cerrar la sesión**.
- Durante la sesión, las filas `assistant` se quedan cortas: no incluyen las llamadas internas de Claude (título, sugerencias, compactación…).
- agy escribe cada paso en `transcript_full.jsonl` y nunca da coste.

## Decisión
### Fuentes por CLI
| | En vivo (cada fin de turno) | Al cerrar |
|---|---|---|
| **Claude Code** | **Coste** de la *status line*: el adapter añade `statusLine` a `--settings` y apunta al mismo `hook.cmd` (evento `StatusLine`), que no imprime nada. **Tokens** sumando las filas `assistant`, quedándose con la última fila de cada `message.id` (aproximados) | Fila `cost-state`: coste y tokens exactos, subagentes nativos incluidos |
| **agy** | Suma de los pasos de `transcript_full.jsonl` | Igual (no hay cifra distinta al cerrar) |

- **Ruta del transcript**: manda la que llega en los hooks (`transcript_path` / `transcriptPath`, presentes en todos). Solo si no ha llegado ninguno, se calcula a partir de la carpeta de trabajo y el ID de sesión, respetando `CLAUDE_CONFIG_DIR`.
- **Subagentes nativos de agy**: cada uno tiene su conversación y su transcript. Sus hooks llegan con otro `conversationId` (ya se detectaba en la fase 06) y su `transcriptPath` se guarda en `runs.extra_transcripts` para sumarse a la ejecución que los lanzó.
- **Cierre brusco de Claude** (sin `cost-state`): se reintenta la lectura una vez a los 2 s. Si sigue sin aparecer, quedan el último coste de la *status line* y los tokens aproximados, en estado `final` y con fuente `assistant-rows`.
- **Lectura**: un solo hilo (`UsageService`) lee los transcripts de forma incremental, desde el último byte leído; si el archivo encoge, empieza de nuevo. Ni los hooks ni el cierre de una ejecución esperan al disco.
- **Ejecuciones anteriores** a esta fase, o que terminaron con el backend caído: al arrancar se leen una vez (*backfill*), sin reintento.

### Datos
- Las cifras van en columnas de `runs`: tokens de entrada, salida, razonamiento y caché (lectura y escritura), `cost_usd` (nulo = sin coste), desglose por modelo, fuente, estado (`pending` · `partial` · `final` · `unavailable`), versión del CLI y fecha de la lectura. Todos los agregados salen de las ejecuciones, así que se evitan *joins*.
- El total de tokens no cuenta dos veces el razonamiento de Claude, que ya va dentro de su `output_tokens`. En agy se suma aparte.

### Agregados
- El **día** de una ejecución es el día local (zona horaria del equipo) en que empezó. Una ejecución que cruza la medianoche cuenta entera en ese día.
- Se agrega en Python sobre las ejecuciones del periodo (cientos o pocos miles en una app de escritorio). Así se evitan las funciones de fecha de SQLite. Se revisará con Postgres en la fase 14.
- Moneda: **USD sin convertir**, etiquetado «equivalente API».

### Límites diarios
- **Uno por CLI**: coste en USD para Claude Code, tokens sin caché (entrada + salida + razonamiento) para agy, que no da coste. Se guardan en `app_state.usage_limits`.
- Al superarlo:
  - el scheduler no lanza tareas nuevas de **ese CLI** (`limits.blocked`); el otro CLI sigue;
  - las ejecuciones en marcha siguen;
  - lanzar a mano sigue siendo posible, y la respuesta lleva `warning: "limit_reached"`.
- Un elemento «Límite diario alcanzado» (`kind = limit`, `command = <cli>`) por CLI y día. Se crea al cruzar el límite (comprobación limitada a una cada 5 s tras cada cambio de consumo, más el *housekeeping* de cada minuto). Se resuelve solo al cambiar de día o al subir el límite.

### Cuota agotada
- `ScreenState.quota_notice()` busca el aviso del CLI en las **10 últimas líneas** de la pantalla, con los patrones de `screen.py` (`QUOTA_PATTERNS`, `QUOTA_RESET`). Los textos salen de los binarios instalados, porque no se pudo provocar una cuota real:
  - agy: «Quota exhausted», «Out of credits», `RESOURCE_EXHAUSTED` y «Refreshes in …»;
  - Claude: «Usage limit reached», «You've hit your … limit» y «… resets …». Se excluyen el límite de contexto y el del modo rápido.
- Al detectarlo:
  - se crea un elemento «Cuota agotada» (`kind = quota`, `command = <cli>`);
  - la tarea pasa a «Esperando humano» (`quota`, una espera «viva» que mantiene ocupado al agente);
  - el scheduler no lanza tareas de ese CLI mientras el elemento esté pendiente.
- **Reanudar** (`POST /inbox/{id}/resume`): resuelve el elemento, devuelve la tarea a «En ejecución», escribe «continúa» en la terminal si el CLI sigue vivo y avisa al scheduler.

## Consecuencias
- ✅ Claude da coste exacto en vivo (el de su propia *status line*) y cifras exactas al cerrar. En la prueba real, la última *status line* coincidió con `cost-state`.
- ✅ agy cuenta los tokens de sus subagentes nativos.
- ⚠️ La *status line* de Agentic OS sustituye a la que tenga el usuario en el proyecto, solo en estas sesiones. Las de usuario ya no se cargaban (`--setting-sources project,local`).
- ⚠️ Los tokens de Claude en vivo son una aproximación hasta el cierre.
- ⚠️ Los patrones de cuota no se han visto en una pantalla real: pueden necesitar ajustes cuando aparezcan.
- ⚠️ El límite de agy es una referencia en tokens que fija el usuario según su cuota; no se traduce en dinero.

## Alternativas descartadas
- **Releer el transcript completo en cada turno**: es costoso con transcripts de varios MB.
- **Tabla de precios propia** para estimar el coste en vivo de Claude: la *status line* da el coste del propio CLI sin mantener precios.
- **Tabla de uso aparte** de `runs`: obliga a *joins* en todos los agregados sin ventaja clara.
- **Cortar las ejecuciones en marcha** al superar el límite: perdería trabajo a medias (spec).
