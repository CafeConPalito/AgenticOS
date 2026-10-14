# Roadmap

Estados: `pendiente` · `spec` · `plan` · `dev` · `validación` · `cerrada`

Flujo de cada fase: ver `CLAUDE.md` (Spec → Plan → Desarrollo → Validación, con 3 puertas de aprobación).

| # | Fase | Estado | Objetivo | Criterios clave (orientativos) | Docs |
|---|---|---|---|---|---|
| 00 | Fundaciones | cerrada (`v0.1`) | Monorepo, docs, ADR del stack, esqueleto FastAPI + Vite + Tauri, lint, scripts de CI local, i18n base | `dev` levanta backend y UI; Tauri abre la ventana con el sidecar; tests de humo en verde | [spec](phases/00-fundaciones/spec.md) · [plan](phases/00-fundaciones/plan.md) · [validación](phases/00-fundaciones/validacion.md) |
| 01 | Spike de CLIs | cerrada (`v0.2`) | Validar en Windows **Claude Code y Antigravity CLI (`agy`)**: PTY interactivo con prompt, inyección MCP, permisos, consumo, hooks. Gemini CLI, OpenCode y Codex más adelante | Matriz verificada por CLI en `spike.md`; prototipos funcionando | [spec](phases/01-spike-clis/spec.md) · [plan](phases/01-spike-clis/plan.md) · [spike](phases/01-spike-clis/spike.md) · [validación](phases/01-spike-clis/validacion.md) |
| 02 | Dominio y CRUD | cerrada (`v0.3`) | Agentes (con plantillas y catálogo de CLIs) y Proyectos (con git y memoria); SQLite + Alembic; API REST; pantallas de Agentes y Proyectos | CRUD completo desde la UI; tests de la API; persistencia en SQLite | [spec](phases/02-dominio-crud/spec.md) · [plan](phases/02-dominio-crud/plan.md) · [validación](phases/02-dominio-crud/validacion.md) |
| 03 | Terminales en vivo | cerrada (`v0.4`) | Ejecuciones lanzadas a mano en PTY, log a disco, WS multi-visor, xterm.js, tomar control (ADR 0003), confianza automática, página de ejecución, dock global y lista de ejecuciones | Sesión real de Claude Code y agy en vivo, interactiva, con scrollback recuperable y sin huérfanos | [spec](phases/03-terminales/spec.md) · [plan](phases/03-terminales/plan.md) · [validación](phases/03-terminales/validacion.md) |
| 04 | Adapters y MCP | cerrada (`v0.5`) | Adapters de los CLIs según ADR 0004 (Claude por flags aislados; `agy` por plugin de workspace), context builder, servidor MCP `agentic-os` con token por ejecución, hooks `Stop`, `fake_agent`; evaluar el SDK de Antigravity | Cada CLI recibe su contexto y su MCP; `complete_task`/`update_status` llegan a la BD | [spec](phases/04-adapters-mcp/spec.md) · [plan](phases/04-adapters-mcp/plan.md) · [validación](phases/04-adapters-mcp/validacion.md) |
| 05 | Scheduler y pipelines | cerrada (`v0.6`) | Modelos de Pipeline/Stage/Task, editor visual de pipeline, colas estrictas, concurrencia, Req→Dev→QA, workspaces (con carpeta directa, `agy` limitado a 1 ejecución por carpeta), memoria de proyecto, Kanban | Un agente encadena tareas de 2 proyectos sin compartir contexto; e2e del pipeline | [spec](phases/05-scheduler-pipelines/spec.md) · [plan](phases/05-scheduler-pipelines/plan.md) · [validación](phases/05-scheduler-pipelines/validacion.md) |
| 06 | Subagentes y human-in-the-loop | cerrada (`v0.7`) | `spawn_subagent`, `create_subtask`, árbol de ejecuciones, Inbox, `request_human`, notificaciones de Windows | La aprobación llega a la Inbox y a la notificación, y la respuesta desbloquea al agente | [spec](phases/06-subagentes-hitl/spec.md) · [plan](phases/06-subagentes-hitl/plan.md) · [validación](phases/06-subagentes-hitl/validacion.md) |
| 07 | Consumo | cerrada (`v0.8`) | Parsers de transcripts por CLI (ADR 0005; prototipo en `spikes/usage_probe.py`), coste equivalente API en Claude y solo tokens en `agy`, límite diario, panel por agente, proyecto y sesión | Las cifras coinciden con las del propio CLI | [spec](phases/07-consumo/spec.md) · [plan](phases/07-consumo/plan.md) · [validación](phases/07-consumo/validacion.md) |
| 08 | Empaquetado v1.0 (MVP) | cerrada (`v1.0`) | Instalador, ajustes, robustez (reinicios, ejecuciones huérfanas, reanudar sesiones) | El instalador funciona en una máquina limpia; los e2e completos pasan | [spec](phases/08-empaquetado/spec.md) · [plan](phases/08-empaquetado/plan.md) · [validación](phases/08-empaquetado/validacion.md) |
| 09 | Mejora de UX/UI | cerrada (`v1.1`) | Revisar la navegación y simplificar la interfaz tras la v1.0: menú y flujos principales, menos elementos por pantalla, jerarquía visual más clara y coherente | Las tareas habituales se hacen en menos pasos y cada pantalla se entiende de un vistazo (revisión con el usuario) | [spec](phases/09-ux-ui/spec.md) · [plan](phases/09-ux-ui/plan.md) · [validación](phases/09-ux-ui/validacion.md) |
| 10 | Equipos y cuentas de CLI | cerrada (`v1.2`) | Agrupar agentes en equipos y usar varias cuentas por CLI (cada agente con su cuenta; sesiones y avisos por cuenta), según el diseño v7 (`docs/design/v2/`) | Dos agentes del mismo CLI trabajan con cuentas distintas; Inicio los muestra por equipo | [spec](phases/10-equipos-cuentas/spec.md) · [plan](phases/10-equipos-cuentas/plan.md) · [validación](phases/10-equipos-cuentas/validacion.md) |
| 11 | Revisión de código | pendiente | Ver el código que ha cambiado cada agente: diff por tarea y por ejecución, por fichero y por línea (como `git diff`), con lista de ficheros, añadidos y borrados; visible al validar la tarea (etapa de revisión, Peticiones) y desde la ficha del agente | Al revisar una tarea se ven sus ficheros cambiados y el diff línea a línea antes de aprobar o rechazar | |
| 12 | Conocimiento | pendiente | Subida en 3 niveles, conversión, URLs, imágenes, RAG local, MCP `search_knowledge` | Un agente usa un PDF del proyecto para responder | |
| 13 | Dictado por voz | pendiente | Voz a texto local en los campos donde se escribe mucho (descripción de tarea, instrucciones del agente, motivo de un rechazo, conversación con el Arquitecto): transcripción con Whisper en el backend sin enviar audio fuera, modelo elegible y descargable desde Ajustes (reutiliza la gestión de modelos locales de la fase 12), botón de micrófono y atajo de mantener pulsado, texto insertado en el cursor; validar pronto el permiso de micrófono en WebView2 | Se dicta en español una descripción de tarea de un par de párrafos sin conexión a internet y llega al campo en pocos segundos | |
| 14 | Skills | pendiente | Biblioteca SKILL.md en 3 niveles, autoselección, `propose_skill` | La skill relevante se carga sola; se registra una skill creada por un agente | |
| 15 | Conexiones MCP | pendiente | Conectar los agentes a servidores MCP externos (GitHub, bases de datos, navegador, servicios propios…): catálogo de conexiones (stdio o HTTP) con sus credenciales guardadas de forma segura, asignación por agente o por proyecto, inyección en la configuración de cada CLI por ejecución (junto al MCP `agentic-os`), prueba de conexión y lista de herramientas | Un agente usa en una tarea las herramientas de un MCP externo configurado desde la app, sin tocar a mano la configuración del CLI | |
| 16 | Meta-agentes | pendiente | Agente Arquitecto, propuestas en borrador, plantillas | Se crea un "Redactor" desde una conversación y ejecuta una tarea | |
| 17 | Avisos externos | pendiente | Telegram, email, Slack | Los avisos llegan al móvil | |
| 18 | Instaladores firmados | pendiente | Instaladores multiplataforma y firmados: Windows (NSIS/MSI con firma Authenticode, sin aviso de SmartScreen), macOS (`.dmg` firmado con Developer ID y notarizado, Intel y Apple Silicon) y Linux (AppImage, `.deb` y `.rpm` con firma GPG); sidecar del backend construido y firmado para cada plataforma; actualizaciones automáticas firmadas (updater de Tauri); builds y firma en CI | En una máquina limpia de cada sistema la app se instala sin avisos de seguridad, arranca con su backend y se actualiza sola a una versión nueva | |
| 19 | Modo servidor | pendiente | Docker, autenticación, Postgres, WS autenticado; el dictado por voz transcribe en el servidor o en el cliente | La app funciona desplegada en un servidor | |

