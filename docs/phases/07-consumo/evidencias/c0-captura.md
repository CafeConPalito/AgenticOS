# C0 · Captura con los CLIs reales

Fecha: 2026-10-12 · Claude Code 2.1.296 · agy 1.3.3

## 1. Cuándo escribe Claude la fila `cost-state`
- Solo **al cerrar la sesión** (después de `SessionEnd`). Nunca tras un `Stop`. Si la sesión se cierra dos veces (p. ej. `/exit` y luego el cierre del proceso), aparecen dos filas iguales.
- Las ejecuciones que se mataron sin cierre ordenado **no tienen** `cost-state` (p. ej. `claude-2.1.296-no-cost-state.jsonl`).
- Consecuencia: durante la ejecución, el transcript no tiene coste.

## 2. Filas `assistant` frente a `cost-state`
Hay una fila por bloque de contenido; las del mismo `message.id` repiten el mismo `usage`, así que se toma una por id.

| Transcript | `cost-state` (entrada · salida · caché lectura · caché escritura) | Suma de filas `assistant` (+ subagentes) |
|---|---|---|
| dos turnos (`two-turns`) | 1678 · 28 · 101 275 · 19 371 · **0,00507 $** | 4 · 8 · 62 310 · 17 486 |
| con subagente (`subagent`) | 1754 · 1564 · 261 471 · 42 426 · **0,00987 $** | 16 · 891 · 220 326 · 42 383 |
| tarea sencilla (fase 06) | 1245 · 786 · 149 189 · 12 223 | 8 · 623 · 149 189 · 12 223 |

- La suma de las filas **se queda corta**: Claude hace llamadas internas (título de la sesión, sugerencias, compactación…) que no escribe en el transcript pero sí cuenta en `cost-state`.
- Sirve como **aproximación de tokens en vivo**, no como cifra final.

## 3. La *status line* de Claude da el coste en vivo
- Con `--settings '{"statusLine": {"type": "command", "command": "…"}}'` (y `--setting-sources project,local`, como ya lanza Agentic OS), Claude ejecuta el comando con un JSON por stdin tras cada cambio relevante, también justo después de cada `Stop` (~0,3 s).
- El JSON trae `cost.total_cost_usd` **acumulado de la sesión**, `session_id`, `transcript_path`, `model` y `version` (*fixture* `claude-2.1.296-statusline.json`).
- `context_window.total_*_tokens` es el contexto actual, **no** el acumulado: no sirve para el consumo.
- En la prueba: tras el 1.er turno 0,00243 $, tras el 2.º 0,00425 $; `cost-state` al cerrar, 0,00507 $ (incluye las llamadas internas del cierre).
- El comando no imprime nada, así que no añade ninguna línea a la TUI.

→ **Claude**: coste en vivo por la *status line*; tokens en vivo por las filas `assistant` (aproximados); cifras exactas de `cost-state` al cerrar. Si no hay `cost-state` (cierre brusco), queda el último coste de la *status line* y los tokens aproximados, con fuente «parcial».

## 4. agy
- `transcript_full.jsonl` se escribe en cada paso: una fila `PLANNER_RESPONSE` con `input_tokens`, `output_tokens` y `cache_read_tokens` por llamada al modelo. No hay `thinking_tokens` en 1.3.3 (se lee si aparece).
- Los subagentes nativos tienen su propia conversación; sus hooks (`PreInvocation`…) llevan su propio `transcriptPath` (*fixture* `agy-PreInvocation-subagent-conversation.json`). Se guardan como `agy-1.3.3-subagent-main.jsonl` y `agy-1.3.3-subagent-child.jsonl`.
- Todos los hooks de agy traen `transcriptPath`; todos los de Claude traen `transcript_path`.

## 5. Textos de cuota y de límite de uso
No se ha podido provocar una cuota agotada real. Los textos salen de los binarios instalados:

| CLI | Textos | Uso |
|---|---|---|
| agy 1.3.3 | «Quota exhausted», «AI: Out of credits», `RESOURCE_EXHAUSTED`; «Refreshes in …» acompaña al estado de la cuota | patrones de `quota_notice`; «Refreshes in …» como hora de reinicio |
| Claude 2.1.296 | «Usage limit reached», «You've hit your … limit» (sesión, semanal, *spend limit* mensual), «your usage limit resets …», «resets …» | patrones de `quota_notice` |

Se excluyen los avisos que no son de cuota: «Context limit reached», «You've hit your fast limit» (modo rápido) y «Fast limit reached». Los patrones viven en `screen.py` (`QUOTA_PATTERNS`) para ampliarlos cuando se vean las pantallas reales.

## *Fixtures*
`backend/tests/fixtures/transcripts/`: transcripts anonimizados (solo tipos, ids, modelos y cifras) y el JSON de la *status line*.
