# Fase 00: Fundaciones · Spec

- **Estado**: borrador (pendiente de aprobación)
- **Rama**: `phase/00-fundaciones`

## Objetivo
Montar el esqueleto del monorepo, con backend, frontend y la ventana de escritorio funcionando juntos, más las herramientas de calidad (lint, formato, tests) y los scripts de desarrollo. Así las fases siguientes solo tienen que añadir funcionalidad. Al terminar no habrá funcionalidad de producto, pero sí la cadena completa funcionando: **ventana Tauri → UI React → API FastAPI (sidecar)**.

## Alcance
### Dentro
- Estructura del monorepo: `backend/`, `frontend/`, `desktop/`, `scripts/`, `docs/`.
- **Backend** (uv + FastAPI): app mínima con `GET /api/health` (versión, estado), configuración por variables de entorno o `.env` (puerto, carpeta de datos), logging estructurado, CORS para el origen de la UI, ruff y pytest.
- **Frontend** (Vite + React + TS + Tailwind + shadcn/ui): layout base con barra lateral (Dashboard, Agentes, Proyectos, Tablero, Inbox, Consumo, Ajustes; las pantallas son marcadores vacíos), router, TanStack Query, i18next con `es.json`, un indicador de "Backend conectado" que consulta `/api/health`, tema claro/oscuro, ESLint, Prettier y vitest.
- **Escritorio** (Tauri v2): ventana que carga la UI; en desarrollo apunta al servidor de Vite y en build arranca el backend empaquetado con PyInstaller como sidecar en un puerto libre y lo para al cerrar.
- **Scripts** (`scripts/`, PowerShell y npm): `dev` (backend + frontend en paralelo), `dev:desktop`, `test` (pytest + vitest), `lint`, `build:backend` (PyInstaller), `build:desktop`.
- **CI local**: `scripts/check` ejecuta lint y todos los tests, y es la puerta mínima de cada commit. Opcionalmente un hook pre-commit.
- `README.md` con los requisitos y cómo arrancar.

### Fuera
- Base de datos, modelos y migraciones (fase 02).
- PTY, terminales y CLIs (fases 01 y 03).
- Instalador final, auto-update e iconos definitivos (fase 08).
- CI en GitHub Actions (cuando exista remoto).

## Historias de usuario
- Como desarrollador, quiero arrancar todo con un solo comando para iterar rápido.
- Como usuario, quiero abrir la app de escritorio y ver la interfaz en español con la navegación principal, y saber que el backend está conectado.
- Como desarrollador, quiero que `check` me diga si he roto algo antes de hacer commit.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | `scripts/dev` levanta el backend (`:8765` por defecto) y la UI (Vite), y la UI muestra "Backend conectado" | Ejecución manual + captura |
| CA2 | `GET /api/health` devuelve `200` con `{status:"ok", version}` | test pytest |
| CA3 | La UI tiene barra lateral con las 7 secciones, navegación funcional y textos desde `es.json` (sin cadenas en duro) | test vitest + revisión |
| CA4 | Funciona el cambio de tema claro/oscuro y se recuerda | test vitest |
| CA5 | `dev:desktop` abre una ventana Tauri con la UI conectada al backend | Ejecución manual + captura |
| CA6 | `build:desktop` genera un ejecutable que arranca el sidecar del backend en un puerto libre, lo conecta a la UI y lo para al cerrar la ventana (sin procesos huérfanos) | Ejecución manual + comprobación de procesos |
| CA7 | `scripts/check` ejecuta ruff, ESLint, Prettier (check), pytest y vitest, todos en verde | Salida del comando |
| CA8 | `README.md` documenta los requisitos y los comandos; `docs/roadmap.md` está actualizado | Revisión |

## Prerrequisitos
Ya presentes: Python 3.12.10, uv 0.12.5, Node 24.19, npm 11.17, git 2.55, Claude Code 2.1.294.

Faltan:
- ⚠️ **Rust (rustup + toolchain MSVC) y Visual Studio Build Tools (C++)**, necesarios para Tauri (CA5 y CA6). Hay que instalarlos antes de empezar el desarrollo de esta fase. WebView2 ya viene con Windows 11.
- (Para la fase 01) Gemini CLI, OpenCode y Codex CLI no están instalados.

## Riesgos y preguntas abiertas
- **Sidecar con PyInstaller en Windows**: tamaño del binario, antivirus y tiempo de arranque. Mitigación: probarlo en esta fase (CA6) en vez de dejarlo para la 08.
- **Puerto del backend**: el sidecar elige un puerto libre y se lo comunica a la UI a través de Tauri (comando o evento). Se detalla en el plan.
- **Nombre de la app**: "Agentic OS" como nombre provisional. ¿Te vale?
