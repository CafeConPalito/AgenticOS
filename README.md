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
- Claude Code se lanza aislado de tu configuración global (`--setting-sources project,local --strict-mcp-config`) y en modo de permisos manual: las peticiones de permiso aparecen en la terminal y las respondes tú ([ADR 0003](docs/adr/0003-execution-mode.md), [ADR 0004](docs/adr/0004-per-run-context-and-mcp.md)).
- Al cerrar la app, las ejecuciones activas se cortan (no queda ningún CLI vivo) y aparecen como «Interrumpida» al volver a abrirla.
- Para probar con un CLI falso o con otra ruta: `AGENTIC_OS_CLI_COMMAND_OVERRIDES='{"claude": ["ruta\\a\\claude.exe"]}'`.

## API (backend)
| Ruta | Para qué |
|---|---|
| `GET /api/health` | Estado y versión |
| `/api/agents`, `/api/agents/{id}`, `POST /api/agents/{id}/duplicate`, `GET /api/agent-templates` | Agentes y plantillas |
| `/api/projects`, `/api/projects/{id}`, `POST /api/projects/{id}/open` | Proyectos (con el estado git calculado al leerlos) |
| `GET /api/clis?refresh=true` | CLIs detectados: versión y modelos |
| `POST /api/runs`, `GET /api/runs?agent_id&project_id&active`, `GET /api/runs/{id}` | Ejecuciones: lanzar un agente sobre un proyecto con un prompt, listar y consultar |
| `POST /api/runs/{id}/control` (`take`/`release`), `POST /api/runs/{id}/stop` | Tomar o devolver el control de la terminal; parar (salida ordenada y, si no, forzada) |
| `WS /api/runs/{id}/terminal?client_id=` | Terminal en vivo: `snapshot`, `output`, `state`, `exit`; el cliente envía `input` y `resize` |

Los errores tienen la forma `{"detail": {"code", "message", "field"}}`; la interfaz traduce por `code`.
