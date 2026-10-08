# Fase 00: Fundaciones · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador (pendiente de aprobación, Puerta 2)
- **Rama**: `phase/00-fundaciones`

## Diseño

### Monorepo
```
agentic_os/
  package.json            # npm workspaces: frontend, desktop; scripts raíz (dev, test, lint, check, build:*)
  .gitattributes          # eol=lf (normaliza finales de línea)
  .editorconfig
  .husky/pre-commit       # lint-staged (solo lint/formato)
  backend/                # proyecto uv
  frontend/               # Vite + React
  desktop/                # Tauri v2 (src-tauri/)
  scripts/                # build-backend.ps1, check.ps1
  docs/
```
Los scripts raíz son npm (multiplataforma, válidos el día de mañana en el servidor). Los `.ps1` solo envuelven tareas propias de Windows, como el build de PyInstaller.

### Backend (`backend/`)
- **uv**, Python 3.12, paquete `agentic_os` en `backend/src/agentic_os/`.
- Dependencias: fastapi 0.143, uvicorn 0.54, pydantic-settings 2.15, structlog 26. Desarrollo: pytest 9, httpx, ruff 0.16, pyinstaller 6.22.
- Módulos:
  - `config.py`: `Settings` (pydantic-settings, prefijo `AGENTIC_OS_`, `.env`), con `host=127.0.0.1`, `port=8765`, `data_dir` (`%APPDATA%\AgenticOS` por defecto), `cors_origins` (`http://localhost:5173`, `tauri://localhost`, `http://tauri.localhost`) y `log_level`.
  - `logging.py`: structlog; salida legible en desarrollo y JSON en el build.
  - `app.py`: `create_app()` con CORS y routers bajo `/api`.
  - `api/health.py`: `GET /api/health` → `{"status":"ok","name":"Agentic OS","version":<__version__>}`.
  - `__main__.py`: entrada `agentic-os-backend` con `--host`, `--port` (`0` = puerto libre) y `--parent-pid`.
- **Protocolo con el sidecar** (ADR 0002):
  1. Con `--port 0`, el backend abre el socket en un puerto libre y se lo pasa a uvicorn (`fd`/`sockets`), sin condiciones de carrera.
  2. Cuando está listo, imprime en stdout una línea `AGENTIC_OS_READY {"port": N}`.
  3. Con `--parent-pid`, un hilo comprueba cada 2 s si el proceso padre sigue vivo y, si ha muerto, apaga el servidor. Así no quedan procesos huérfanos aunque Tauri termine de forma brusca.
- **Empaquetado**: `scripts/build-backend.ps1` ejecuta PyInstaller en modo `--onefile` y copia el ejecutable a `desktop/src-tauri/binaries/agentic-os-backend-x86_64-pc-windows-msvc.exe`, con el sufijo del target triple que exige Tauri.

### Frontend (`frontend/`)
- Vite 8, React 19, TS estricto, Tailwind 4 (`@tailwindcss/vite`), shadcn (CLI 4) con los componentes `sidebar`, `button`, `tooltip`, `badge`, `separator` y `sonner`.
- React Router 8 (router de navegador; si el build de Tauri da problemas con las rutas, cambiamos a hash: riesgo verificado en CA6).
- TanStack Query 5, i18next 26 + react-i18next 17 (`src/i18n/es.json`, idioma por defecto `es`).
- Fuentes locales con `@fontsource/ubuntu` (400/500/700) y `@fontsource/ubuntu-mono` (400/700).
- **Diseño** (ver `docs/design/` y `docs/design/revision.md`):
  - `src/styles/tokens.css` es una copia de `docs/design/tokens.css` sin el `@import` de Google Fonts.
  - Tema navy = clase `.dark` en `<html>`, por defecto; el claro es `:root`.
  - `ThemeProvider` guarda la elección en `localStorage` (con try/catch).
  - El layout reproduce las capturas `01a`/`01b` en lo que toca a esta fase:
    - sidebar de 232 px (60 px colapsada) con logo, los 7 ítems con sus iconos lucide (§6 del design system), contador de Inbox, estado «Conectado · vX» y el cambio de tema al pie;
    - header de 52 px con breadcrumb, el buscador «Buscar o ejecutar un comando… Ctrl K» (aún sin función), el botón «Terminal» (deshabilitado) y el botón primario contextual;
    - banner «Backend desconectado» cuando falla el health.
  - Se toman como base `shell.tsx` y `primitives.tsx` de `docs/design/code/`, adaptados: textos a i18n, router real y tokens en lugar de hex.
  - Componentes shadcn de esta fase: `sidebar breadcrumb button badge tooltip separator skeleton sonner`.
