# Agentic OS

App de escritorio para orquestar un equipo de agentes de IA (Claude Code, Antigravity CLI…) que trabajan como empleados: colas por agente, pipelines (Requisitos → Desarrollo → QA), terminales en vivo con *human-in-the-loop*, conocimiento y skills.

- Visión: [`docs/vision.md`](docs/vision.md)
- Roadmap y estado de las fases: [`docs/roadmap.md`](docs/roadmap.md)
- Diseño de la interfaz: [`docs/design/`](docs/design/)
- Flujo de trabajo (Spec → Plan → Desarrollo → Validación): [`CLAUDE.md`](CLAUDE.md)

## Arquitectura
```
desktop/   Tauri 2 (Rust): ventana nativa; en release lanza el backend como sidecar
frontend/  Vite + React 19 + TypeScript + Tailwind 4 + shadcn/ui
backend/   Python 3.12 + FastAPI (uv)
scripts/   build del sidecar y check local
docs/      visión, roadmap, ADRs, fases y diseño
```

## Requisitos (Windows)
| Herramienta | Versión |
|---|---|
| Python | 3.12 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.12 |
| Node.js / npm | ≥ 22 / ≥ 10 |
| Rust (rustup, toolchain MSVC) | stable |
| Visual Studio 2022 Build Tools (C++) | necesarias para Tauri |
| WebView2 | incluido en Windows 11 |

## Puesta en marcha
```powershell
npm install                     # dependencias de frontend y desktop + hook pre-commit
uv sync --project backend       # dependencias del backend
```

## Comandos
| Comando | Qué hace |
|---|---|
| `npm run dev` | Backend (`http://127.0.0.1:8765`, con recarga) + UI en el navegador (`http://localhost:5173`) |
| `npm run dev:desktop` | Backend + ventana de Tauri en modo desarrollo |
| `npm run test` | pytest + vitest + cargo test |
| `npm run lint` | ruff + ESLint + Prettier + rustfmt |
| `npm run check` | lint y todos los tests (puerta mínima antes de integrar). `scripts/check.ps1` muestra un resumen |
| `npm run build:backend` | Empaqueta el backend con PyInstaller como sidecar (`desktop/src-tauri/binaries/`) |
| `npm run build:desktop` | Sidecar + frontend + instalador NSIS (`desktop/src-tauri/target/release/bundle/nsis/`) |

El hook pre-commit (husky + lint-staged) pasa el lint y el formato a los archivos en stage.

## Configuración del backend
Variables de entorno con prefijo `AGENTIC_OS_` (o un archivo `backend/.env`):

| Variable | Por defecto |
|---|---|
| `AGENTIC_OS_HOST` | `127.0.0.1` |
| `AGENTIC_OS_PORT` | `8765` |
| `AGENTIC_OS_DATA_DIR` | `%APPDATA%\AgenticOS` |
| `AGENTIC_OS_LOG_LEVEL` | `INFO` |
| `AGENTIC_OS_LOG_JSON` | `false` |
| `AGENTIC_OS_LOG_FILE` | (en la app empaquetada: `<data_dir>\logs\backend.log`) |
| `AGENTIC_OS_DATABASE_URL` | SQLite en `<data_dir>\agentic-os.db` |
| `AGENTIC_OS_CLI_COMMAND_OVERRIDES` | `{}` (JSON `{"claude": [...], "agy": [...]}` con el comando de cada CLI) |
| `AGENTIC_OS_CLAUDE_CONFIG_FILE`, `AGENTIC_OS_AGY_SETTINGS_FILE` | Los reales (`~/.claude.json`, `~/.gemini/antigravity-cli/settings.json`): de dónde se borra la confianza de los worktrees de tareas. Los tests los apuntan a archivos temporales |

En la app empaquetada, el backend usa un puerto libre asignado al arrancar (ver [ADR 0002](docs/adr/0002-sidecar-protocol.md)).

## Datos y migraciones
- La base de datos es SQLite en la carpeta de datos y se migra sola al arrancar el backend ([ADR 0006](docs/adr/0006-persistence.md)).
- Para probar sin tocar tus datos reales: `AGENTIC_OS_DATA_DIR=<carpeta temporal>` (vale también para la app empaquetada, que lo pasa al sidecar).
- Nueva migración tras cambiar modelos (revísala antes de hacer commit):
  ```powershell
  uv run --project backend python backend/scripts/new_migration.py "describe el cambio"
  ```

