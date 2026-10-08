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

En la app empaquetada, el backend usa un puerto libre asignado al arrancar (ver [ADR 0002](docs/adr/0002-sidecar-protocol.md)).
