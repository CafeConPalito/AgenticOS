# Fase 08 · R1: reanudar sesiones con una configuración nueva

Guion: `spikes/scenarios/resume.py` (`claude`, `claude-killed`, `agy`). Fecha: 2026-10-12. Versiones: Claude Code 2.1.296 (`haiku`) y agy 1.3.3 (`gemini-3.8-flash-low`).

En cada caso, la primera sesión recibe la palabra clave `GIRASOL` y llama a `report_status` del MCP con el **token A**. Después se reanuda con el **token B** (otro `--mcp-config` / plugin y otros hooks) y se le pregunta la palabra. Servidor MCP del spike con un token por ejecución.

## Resultados

| Caso | ¿Recuerda? | MCP | Hooks | Transcript | Consumo |
|---|---|---|---|---|---|
| Claude, cierre limpio (`-p`) → `--resume <id>` | ✅ «GIRASOL» | La reanudada llama **solo con B** | El `Stop` de la config A saltó solo en la sesión 1 («OK»), el de B solo en la reanudada («GIRASOL») | **El mismo archivo** (`<id>.jsonl`), de 40 a 58 líneas; mismo `session_id` | Hay dos `cost-state` y la segunda es **acumulada**: mismo `startTime`, `totalDuration` 7419 → 9537 ms, salida 211 → 308 tokens, coste 0,00366 → 0,00433 $. El `total_cost_usd` del JSON del CLI también es el acumulado |
| Claude, TUI **cortada a la fuerza** tras un turno → `--resume <id>` | ✅ | Solo B | — | El mismo archivo; tras el corte **no hay ninguna `cost-state`** (solo filas `assistant`) | La reanudada **empieza de cero**: su `cost-state` (nuevo `startTime`) solo cuenta ese proceso (0,00117 $) |
| agy (`-p`) → `--conversation <id>` con el plugin reescrito | ✅ «GIRASOL» | Solo B | — | El mismo `transcript_full.jsonl`, de 6 a 11 líneas | Los pasos se **añaden**: los tokens leídos pasan de 38 859 a 66 090 de entrada |

**Claude con un ID inexistente**:
- en la TUI, escribe `No conversation found with session ID: <id>` y el proceso **termina** ([log](r1-claude-bogus.raw.log));
- en modo `-p`, sale con `rc=1` y el mismo texto por stderr.

**agy con un ID inexistente**: **no falla**. Escribe por stderr `warning: conversation "<id>" not found` y **abre una conversación nueva** (`rc=0`, otro `conversation_id`). En la TUI no se ve ningún aviso: abre normalmente ([log](r1-agy-bogus.raw.log)).

El JSON de `agy -p` trae `conversation_id` y `usage` (no se usan: el backend trabaja en modo interactivo).

## Consecuencias para el plan
1. **Reanudar funciona en los dos CLIs** con el contexto, el MCP y los hooks nuevos: la configuración no se guarda en la sesión. Se confirma el diseño (`--resume` / `--conversation` + configuración nueva).
2. **Consumo de una ejecución reanudada**: restar un total no sirve en todos los casos, porque la `cost-state` de Claude es acumulada tras un cierre limpio y empieza de cero tras un corte. Al reanudar se guarda `usage_baseline = {offset, cost_state}`:
   - `offset`: el tamaño del transcript en ese momento. Las filas `assistant` de Claude y los pasos de agy se leen **solo a partir de ahí**;
   - `cost_state`: la última `cost-state` que había (o nada). La `cost-state` de la ejecución reanudada es la última **posterior** al `offset`, menos esa base. El coste de la *status line* se trata igual.
3. **Sesión inexistente**:
   - **Claude**: el texto `No conversation found with session ID` se detecta en `screen.py`. Además, el proceso termina solo, así que la ejecución acaba `failed` con ese error;
   - **agy**: hay que detectarlo por el hook. Si el primer `conversationId` no es el pedido, la ejecución se para y termina `failed` con «La conversación ya no existe». Antes de lanzar se comprueba que existe su `transcript_full.jsonl`, así que este caso debería ser raro.
4. La prueba en la TUI marcó la carpeta del sandbox como de confianza en agy. Se quitó después a mano de `trustedWorkspaces`.
