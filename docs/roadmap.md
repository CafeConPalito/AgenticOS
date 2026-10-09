# Roadmap

Estados: `pendiente` · `spec` · `plan` · `dev` · `validación` · `cerrada`

Flujo de cada fase: ver `CLAUDE.md` (Spec → Plan → Desarrollo → Validación, con 3 puertas de aprobación).

| # | Fase | Estado | Objetivo | Criterios clave (orientativos) | Docs |
|---|---|---|---|---|---|
| 00 | Fundaciones | cerrada (`v0.1`) | Monorepo, docs, ADR del stack, esqueleto FastAPI + Vite + Tauri, lint, scripts de CI local, i18n base | `dev` levanta backend y UI; Tauri abre la ventana con el sidecar; tests de humo en verde | [spec](phases/00-fundaciones/spec.md) · [plan](phases/00-fundaciones/plan.md) · [validación](phases/00-fundaciones/validacion.md) |
| 01 | Spike de CLIs | **plan** | Validar en Windows **Claude Code y Antigravity CLI (`agy`)**: PTY interactivo con prompt, inyección MCP, permisos, consumo, hooks. Gemini CLI, OpenCode y Codex más adelante | Matriz verificada por CLI en `spike.md`; prototipos funcionando | [spec](phases/01-spike-clis/spec.md) · [plan](phases/01-spike-clis/plan.md) |
| 02 | Dominio y CRUD | pendiente | Agent, Project, Pipeline/Stage, Task; API REST; pantallas de Agentes y Proyectos | CRUD completo desde la UI; tests de la API; persistencia en SQLite | |
| 03 | Terminales en vivo | pendiente | PtySession, log a disco, WS multi-viewer, xterm.js, tomar control | Sesión real de Claude Code visible en vivo, interactiva, con scrollback recuperable | |
| 04 | Adapters y MCP | pendiente | Adapters de los CLIs, context builder, servidor MCP `agentic-os`, `fake_agent` | Cada CLI recibe su contexto y su MCP; `complete_task`/`update_status` llegan a la BD | |
| 05 | Scheduler y pipelines | pendiente | Colas estrictas, concurrencia, Req→Dev→QA, workspaces, memoria de proyecto, Kanban | Un agente encadena tareas de 2 proyectos sin compartir contexto; e2e del pipeline | |
| 06 | Subagentes y human-in-the-loop | pendiente | `spawn_subagent`, `create_subtask`, árbol de ejecuciones, Inbox, `request_human`, notificaciones de Windows | La aprobación llega a la Inbox y a la notificación, y la respuesta desbloquea al agente | |
| 07 | Consumo | pendiente | Parsers de consumo por CLI, panel por agente, proyecto y sesión | Las cifras coinciden con las del propio CLI | |
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