## Historial
| Fecha | Cambio |
|---|---|
| 2026-10-08 | Roadmap inicial. Fase 00 en spec. |
| 2026-10-08 | Nombre "Agentic OS" confirmado. CLIs iniciales: Claude Code y Antigravity CLI. Diseño de la UI con Claude Design (`docs/design/`). |
| 2026-10-09 | Fase 00 cerrada (`v0.1`). Fase 01 en spec. |
| 2026-10-09 | Spike de CLIs completado: ADRs 0003 (modo de ejecución), 0004 (contexto y MCP por ejecución), 0005 (consumo); fases 03, 04, 05 y 07 ajustadas. |
| 2026-10-09 | Fase 01 cerrada (`v0.2`). Fase 02 en spec. |
| 2026-10-10 | Fase 02 cerrada (`v0.3`). Fase 03 en spec. |
| 2026-10-10 | Fase 03 en validación: ADR 0007 (procesos de las ejecuciones). |
| 2026-10-10 | Fase 03 cerrada (`v0.4`). Fase 04 en spec. |
| 2026-10-11 | Fase 04 en validación: ADR 0008 (coordinación de agentes). |
| 2026-10-11 | Fase 04 cerrada (`v0.5`). Fase 05 en spec. |
| 2026-10-11 | Fase 05 en validación: ADR 0009 (scheduler, colas y workspaces). |
| 2026-10-11 | Fase 05 cerrada (`v0.6`). Fase 06 en spec. |
| 2026-10-11 | Fase 06 en validación: ADR 0010 (human-in-the-loop y subagentes). |
| 2026-10-11 | Fase 06 cerrada (`v0.7`). La fase 07 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-12 | Nueva fase 09 (Mejora de UX/UI) tras la v1.0; las fases 09–13 pasan a ser 10–14. |
| 2026-10-12 | Fase 07 en spec. |
| 2026-10-12 | Spec de la fase 07 aprobada. Fase 07 en plan. |
| 2026-10-12 | Plan de la fase 07 aprobado. Fase 07 en dev. |
| 2026-10-12 | Fase 07 en validación: ADR 0011 (consumo y límites). |
| 2026-10-12 | Fase 07 cerrada (`v0.8`). La fase 08 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-12 | Fase 08 en spec. Auto-update y firma de código fuera de la v1.0. |
| 2026-10-12 | Spec de la fase 08 aprobada. Fase 08 en plan. |
| 2026-10-12 | Plan de la fase 08 aprobado. Fase 08 en dev. |
| 2026-10-12 | Fase 08 en validación: ADR 0012 (empaquetado y reanudación de sesiones). |
| 2026-10-12 | Fase 08 cerrada (`v1.0`, MVP). La fase 09 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-13 | Fase 09 en spec. |
| 2026-10-13 | Fase 09 basada en el diseño v7 de Claude Design (`docs/design/v2/`). Nueva fase 10 (Equipos y cuentas de CLI); las fases 10–14 pasan a ser 11–15. |
| 2026-10-13 | Spec de la fase 09 aprobada. Fase 09 en plan. |
| 2026-10-14 | Plan de la fase 09 aprobado. Fase 09 en dev. |
| 2026-10-14 | Fase 09 en validación: ADR 0013 (navegación, Inicio y atajos). |
| 2026-10-14 | Fase 09 cerrada (`v1.1`). La fase 10 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-14 | Nueva fase 15 (Instaladores firmados para Windows, macOS y Linux); Modo servidor pasa a ser la 16. |
| 2026-10-14 | Nueva fase 12 (Dictado por voz, local); las fases 12–16 pasan a ser 13–17. |
| 2026-10-14 | Fase 10 en spec. |
| 2026-10-14 | Spec de la fase 10 aprobada (incluye la cuota de las suscripciones, leída de la status line). Fase 10 en plan. |
| 2026-10-14 | Plan de la fase 10 aprobado. Fase 10 en dev. |
| 2026-10-14 | Ampliación de la fase 10 aprobada (CLI secundario por agente y alerta de cambio por cuota). |
| 2026-10-14 | Fase 10 cerrada (`v1.2`); queda anotada la prueba manual con una segunda cuenta real. |
| 2026-10-14 | Nueva fase 11 (Revisión de código: diff por agente y al validar la tarea); las fases 11–17 pasan a ser 12–18. |
| 2026-10-14 | Nueva fase 15 (Conexiones MCP), tras Skills; las fases 15–18 pasan a ser 16–19. |