- **Estructura**:
  - `src/lib/api.ts`: `getApiBaseUrl()`. En Tauri hace `invoke("backend_url")` con reintentos hasta que el sidecar está listo; en el navegador usa `import.meta.env.VITE_API_URL` o `http://127.0.0.1:8765`. Además, `apiFetch()`.
  - `src/hooks/useHealth.ts`: TanStack Query que consulta `/api/health` cada 5 s.
  - `src/components/layout/AppShell.tsx`, `AppSidebar.tsx`, `AppHeader.tsx`, `BackendStatus.tsx` (Conectado / Desconectado / Conectando) y `OfflineBanner.tsx`.
  - `src/pages/`: `DashboardPage`, `AgentsPage`, `ProjectsPage`, `BoardPage`, `InboxPage`, `UsagePage` y `SettingsPage`, todas con el `EmptyState` del diseño y textos de i18n.
  - Rutas en español: `/`, `/agentes`, `/proyectos`, `/tablero`, `/inbox`, `/consumo`, `/ajustes`.
- Calidad: ESLint 10 (flat config, plugins react-hooks y jsx-a11y, y la regla `i18next/no-literal-string` para impedir cadenas en duro en el JSX), Prettier 3 y Vitest 5 con Testing Library y jsdom.

### Escritorio (`desktop/src-tauri/`)
- Tauri 2.12, identificador `com.agenticos.app`, título de ventana "Agentic OS", tamaño 1440×900 y mínimo 1100×700.
- `tauri.conf.json`:
  - `build.devUrl = http://localhost:5173` y `frontendDist = ../../frontend/dist`.
  - `bundle.externalBin = ["binaries/agentic-os-backend"]`.
  - CSP con `connect-src` a `http://127.0.0.1:*` y `ws://127.0.0.1:*` (los WS se usarán en la fase 03).
- `src/lib.rs`:
  - **Debug** (`dev:desktop`): no lanza el sidecar; `backend_url` devuelve `AGENTIC_OS_BACKEND_URL` o `http://127.0.0.1:8765`, y el backend lo arranca el script de desarrollo.
  - **Release**:
    - Lanza el sidecar con `tauri-plugin-shell` y los argumentos `--port 0 --parent-pid <pid>`.
    - Lee stdout hasta encontrar `AGENTIC_OS_READY` y guarda la URL en el estado.
    - El comando `backend_url` espera a que esté lista (timeout de 30 s y luego error visible).
    - En `RunEvent::Exit` o al cerrar la ventana, mata el proceso hijo.
- Capabilities: `shell:allow-spawn` limitado al sidecar `agentic-os-backend` y `core:default`.
- Iconos provisionales generados con `tauri icon` a partir de un SVG simple con "AO" en navy.

### Scripts raíz (`package.json`)
| Script | Acción |
|---|---|
| `dev` | `concurrently` backend (`uv run --project backend agentic-os-backend --reload`) + `npm -w frontend run dev` |
| `dev:desktop` | backend + `npm -w desktop run tauri dev` (que a su vez lanza Vite con `beforeDevCommand`) |
| `test` | `uv run --project backend pytest` y `npm -w frontend run test` |
| `lint` | `ruff check` + `ruff format --check` + `eslint` + `prettier --check` |
| `check` | `lint` y después `test` (`scripts/check.ps1` lo envuelve y muestra un resumen) |
| `build:backend` | `scripts/build-backend.ps1` |
| `build:desktop` | `build:backend` + `npm -w frontend run build` + `tauri build` |

Pre-commit: husky + lint-staged, con `ruff check --fix` y `ruff format` en `*.py`, y `eslint --fix` y `prettier --write` en `*.{ts,tsx,json,css,md}` de `frontend/`.

