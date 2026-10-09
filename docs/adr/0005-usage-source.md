# ADR 0005: Fuente del consumo por sesión

- **Estado**: aceptado
- **Fecha**: 2026-10-09
- **Contexto de decisión**: spike de la fase 01 ([`spike.md`](../phases/01-spike-clis/spike.md), P8)

## Contexto
Hay que registrar el consumo por ejecución (sesión de CLI) y agregarlo por agente y por proyecto, tanto en modo interactivo (PTY) como en headless.

## Decisión
Leer el consumo de los **transcripts que escribe cada CLI**:
- **Claude Code**: `~/.claude/projects/<slug-del-cwd>/<session-id>.jsonl`. La ruta llega también en los hooks (`transcript_path`).
  - Se usa la última fila `cost-state`: `totalCostUSD` y `modelUsage` por modelo (entrada, salida, razonamiento, lectura y creación de caché), con subagentes incluidos.
  - Si falta, se suma el `usage` de las filas `assistant`, deduplicando por id de mensaje (hay una fila por bloque de contenido).
- **agy**: `~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/transcript_full.jsonl`. La ruta llega en los hooks (`transcriptPath`). Se suman los tokens de cada paso. **No hay coste**; se muestra «—», o un coste estimado si en el futuro se configura una tabla de precios.
- **Cuándo leerlo**: en cada hook `Stop` (consumo parcial en vivo) y al cerrar la ejecución (consumo final).
- Los parsers registran la versión del CLI. Los formatos no están documentados y pueden cambiar, así que los parsers toleran filas desconocidas y la app marca «consumo no disponible» si no encuentran nada.

## Consecuencias
- ✅ Funciona igual en PTY y en headless, y coincide exactamente con lo que reporta el propio CLI (verificado en el spike).
- ✅ Los subagentes de Claude quedan incluidos en `cost-state`.
- ⚠️ El coste de Claude es el **equivalente API**: con suscripción no es un cargo real. La UI lo etiquetará así.
- ⚠️ Dependemos de formatos internos: necesitamos tests con fixtures por versión.

## Alternativas descartadas
- **JSON de resultado del modo headless**: no existe en PTY, y su `usage` solo cubre el último turno.
- **OpenTelemetry de Claude Code**: más configuración y no cubre `agy`; se puede revisar si los transcripts dejan de servir.
