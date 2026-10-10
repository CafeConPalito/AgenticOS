# Roadmap

Estados: `pendiente` · `spec` · `plan` · `dev` · `validación` · `cerrada`

Flujo de cada fase: ver `CLAUDE.md` (Spec → Plan → Desarrollo → Validación, con 3 puertas de aprobación).

| # | Fase | Estado | Objetivo | Criterios clave (orientativos) | Docs |
|---|---|---|---|---|---|
| 00 | Fundaciones | cerrada (`v0.1`) | Monorepo, docs, ADR del stack, esqueleto FastAPI + Vite + Tauri, lint, scripts de CI local, i18n base | `dev` levanta backend y UI; Tauri abre la ventana con el sidecar; tests de humo en verde | [spec](phases/00-fundaciones/spec.md) · [plan](phases/00-fundaciones/plan.md) · [validación](phases/00-fundaciones/validacion.md) |
| 01 | Spike de CLIs | cerrada (`v0.2`) | Validar en Windows **Claude Code y Antigravity CLI (`agy`)**: PTY interactivo con prompt, inyección MCP, permisos, consumo, hooks. Gemini CLI, OpenCode y Codex más adelante | Matriz verificada por CLI en `spike.md`; prototipos funcionando | [spec](phases/01-spike-clis/spec.md) · [plan](phases/01-spike-clis/plan.md) · [spike](phases/01-spike-clis/spike.md) · [validación](phases/01-spike-clis/validacion.md) |
| 02 | Dominio y CRUD | **validación** | Agentes (con plantillas y catálogo de CLIs) y Proyectos (con git y memoria); SQLite + Alembic; API REST; pantallas de Agentes y Proyectos | CRUD completo desde la UI; tests de la API; persistencia en SQLite | [spec](phases/02-dominio-crud/spec.md) · [plan](phases/02-dominio-crud/plan.md) · [validación](phases/02-dominio-crud/validacion.md) |
| 03 | Terminales en vivo | pendiente | PtySession, log a disco, WS multi-viewer, xterm.js, tomar control (Esc + stdin al humano, ADR 0003), aceptación automática del diálogo de confianza | Sesión real de Claude Code visible en vivo, interactiva, con scrollback recuperable | |
| 04 | Adapters y MCP | pendiente | Adapters de los CLIs según ADR 0004 (Claude por flags aislados; `agy` por plugin de workspace), context builder, servidor MCP `agentic-os` con token por ejecución, hooks `Stop`, `fake_agent`; evaluar el SDK de Antigravity | Cada CLI recibe su contexto y su MCP; `complete_task`/`update_status` llegan a la BD | |
| 05 | Scheduler y pipelines | pendiente | Modelos de Pipeline/Stage/Task, editor visual de pipeline, colas estrictas, concurrencia, Req→Dev→QA, workspaces (con carpeta directa, `agy` limitado a 1 ejecución por carpeta), memoria de proyecto, Kanban | Un agente encadena tareas de 2 proyectos sin compartir contexto; e2e del pipeline | |
| 06 | Subagentes y human-in-the-loop | pendiente | `spawn_subagent`, `create_subtask`, árbol de ejecuciones, Inbox, `request_human`, notificaciones de Windows | La aprobación llega a la Inbox y a la notificación, y la respuesta desbloquea al agente | |
| 07 | Consumo | pendiente | Parsers de transcripts por CLI (ADR 0005; prototipo en `spikes/usage_probe.py`), coste equivalente API en Claude y solo tokens en `agy`, límite diario, panel por agente, proyecto y sesión | Las cifras coinciden con las del propio CLI | |
| 08 | Empaquetado v1.0 (MVP) | pendiente | Instalador, ajustes, robustez (reinicios, ejecuciones huérfanas) | El instalador funciona en una máquina limpia; los e2e completos pasan | |
| 09 | Conocimiento | pendiente | Subida en 3 niveles, conversión, URLs, imágenes, RAG local, MCP `search_knowledge` | Un agente usa un PDF del proyecto para responder | |
| 10 | Skills | pendiente | Biblioteca SKILL.md en 3 niveles, autoselección, `propose_skill` | La skill relevante se carga sola; se registra una skill creada por un agente | |
| 11 | Meta-agentes | pendiente | Agente Arquitecto, propuestas en borrador, plantillas | Se crea un "Redactor" desde una conversación y ejecuta una tarea | |
| 12 | Avisos externos | pendiente | Telegram, email, Slack | Los avisos llegan al móvil | |
| 13 | Modo servidor | pendiente | Docker, autenticación, Postgres, WS autenticado | La app funciona desplegada en un servidor | |

## Historial
| Fecha | Cambio |
|---|---|
| 2026-10-08 | Roadmap inicial. Fase 00 en spec. |
| 2026-10-08 | Nombre "Agentic OS" confirmado. CLIs iniciales: Claude Code y Antigravity CLI. Diseño de la UI con Claude Design (`docs/design/`). |
| 2026-10-09 | Fase 00 cerrada (`v0.1`). Fase 01 en spec. |
| 2026-10-09 | Spike de CLIs completado: ADRs 0003 (modo de ejecución), 0004 (contexto y MCP por ejecución), 0005 (consumo); fases 03, 04, 05 y 07 ajustadas. |
| 2026-10-09 | Fase 01 cerrada (`v0.2`). Fase 02 en spec. |