## Ejecuciones (terminales en vivo)
- Cada ejecución es el CLI del agente en una terminal real (ConPTY) que gestiona el backend ([ADR 0007](docs/adr/0007-run-processes.md)). La salida se guarda en `<data_dir>\runs\<id>.log`.
- Cada ejecución arranca con el **contexto de su agente**:
  - su rol e instrucciones;
  - la memoria del proyecto;
  - su modo de permisos («Autónomo», «Restringido» o «Preguntar»);
  - el servidor MCP `agentic-os` con un token propio.

  Lo recibe así ([ADR 0004](docs/adr/0004-per-run-context-and-mcp.md), [ADR 0008](docs/adr/0008-agent-coordination.md)):
  - **Claude Code**: por opciones, aislado de tu configuración global (`--setting-sources project,local --strict-mcp-config`). Sus archivos van en `<data_dir>\runs\<id>\`.
  - **agy**: por un plugin temporal en `.agents/plugins/agentic-os/` del proyecto, excluido de git y borrado al terminar. Solo puede haber una ejecución de agy a la vez por carpeta.
- Herramientas del MCP `agentic-os`:
  - `report_status`: el agente cuenta en qué está;
  - `write_project_memory`: añade notas a la memoria del proyecto;
  - `complete_task`: deja el resumen (y, en las etapas que revisan, el veredicto); Agentic OS cierra el CLI y la ejecución queda «Completada»;
  - `get_context`.

  Los eventos se ven en vivo en la columna «Eventos MCP».
- La primera vez que lances un agente de Claude en modo «Autónomo», Claude Code pide aceptar ese modo. Agentic OS no lo acepta por ti: toma el control de la terminal y respóndelo una vez.
- Los CLIs tienen que estar instalados como ejecutable nativo (`claude.exe`, `agy.exe`): un shim `.cmd` de npm se rechaza, porque `cmd.exe` reinterpretaría el prompt.
- Al cerrar la app, las ejecuciones activas se cortan (no queda ningún CLI vivo) y aparecen como «Interrumpida» al volver a abrirla.
- Para probar con un CLI falso o con otra ruta: `AGENTIC_OS_CLI_COMMAND_OVERRIDES='{"claude": ["ruta\\a\\claude.exe"]}'`.

## Tareas, colas y pipelines
- Una **tarea** (`T-142`) pertenece a un proyecto y la hace el agente de su **etapa** actual o, si el proyecto no tiene pipeline, el agente que elijas ([ADR 0009](docs/adr/0009-scheduler-and-workspaces.md)).
- **Colas**:
  - cada agente recorre la suya en orden: por prioridad y después por posición. Puedes reordenarla en el tablero, en «Colas por agente»;
  - un agente trabaja a la vez en tantas tareas como diga su concurrencia;
  - cada tarea es una sesión nueva del CLI, con el contexto de su proyecto y nada más.
- **Pipeline** (pestaña «Pipeline» del proyecto):
  - etapas en orden, cada una con su agente;
  - una etapa puede **requerir revisión** (la tarea espera en «En revisión» a que la apruebes o la rechaces) o **rechazar** y devolver la tarea a una etapa anterior. El agente lo hace con `complete_task(summary, verdict="rejected")`, hasta un máximo de rechazos;
  - plantilla «Desarrollo web»: Requisitos → Desarrollo → QA.
- **Cuando algo falla**, la tarea queda **«Esperando humano»** con el motivo, y el agente sigue con su cola. Desde la tarea puedes reintentarla, darla por terminada con un resumen o cancelarla. Una ejecución cortada por un reinicio nunca se relanza sola.
- **Workspaces**, según el modo del proyecto:
  - **Carpeta directa**: como mucho una tarea a la vez por proyecto; mientras, el agente adelanta trabajo de otros proyectos.
  - **Git worktree por tarea**: `<carpeta>.wt\T-142` en la rama `agentic/T-142`, creada desde la rama base. Al terminar, lo que quede sin commitear se commitea en la rama y se borra la carpeta. **La rama se conserva** y el merge lo haces tú.
- **Confianza de las carpetas**: la de los worktrees se borra de la configuración de Claude Code y de agy **solo cuando ese CLI no está abierto**, porque los CLIs reescriben esos archivos. Lo pendiente espera en `<data_dir>\trust-cleanup.json`.
- **Pausar el scheduler** (botón del tablero): no arranca tareas nuevas; las que están en marcha siguen.
- **Memoria del proyecto**: son notas con autor. A los agentes les llegan las más recientes hasta unos 12 000 caracteres, y la pestaña avisa cuando no caben todas.

## API (backend)
| Ruta | Para qué |
|---|---|
| `GET /api/health` | Estado y versión |
| `/api/agents`, `/api/agents/{id}`, `POST /api/agents/{id}/duplicate`, `GET /api/agent-templates` | Agentes y plantillas |
| `/api/projects`, `/api/projects/{id}`, `POST /api/projects/{id}/open` | Proyectos (con el estado git calculado al leerlos) |
| `/api/projects/{id}/memory`, `/api/projects/{id}/memory/{note_id}` | Notas de la memoria del proyecto |
| `GET/PUT/DELETE /api/projects/{id}/pipeline`, `POST /api/projects/{id}/pipeline/template` | Pipeline del proyecto (las etapas conservan su id) |
| `/api/tasks?project_id&agent_id&status`, `/api/tasks/{id}`, `GET /api/tasks/{id}/events` | Tareas e historial |
| `POST /api/tasks/{id}/enqueue · retry · complete · review · cancel · open-worktree` | Acciones sobre una tarea |
| `GET/PUT /api/agents/{id}/queue` | Cola de un agente / reordenarla |
| `GET /api/scheduler`, `POST /api/scheduler/pause · resume` | Estado y pausa global del scheduler |
| `GET /api/clis?refresh=true` | CLIs detectados: versión y modelos |
| `POST /api/runs`, `GET /api/runs?agent_id&project_id&task_id&active`, `GET /api/runs/{id}` | Ejecuciones: lanzar un agente sobre un proyecto con un prompt, listar y consultar |
| `POST /api/runs/{id}/control` (`take`/`release`), `POST /api/runs/{id}/stop` | Tomar o devolver el control de la terminal; parar (salida ordenada y, si no, forzada) |
| `GET /api/runs/{id}/events` | Eventos de la ejecución (herramientas MCP, hooks y acciones de Agentic OS) |
| `WS /api/runs/{id}/terminal?client_id=` | Terminal en vivo: `snapshot`, `output`, `state`, `event`, `exit`; el cliente envía `input` y `resize` |
| `/r/<token>/mcp`, `POST /r/<token>/hook/<evento>` | Para los CLIs de los agentes: servidor MCP `agentic-os` y hooks (token por ejecución) |

Los errores tienen la forma `{"detail": {"code", "message", "field"}}`; la interfaz traduce por `code`.
