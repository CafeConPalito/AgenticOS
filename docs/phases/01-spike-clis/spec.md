# Fase 01: Spike de CLIs · Spec

- **Estado**: aprobada (2026-10-09)
- **Rama**: `phase/01-spike-clis`

## Objetivo
Comprobar en Windows, con pruebas reales, **cómo controlar Claude Code y Antigravity CLI (`agy`) desde Agentic OS** antes de construir sobre ellos. Al acabar tendremos una matriz verificada de capacidades por CLI y prototipos mínimos que funcionan, y las decisiones de diseño de las fases 03 (terminales), 04 (adapters y MCP), 06 (human-in-the-loop) y 07 (consumo) estarán tomadas sobre hechos y no sobre suposiciones.

Es una fase de investigación: el código que produce son prototipos (`spikes/`), no código de producto.

## Alcance
### Dentro
Para **Claude Code** (2.1.x) y **Antigravity CLI** (`agy` 1.3.x), responder con evidencia a estas preguntas:

| # | Pregunta | Por qué importa |
|---|---|---|
| P1 | **Lanzamiento en PTY**: ¿arranca en modo interactivo dentro de un pseudo-terminal (pywinpty/ConPTY) con un prompt inicial, se ve bien (ANSI, redimensionado) y acepta texto escrito desde fuera? | Base de la fase 03 (terminal en vivo + «Tomar control») |
| P2 | **Fin de turno e inactividad**: ¿cómo sabemos que el agente terminó un turno o está esperando entrada (hooks, salida, ausencia de salida)? | Saber cuándo una tarea acaba o necesita a un humano |
| P3 | **Pausar / interrumpir**: ¿qué pasa al enviar Esc o Ctrl+C? ¿Se puede interrumpir un turno sin matar la sesión y luego continuar? | Define qué significa «Tomar control → el agente queda en pausa» del diseño |
| P4 | **Contexto e instrucciones**: ¿cómo inyectamos el rol y la tarea del agente sin tocar archivos del usuario? (`--append-system-prompt`, `CLAUDE.md`, `GEMINI.md`/`AGENTS.md`, `--agent`…) | Context builder de la fase 04 |
| P5 | **MCP por sesión**: ¿podemos dar a cada ejecución nuestro servidor MCP (`agentic-os`) **sin modificar la configuración global** del usuario? ¿Funciona con un servidor HTTP local? | Coordinación de agentes (fase 04). Riesgo principal en `agy`, cuyo `mcp add` parece global |
| P6 | **Permisos**: ¿cómo se traducen nuestros modos Autónomo / Restringido / Preguntar a los flags de cada CLI? ¿Dónde aparecen las peticiones de permiso? | Modo de permisos por agente |
| P7 | **Sesión e identificador**: ¿podemos fijar o leer el ID de sesión, y reanudarla? (`--session-id`, `--resume`, `--conversation`) | Vincular Run ↔ sesión de CLI; reintentos |
| P8 | **Consumo**: ¿de dónde sacamos tokens de entrada, salida y caché, coste y modelo por sesión? (transcripts JSONL, `stream-json`, bases de datos locales, logs) | Fase 07; requisito de consumo por agente, proyecto y sesión |
| P9 | **Hooks y eventos**: ¿qué hooks o eventos ofrece cada CLI (fin de turno, notificación, uso de herramientas) y cómo los configuramos por sesión? | Plan B al MCP para estado y aprobaciones |
| P10 | **Subagentes nativos**: ¿podemos detectar cuándo el CLI lanza sus propios subagentes (p. ej. la herramienta Task de Claude)? | Árbol de ejecución (fase 06) |
| P11 | **Modo headless** (`-p` + `stream-json`): ¿sirve como alternativa o complemento al PTY? | Plan B si el PTY no es fiable |
| P12 | **Estado del CLI**: ¿cómo detectamos instalación, versión, sesión iniciada y modelos disponibles? | Pantalla Ajustes › CLIs detectados |

