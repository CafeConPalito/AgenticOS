# Visión: Agentic OS

## Qué es
Una app de escritorio (que más adelante se podrá desplegar en un servidor) para **declarar y orquestar agentes de IA que trabajan como empleados**. Cada agente usa un CLI existente (Claude Code, Gemini CLI, OpenCode, Codex CLI u otros) y trabaja en una terminal real.

## Capacidades objetivo
- **Agentes declarados desde la UI**: rol, prompt, CLI, modelo, permisos, concurrencia, skills y conocimiento. Ejemplos: Analista de requisitos, Desarrollador, QA, Comercial, Redactor.
- **Proyectos**: carpeta local (git opcional). También sirven para proyectos que no son de código.
- **Orquestación híbrida**: pipelines configurables por proyecto (p. ej. Requisitos → Desarrollo → QA, y si QA rechaza, vuelta a Dev), y además los agentes pueden crear subtareas y lanzar subagentes.
- **Colas como empleados**: cola FIFO estricta por agente con prioridad y `max_concurrency` (1 por defecto). Cada tarea arranca una sesión nueva, sin contexto compartido entre proyectos. El agente termina la tarea del proyecto 1 y pasa a la del proyecto 2.
- **Memoria de proyecto**: al terminar cada tarea, el agente escribe notas que se inyectan en las siguientes tareas de ese proyecto.
- **Agentes autónomos con human-in-the-loop**: cada ejecución vive en su propia terminal (PTY) y puedes entrar, ver todo lo hecho y tomar el control.
- **Control**: estado de las tareas, árbol de subagentes, Inbox de aprobaciones y preguntas, y notificaciones.
- **Consumo**: tokens, coste y duración por sesión de CLI, agregados por agente y por proyecto.
- **Conocimiento en 3 niveles** (general, proyecto y agente): md/código, PDF/Word/Excel, URLs e imágenes. Los documentos pequeños van al contexto y los grandes a RAG local.
- **Skills en 3 niveles**: biblioteca local (SKILL.md), autoselección por tarea y skills creadas por los agentes con aprobación.
- **Meta-agentes**: un agente Arquitecto propone nuevos agentes (Comercial, Redactor…) y tú los apruebas.

## Arquitectura de referencia
| Tema | Decisión |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic; SQLite (local) y Postgres (servidor) |
| Frontend | Vite, React, TS, shadcn/ui, TanStack Query, Zustand, xterm.js, dnd-kit, i18next |
| Escritorio | Tauri v2 con el backend como sidecar (PyInstaller) |
| Ejecución | PTY por ejecución (pywinpty en Windows), CLI interactivo con prompt inicial, emisión por WebSocket a xterm.js |
| Coordinación | Servidor MCP propio `agentic-os`: `get_task`, `update_status`, `create_subtask`, `spawn_subagent`, `request_human`, `write_project_memory`, `complete_task`; con hooks e inactividad/salida del proceso como respaldo |
| Workspaces | Por proyecto: carpeta directa o git worktree por tarea |
| Permisos | Por agente: autonomous / restricted / ask, traducido a los flags de cada CLI |
| Avisos | Inbox y notificaciones del sistema; Telegram, email y Slack más adelante |
| Usuarios | Mono-usuario, con modelo de datos preparado para multi-usuario (`workspace_id`) |

```
┌──────────── Tauri (ventana nativa) ────────────┐
│  Frontend React (Vite)  ◄── REST + WebSocket ──┼──► Backend FastAPI (sidecar)
└────────────────────────────────────────────────┘      ├─ Scheduler (colas por agente)
                                                        ├─ RunManager → PTY → CLI (claude/gemini/…)
                                                        ├─ Servidor MCP agentic-os ◄── los CLIs
                                                        └─ SQLite / logs / workspaces
```

## Fuera de alcance (por ahora)
- Multi-usuario y autenticación (fase 13).
- Registros públicos de skills (solo biblioteca local).