## Archivos
| Archivo | Cambio |
|---|---|
| `package.json`, `.gitattributes`, `.editorconfig`, `.husky/pre-commit`, `.lintstagedrc.json` | nuevos |
| `backend/pyproject.toml`, `backend/src/agentic_os/{__init__,__main__,app,config,logging}.py`, `backend/src/agentic_os/api/health.py` | nuevos |
| `backend/tests/{test_health,test_config,test_main}.py`, `backend/agentic-os-backend.spec` | nuevos |
| `frontend/` (scaffold Vite, `components.json`, `src/**`, `eslint.config.js`, `vitest.config.ts`) | nuevos |
| `desktop/package.json`, `desktop/src-tauri/{Cargo.toml,tauri.conf.json,build.rs,src/lib.rs,src/main.rs,capabilities/default.json,icons/}` | nuevos |
| `scripts/build-backend.ps1`, `scripts/check.ps1` | nuevos |
| `README.md`, `docs/adr/0002-sidecar-protocol.md`, `docs/roadmap.md` | nuevo / nuevo / modificado |

## Tareas (en orden, cada una en su commit)
1. [ ] Rama `phase/00-fundaciones`; `.gitattributes` y `.editorconfig`; `package.json` raíz con workspaces; husky + lint-staged.
2. [ ] Backend: proyecto uv, config, logging, `create_app`, `/api/health`, ruff y tests.
3. [ ] Backend: `__main__` con `--port 0`, handshake `AGENTIC_OS_READY`, watchdog `--parent-pid` y sus tests.
4. [ ] Frontend: scaffold Vite + TS + Tailwind 4 + shadcn, fuentes Ubuntu y tokens navy/light.
5. [ ] Frontend: i18n, router, AppShell, sidebar, header, las 7 páginas vacías y ThemeProvider.
6. [ ] Frontend: `api.ts`, `useHealth`, `BackendStatus`; ESLint, Prettier y tests de Vitest.
7. [ ] Scripts raíz `dev`, `test`, `lint`, `check` y `check.ps1` → CA1, CA2, CA3, CA4 y CA7 en verde.
8. [ ] Desktop: scaffold Tauri 2, ventana y modo debug con `dev:desktop` → CA5.
9. [ ] Desktop: sidecar en release, `build-backend.ps1`, `build:desktop`, cierre limpio → CA6.
10. [ ] README, ADR 0002, `validacion.md` y roadmap → CA8.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_health.py`: `GET /api/health` → 200 con `status`, `name` y `version` | CA2 |
| `test_config.py`: valores por defecto y lectura de `AGENTIC_OS_*` | CA1 |
| `test_main.py`: lanzar el backend como subproceso con `--port 0`, leer `AGENTIC_OS_READY`, pedir `/api/health` al puerto anunciado; con `--parent-pid` de un proceso ficticio que se mata, el backend termina en ≤ 5 s | CA6 (parte automatizable) |
| `AppSidebar.test.tsx`: 7 enlaces con los textos de `es.json`; al hacer clic cambia la página | CA3 |
| `ThemeProvider.test.tsx`: navy por defecto; cambiar a claro aplica la clase y se guarda en `localStorage` | CA4 |
| `BackendStatus.test.tsx`: con fetch simulado muestra "Conectado", "Desconectado" y "Conectando" | CA1 |
| `api.test.ts`: `getApiBaseUrl` en navegador (env/default) y en Tauri (`invoke` simulado, con reintentos) | CA1, CA5 |
| ESLint `i18next/no-literal-string` dentro de `lint` | CA3 |
| Visual: comparar con las capturas `01a`/`01b` (sidebar, header, tema y tipografía) | CA3, CA4 |
| Manual: `npm run dev` + captura; `npm run dev:desktop` + captura; `build:desktop` → abrir el exe, comprobar con `Get-Process` que el backend existe, cerrar la ventana y verificar que el proceso desaparece; además, matar Tauri por la fuerza y comprobar que el watchdog cierra el backend | CA1, CA5, CA6 |

## Decisiones (ADR)
- **ADR 0002: protocolo del sidecar.** Puerto libre (`--port 0`) + línea `AGENTIC_OS_READY` por stdout + watchdog del proceso padre + kill desde Tauri al salir. Alternativas descartadas: puerto fijo (choques con otros procesos) y fichero de puerto en disco (carreras y limpieza).

## Riesgos
- **PyInstaller onefile**: el arranque es más lento (descomprime en temp) y el antivirus puede dar falsos positivos. Si el arranque supera los 5 s, se pasa a `--onedir` en la fase 08.
- **Tauri sobre una ruta de React Router de navegador**: se verifica en CA6; el plan B es usar el router hash.
- **Primera compilación de Rust**: varios minutos; es normal.