Entregables:
- `docs/phases/01-spike-clis/spike.md`: **matriz de capacidades** (P1–P12 × CLI) con ✅ / ⚠️ / ❌, el comando o el mecanismo exacto, y un extracto de la salida como evidencia.
- `spikes/` con prototipos mínimos y reproducibles:
  - `pty_run.py`: lanza un CLI en ConPTY con un prompt, muestra la salida en vivo, permite escribir y redimensionar, y lo registra en un log.
  - `spike_mcp.py`: servidor MCP mínimo con las herramientas `report_status` y `complete_task`, que cada CLI llama desde una configuración inyectada por sesión.
  - `usage_probe.py`: extrae el consumo de una sesión y lo compara con lo que dice el propio CLI.
- ADRs con las decisiones que salgan (p. ej. «PTY interactivo vs headless», «inyección de MCP en `agy`», «semántica de pausar»).
- Ajustes en `docs/roadmap.md` y en la visión si los hallazgos cambian el plan de fases.

### Fuera
- Integrar nada en la app (backend, UI, Tauri): eso es de las fases 03 y 04.
- Gemini CLI, OpenCode y Codex: se investigarán cuando se incorporen.
- Optimizar o empaquetar los prototipos.

## Historias de usuario
- Como desarrollador de Agentic OS, quiero saber con certeza qué puedo controlar de cada CLI para diseñar los adapters sin sorpresas.
- Como usuario, quiero que mis agentes usen mis CLIs y suscripciones actuales sin que Agentic OS me desordene la configuración global.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | `spike.md` responde P1–P12 para los dos CLIs, cada celda con estado, mecanismo y evidencia (comando + extracto) | Revisión |
| CA2 | `pty_run.py` lanza Claude Code y `agy` en ConPTY con un prompt inicial, emite la salida en vivo, acepta texto escrito desde fuera y guarda el log | Ejecución + log en `evidencias/` |
| CA3 | Los dos CLIs llaman a `report_status` y `complete_task` de `spike_mcp.py` mediante una configuración inyectada **solo para esa ejecución**; la configuración global del usuario no cambia (diff antes/después) | Log del servidor MCP + diff de los archivos de configuración |
| CA4 | Queda documentado qué hacen Esc y Ctrl+C en cada CLI y se propone la semántica de «Tomar control / Pausar» | `spike.md` + ADR |
| CA5 | `usage_probe.py` obtiene tokens (y coste si el CLI lo da) de una sesión de cada CLI, y las cifras coinciden con las que reporta el propio CLI | Salida comparada en `spike.md` |
| CA6 | Las decisiones están registradas en ADRs y el roadmap está actualizado si cambia algo | Revisión |

## Prerrequisitos
- Claude Code 2.1.295 y `agy` 1.3.1 instalados y con sesión iniciada (verificado: `agy models` lista los modelos Gemini).
- Dependencias de los prototipos: `pywinpty` y `mcp` (SDK oficial de Python) en el grupo de desarrollo del backend o en un entorno propio de `spikes/`.

## Riesgos y preguntas abiertas
- **Consumo de tokens**: las pruebas usan prompts cortos y modelos baratos (Haiku en Claude; Flash Low en `agy`), y `--max-budget-usd` cuando esté disponible.
- **Seguridad**: los modos sin permisos (`--dangerously-skip-permissions`) solo se prueban dentro de una carpeta desechable creada para el spike, nunca sobre el repo ni sobre carpetas del usuario.
- **MCP en `agy`**: si no admite configuración por sesión o por proyecto, el plan B es lanzar `agy` con un directorio de configuración aislado (variable de entorno o HOME temporal), si existe esa opción. Si no hay ninguna vía, se documenta y se decide en el ADR (p. ej. registrar un único servidor `agentic-os` global que identifique la ejecución por token).
- **Comportamiento cambiante**: los CLIs se actualizan a menudo; `spike.md` registra las versiones exactas probadas.
