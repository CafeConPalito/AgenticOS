# Consumo por sesión (P8)

## Claude (simple): transcript vs resultado ✅ ()

| | Transcript (`cost-state`) | Resultado JSON |
|---|---|---|
| Coste USD | 0.00144932 | 0.00144932 |
| Tokens entrada (todos los modelos) | 2 | 2 |
| Tokens salida (todos los modelos) | 30 | 30 |
| Caché lectura / creación | 14052 / 6468 | `usage` del último turno: 14052 / 6468 |
| Modelos | ['claude-haiku-5-5'] | ['claude-haiku-5-5'] |


## Claude (subagente): transcript vs resultado ✅ ()

| | Transcript (`cost-state`) | Resultado JSON |
|---|---|---|
| Coste USD | 0.00422583 | 0.00422583 |
| Tokens entrada (todos los modelos) | 8 | 8 |
| Tokens salida (todos los modelos) | 888 | 888 |
| Caché lectura / creación | 49163 / 22027 | `usage` del último turno: 34580 / 7147 |
| Modelos | ['claude-haiku-5-5'] | ['claude-haiku-5-5'] |


## agy: transcript vs resultado ✅ ()

| | transcript_full.jsonl | Resultado JSON |
|---|---|---|
| Tokens entrada | 11690 | 11690 |
| Tokens salida | 19 | 19 |
| Caché lectura | 0 | 0 |
| Razonamiento | 0 | 0 |
| Coste | — (no registrado) | — |


## Claude (sesión interactiva PTY de P5): consumo desde el transcript ✅ ()

`3cfbe5d4-1880-427c-8fc2-dede691525d0.jsonl` → {"source": "claude:cost-state", "input_tokens": 1737, "output_tokens": 714, "cache_read_tokens": 186667, "cache_creation_tokens": 11144, "thinking_tokens": 460, "cost_usd": 0.004626170000000001, "models": {"claude-haiku-5-5": {"inputTokens": 1737, "outputTokens": 714, "thinkingTokens": 460, "cacheReadInputTokens": 186667, "cacheCreationInputTokens": 11144, "webSearchRequests": 0, "costUSD": 0.004626170000000001}}}

Configuración global: SIN CAMBIOS
